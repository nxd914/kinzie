from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, RAW_DATA_DIR


DISPLAY_COLUMNS = [
    "transaction_at",
    "business_date",
    "processor",
    "venue_area",
    "terminal_id",
    "reference_id",
    "transaction_type",
    "amount",
    "settlement_status",
    "auth_code",
    "discrepancy_type",
    "recommended_action",
]


@dataclass(frozen=True)
class PipelineArtifacts:
    ledger_path: Path
    discrepancy_path: Path
    dashboard_path: Path


def normalize_shift4(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["transaction_at"] = pd.to_datetime(
        df["TransactionDate"] + " " + df["Time"], utc=False
    )
    normalized = pd.DataFrame(
        {
            "transaction_at": df["transaction_at"],
            "business_date": df["TransactionDate"],
            "processor": "Shift4",
            "venue_area": df["VenueArea"],
            "terminal_id": df["TerminalID"],
            "reference_id": df["InvoiceNumber"],
            "auth_code": df["AuthCode"].fillna(""),
            "tender_type": df["CardType"],
            "transaction_type": "SALE",
            "amount": df["SettleAmount"].astype(float),
            "settlement_status": df["Status"],
            "batch_id": df["BatchID"],
            "source_file": path.name,
        }
    )
    return normalized


def normalize_freedompay(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    transaction_at = pd.to_datetime(df["Timestamp"], utc=True).dt.tz_convert(
        "America/Chicago"
    )
    normalized = pd.DataFrame(
        {
            "transaction_at": transaction_at.dt.tz_localize(None),
            "business_date": transaction_at.dt.strftime("%Y-%m-%d"),
            "processor": "FreedomPay",
            "venue_area": df["VenueArea"],
            "terminal_id": df["Pos_Terminal"],
            "reference_id": df["Req_ID"],
            "auth_code": df["Auth_Code"].fillna(""),
            "tender_type": "CARD",
            "transaction_type": df["Tran_Type"],
            "amount": df["Settled_Amt"].astype(float),
            "settlement_status": df["Settlement_State"],
            "batch_id": df["Store_ID"],
            "source_file": path.name,
        }
    )
    return normalized


def normalize_amazon(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    transaction_at = pd.to_datetime(df["Trip_End"], utc=False)
    normalized = pd.DataFrame(
        {
            "transaction_at": transaction_at,
            "business_date": transaction_at.dt.strftime("%Y-%m-%d"),
            "processor": "Amazon JWO",
            "venue_area": df["VenueArea"],
            "terminal_id": df["Gate_ID"],
            "reference_id": df["Amazon_Ref"],
            "auth_code": "",
            "tender_type": "AMAZON",
            "transaction_type": "SALE",
            "amount": df["Total_Billed"].astype(float),
            "settlement_status": df["Settlement_Status"],
            "batch_id": df["Location_ID"],
            "source_file": path.name,
        }
    )
    return normalized


def generate_unified_ledger() -> pd.DataFrame:
    frames = [
        normalize_shift4(RAW_DATA_DIR / "shift4_settlement.csv"),
        normalize_freedompay(RAW_DATA_DIR / "freedompay_settlement.csv"),
        normalize_amazon(RAW_DATA_DIR / "amazon_jwo_settlement.csv"),
    ]
    ledger = pd.concat(frames, ignore_index=True)
    ledger["amount"] = ledger["amount"].round(2)
    ledger["discrepancy_type"] = ""
    ledger["recommended_action"] = ""
    return ledger.sort_values(["transaction_at", "processor", "reference_id"]).reset_index(
        drop=True
    )


def apply_rules(ledger: pd.DataFrame) -> pd.DataFrame:
    reviewed = ledger.copy()

    settled_statuses = {"SETTLED", "CAPTURED", "CLEARED"}
    unsettled_mask = ~reviewed["settlement_status"].isin(settled_statuses)
    reviewed.loc[unsettled_mask, "discrepancy_type"] = "Unsettled status"
    reviewed.loc[
        unsettled_mask, "recommended_action"
    ] = "Confirm if this is a timing delay or a true settlement failure."

    missing_auth_mask = (
        reviewed["processor"].isin(["Shift4", "FreedomPay"])
        & reviewed["auth_code"].astype(str).str.strip().eq("")
    )
    reviewed.loc[missing_auth_mask, "discrepancy_type"] = "Missing auth code"
    reviewed.loc[
        missing_auth_mask, "recommended_action"
    ] = "Review processor detail and verify authorization before close."

    refund_mask = reviewed["transaction_type"].eq("REFUND")
    reviewed.loc[refund_mask, "discrepancy_type"] = "Refund requires offset review"
    reviewed.loc[
        refund_mask, "recommended_action"
    ] = "Match this refund against the original sale and settlement batch."

    duplicate_mask = reviewed.duplicated(
        subset=["processor", "reference_id"], keep=False
    )
    reviewed.loc[duplicate_mask, "discrepancy_type"] = "Duplicate reference"
    reviewed.loc[
        duplicate_mask, "recommended_action"
    ] = "Check for duplicate export rows or double settlement."

    high_value_mask = reviewed["amount"].abs().ge(1000)
    unflagged_high_value = high_value_mask & reviewed["discrepancy_type"].eq("")
    reviewed.loc[unflagged_high_value, "discrepancy_type"] = "High-value review"
    reviewed.loc[
        unflagged_high_value, "recommended_action"
    ] = "Large transaction. Validate amount and batch before close."

    return reviewed


def build_dashboard_payload(reviewed: pd.DataFrame) -> dict:
    discrepancies = reviewed[reviewed["discrepancy_type"].ne("")].copy()
    total_volume = float(reviewed["amount"].sum())
    cleared_volume = float(
        reviewed.loc[reviewed["discrepancy_type"].eq(""), "amount"].sum()
    )
    at_risk_volume = float(discrepancies["amount"].sum())
    metrics = {
        "total_transactions": int(len(reviewed)),
        "flagged_transactions": int(len(discrepancies)),
        "total_volume": round(total_volume, 2),
        "cleared_volume": round(cleared_volume, 2),
        "at_risk_volume": round(at_risk_volume, 2),
    }

    processor_summary = (
        reviewed.groupby("processor", dropna=False)
        .agg(
            transactions=("reference_id", "count"),
            total_amount=("amount", "sum"),
            flagged=("discrepancy_type", lambda s: int((s != "").sum())),
        )
        .reset_index()
    )

    discrepancy_summary = (
        discrepancies.groupby("discrepancy_type", dropna=False)
        .agg(
            count=("reference_id", "count"),
            total_amount=("amount", "sum"),
        )
        .reset_index()
        .sort_values(["count", "total_amount"], ascending=[False, False])
    )

    recent = reviewed.sort_values("transaction_at", ascending=False).head(12)
    discrepancies = _serialize_records(discrepancies[DISPLAY_COLUMNS])
    recent = _serialize_records(recent[DISPLAY_COLUMNS])
    payload = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "metrics": metrics,
        "processor_summary": processor_summary.to_dict(orient="records"),
        "discrepancy_summary": discrepancy_summary.to_dict(orient="records"),
        "discrepancies": discrepancies,
        "recent_activity": recent,
    }
    return payload


def _serialize_records(df: pd.DataFrame) -> list[dict]:
    serializable = df.copy()
    for column in serializable.columns:
        if pd.api.types.is_datetime64_any_dtype(serializable[column]):
            serializable[column] = serializable[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    return serializable.to_dict(orient="records")


def run_pipeline() -> PipelineArtifacts:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = generate_unified_ledger()
    reviewed = apply_rules(ledger)
    discrepancies = reviewed[reviewed["discrepancy_type"].ne("")].copy()
    dashboard = build_dashboard_payload(reviewed)

    ledger_path = OUTPUT_DIR / "unified_ledger.csv"
    discrepancy_path = OUTPUT_DIR / "discrepancies.csv"
    dashboard_path = OUTPUT_DIR / "dashboard.json"

    reviewed.to_csv(ledger_path, index=False)
    discrepancies.to_csv(discrepancy_path, index=False)
    dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")

    return PipelineArtifacts(
        ledger_path=ledger_path,
        discrepancy_path=discrepancy_path,
        dashboard_path=dashboard_path,
    )


if __name__ == "__main__":
    artifacts = run_pipeline()
    print(f"Wrote {artifacts.ledger_path}")
    print(f"Wrote {artifacts.discrepancy_path}")
    print(f"Wrote {artifacts.dashboard_path}")
