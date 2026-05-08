"""
Execution Agent

Receives approved (opportunity, size_usdc) pairs from the risk agent
and places orders on Kalshi via the authenticated API.

Modes (resolved by core.environment.resolve_environment):
  PAPER      — places real orders against the Kalshi DEMO API.
  LIVE       — places real orders against the Kalshi PRODUCTION API.

The agent never reads EXECUTION_MODE directly — the daemon resolves the
Environment once and passes it in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional


class OrderOutcome(NamedTuple):
    """Terminal result of polling an order through grace.

    terminal_status ∈ {FILLED, PARTIAL, REJECTED, TIMEOUT, CANCELLED}.
    REJECTED means the exchange rejected; TIMEOUT means grace expired
    with no fill and we cancelled. Conflating these in logs hid which
    knob (cross-offset vs grace vs price-validity) was actually wrong.
    """

    filled_count: int
    fill_price: float
    terminal_status: str
    reason: str

from core.db import connect as db_connect
from core.environment import Environment, resolve_environment
from core.kalshi_client import KalshiClient
from ..core.config import DEFAULT_CONFIG, Config
from ..core.models import Order, OrderStatus, Side, TradeOpportunity

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "paper_trades.db"


def _extract_post_error_reason(post_error: Optional[str], resp: object) -> str:
    """Pull a Kalshi `error.code` out of the POST error envelope.

    `_post` returns `{"_error": "http_400", "_body": '{"error":{"code":...}}'}`
    on rejection. We've been logging the whole blob and ignoring the code,
    which is the only field that tells us *why* the price was invalid.
    """
    if post_error is None and not isinstance(resp, dict):
        return ""
    body = resp.get("_body") if isinstance(resp, dict) else None
    if isinstance(body, str) and body:
        try:
            parsed = json.loads(body)
            err = parsed.get("error") if isinstance(parsed, dict) else None
            if isinstance(err, dict):
                code = err.get("code") or err.get("message")
                if code:
                    return f"{post_error or 'http_error'}:{code}"
        except (ValueError, TypeError):
            pass
    detail = resp.get("_detail") if isinstance(resp, dict) else None
    if detail:
        return f"{post_error or 'error'}:{str(detail)[:80]}"
    return post_error or "no_order_id"


def _extract_order_view_reason(order_view: dict) -> str:
    """Best-effort: dig a reason field out of get_order's response."""
    for key in ("reject_reason", "rejection_reason", "error", "error_message", "message"):
        val = order_view.get(key)
        if val:
            if isinstance(val, dict):
                code = val.get("code") or val.get("message")
                if code:
                    return str(code)[:120]
            return str(val)[:120]
    return ""


class ExecutionAgent:
    """
    Places orders (paper or live) and persists trade records.
    """

    def __init__(
        self,
        approved_queue: asyncio.Queue[tuple[TradeOpportunity, float]],
        risk_agent=None,   # typed weakly to avoid circular import
        environment: Optional[Environment] = None,
        config: Optional[Config] = None,
    ) -> None:
        self._approved = approved_queue
        self._risk_agent = risk_agent
        self._env = environment or resolve_environment()
        self._cfg = config or DEFAULT_CONFIG
        self._db = self._init_db()
        self._kalshi: Optional[KalshiClient] = None
        logger.info(
            "ExecutionAgent ready | mode=%s | grace=%.1fs | cross_offset=[%.2f,%.2f]",
            self._env.label,
            self._cfg.execution_fill_grace_seconds,
            self._cfg.execution_cross_offset_min,
            self._cfg.execution_cross_offset_max,
        )

    async def run(self) -> None:
        while True:
            opp, size_usdc = await self._approved.get()
            order = await self._execute(opp, size_usdc)
            # RiskAgent optimistically books the slot at approval time.
            # If we couldn't actually fill, release the slot so the same
            # expiry/symbol isn't blocked for the life of the market.
            if order.status == OrderStatus.REJECTED and self._risk_agent is not None:
                try:
                    self._risk_agent.release_position(opp.market.ticker)
                except Exception as exc:
                    logger.warning(
                        "release_position(%s) failed: %s",
                        opp.market.ticker, exc,
                    )
            self._persist(order)
            logger.info(
                "Order %s | %s | %.2f USDC | fill=%.4f",
                order.status.value,
                opp.market.title[:50],
                size_usdc,
                order.fill_price or 0.0,
            )

    async def _execute(
        self, opp: TradeOpportunity, size_usdc: float
    ) -> Order:
        return await self._live_order(opp, size_usdc)

    async def _live_order(self, opp: TradeOpportunity, size_usdc: float) -> Order:
        if self._kalshi is None:
            self._kalshi = KalshiClient(
                api_key=self._env.api_key,
                private_key_path=self._env.private_key_path,
                base_url=self._env.rest_base_url,
            )
            await self._kalshi.open()
            logger.info(
                "ExecutionAgent: KalshiClient opened against %s (mode=%s)",
                self._env.rest_base_url,
                self._env.label,
            )

        now = datetime.now(tz=timezone.utc)
        signal_ts = getattr(opp.signal, "timestamp", None)
        signal_age_ms = (
            int((now - signal_ts).total_seconds() * 1000) if signal_ts is not None else -1
        )
        loop_t0 = asyncio.get_event_loop().time()

        # Cross-the-spread offset: the cached ask is a snapshot from the
        # scanner pass and on thin Kalshi 15m books often gets eaten or
        # walked before our POST lands. Bid a few cents above to actually
        # match a marketable seller. We have huge edge (typically 30-45%
        # on these signals); paying 3-5¢ to enter is cheap insurance against
        # the 0/N grace_expired loop. Capped against edge so we never pay
        # away more than half of what we'd capture.
        cross_offset = min(
            self._cfg.execution_cross_offset_max,
            max(self._cfg.execution_cross_offset_min, getattr(opp, "edge", 0.0) * 0.5),
        )

        # Refresh top-of-book just before POST. The scanner's cached ask can
        # be 1-5s stale by the time the order lands, and on thin demo books
        # the inside walks faster than our cross_offset — that's the 0/N
        # grace_expired loop we keep hitting. One extra REST call (~50-100ms)
        # is well inside the 30s grace.
        cached_yes_ask = opp.market.yes_ask
        cached_no_ask = opp.market.no_ask
        live_yes_ask = cached_yes_ask
        live_no_ask = cached_no_ask
        try:
            fresh = await self._kalshi.get_market(opp.market.ticker)
            if fresh is not None:
                live_yes_ask = fresh.yes_ask or cached_yes_ask
                live_no_ask = fresh.no_ask or cached_no_ask
        except Exception as exc:
            logger.warning(
                "get_market refresh failed for %s — using cached ask: %s",
                opp.market.ticker, exc,
            )

        if opp.side == Side.YES:
            base_ask = live_yes_ask
            fill_price = round(max(0.01, min(0.99, base_ask + cross_offset)), 2)
            yes_price_dollars = fill_price
            stale_delta = live_yes_ask - cached_yes_ask
        else:
            base_ask = live_no_ask
            no_price_dollars = round(max(0.01, min(0.99, base_ask + cross_offset)), 2)
            fill_price = no_price_dollars
            yes_price_dollars = round(1.0 - no_price_dollars, 2)
            stale_delta = live_no_ask - cached_no_ask
        if abs(stale_delta) >= 0.01:
            logger.info(
                "Ask refreshed | %s | side=%s cached=%.3f live=%.3f delta=%+0.3f offset=%.3f post=%.3f",
                opp.market.ticker, opp.side.value, base_ask - stale_delta,
                base_ask, stale_delta, cross_offset, fill_price,
            )

        # Cap order count so we don't post 2000+ contracts on a 50-deep book.
        # Most demo 15m markets carry < 200 contracts at the inside; bigger
        # orders just sit unfilled.
        max_count_cap = 200
        count = max(1, min(max_count_cap, int(size_usdc / fill_price)))

        post_t0 = asyncio.get_event_loop().time()
        try:
            resp = await self._kalshi.place_limit_order(
                ticker=opp.market.ticker,
                side=opp.side.value.lower(),
                count=count,
                yes_price_dollars=yes_price_dollars,
                order_group_id=getattr(self, "_order_group_id", None),
            )
        except Exception as exc:
            logger.error("Live order failed for %s: %s", opp.market.ticker, exc)
            return Order(
                opportunity=opp,
                size_usdc=size_usdc,
                status=OrderStatus.REJECTED,
                fill_price=None,
                placed_at=now,
                error=str(exc),
            )

        post_ms = int((asyncio.get_event_loop().time() - post_t0) * 1000)
        pre_ms = int((post_t0 - loop_t0) * 1000)
        logger.info(
            "LATENCY %s | signal_age=%dms pre_post=%dms post=%dms",
            opp.market.ticker, signal_age_ms, pre_ms, post_ms,
        )

        # Distinguish POST failure modes (set by kalshi_client._post):
        #   _error=rate_limited → POST may have landed; reconcile via WS/poll
        #   _error=network/http_* → POST never reached; safe to release slot
        post_error = resp.get("_error") if isinstance(resp, dict) else None
        order_data = resp.get("order", resp)
        order_id = order_data.get("order_id") or order_data.get("id")

        if not order_id:
            reason = _extract_post_error_reason(post_error, resp)
            error_msg = f"{post_error or 'no_order_id'}: {str(resp)[:180]}"
            log_fn = logger.warning if post_error == "rate_limited" else logger.error
            log_fn(
                "Live order rejected for %s: %s | reason=%s",
                opp.market.ticker, error_msg, reason,
            )
            edge_v = getattr(opp, "edge", 0.0)
            logger.info(
                "Order outcome | %s | edge=%.3f | filled=0/? | status=REJECTED | reason=%s",
                opp.market.ticker, edge_v, reason,
            )
            return Order(
                opportunity=opp,
                size_usdc=size_usdc,
                status=OrderStatus.REJECTED,
                fill_price=None,
                placed_at=now,
                error=error_msg,
            )

        # Kalshi V2 limits fill ASYNC — the immediate POST response carries
        # fill_count=0 even for orders that will match a moment later.
        # Poll get_order(order_id) until we see a fill OR the grace window
        # expires; only then cancel. Records FILLED only when Kalshi confirms.
        outcome = await self._await_fill_or_cancel(
            order_id=str(order_id),
            requested_count=count,
            limit_price=fill_price,
        )
        filled_count = outcome.filled_count
        fill_price_actual = outcome.fill_price

        edge = getattr(opp, "edge", 0.0)
        if filled_count <= 0:
            # TIMEOUT vs REJECTED matters: TIMEOUT → grace/cross-offset levers;
            # REJECTED → price validity / exchange-side rule. Log them apart.
            logger.info(
                "Order outcome | %s | edge=%.3f | grace=%.1fs | filled=0/%d | status=%s | reason=%s",
                opp.market.ticker, edge,
                self._cfg.execution_fill_grace_seconds, count,
                outcome.terminal_status, outcome.reason or "-",
            )
            return Order(
                opportunity=opp,
                size_usdc=size_usdc,
                status=OrderStatus.REJECTED,
                fill_price=None,
                placed_at=now,
                error=f"{outcome.terminal_status.lower()} count={count} reason={outcome.reason or '-'}",
            )

        actual_size = filled_count * fill_price_actual
        status = OrderStatus.FILLED if filled_count >= count else OrderStatus.PENDING
        logger.info(
            "Order outcome | %s | edge=%.3f | filled=%d/%d | px=%.4f | status=%s",
            opp.market.ticker, edge, filled_count, count,
            fill_price_actual, status.value,
        )
        return Order(
            opportunity=opp,
            size_usdc=actual_size,
            status=status,
            fill_price=fill_price_actual,
            placed_at=now,
            filled_at=now if status == OrderStatus.FILLED else None,
            order_id=str(order_id),
        )

    async def _await_fill_or_cancel(
        self,
        order_id: str,
        requested_count: int,
        limit_price: float,
    ) -> OrderOutcome:
        """Poll the order until filled or grace window elapses; cancel if stale.

        Returns an OrderOutcome carrying terminal_status (FILLED, PARTIAL,
        REJECTED, CANCELLED, TIMEOUT) and any reason string the exchange
        surfaced. filled_count may be partial; on zero, the order has
        either been rejected by the exchange or cancelled by us.
        """
        deadline = asyncio.get_event_loop().time() + self._cfg.execution_fill_grace_seconds
        poll_every = max(0.1, self._cfg.execution_fill_poll_interval_seconds)
        filled_count = 0
        fill_price_actual = limit_price

        while True:
            try:
                order_view = await self._kalshi.get_order(order_id)
            except Exception as exc:
                logger.warning("get_order(%s) failed: %s", order_id, exc)
                order_view = {}

            status_str = (order_view.get("status") or "").lower()
            raw_filled = (
                order_view.get("fill_count")
                or order_view.get("filled_count")
                or 0
            )
            try:
                filled_count = int(float(raw_filled))
            except (TypeError, ValueError):
                filled_count = 0

            if filled_count > 0:
                # Prefer Kalshi's reported avg fill price if present.
                avg_cents = order_view.get("yes_price") or order_view.get("avg_yes_price")
                if avg_cents is not None:
                    try:
                        fill_price_actual = float(avg_cents) / 100.0
                    except (TypeError, ValueError):
                        pass
                terminal = "FILLED" if filled_count >= requested_count else "PARTIAL"
                return OrderOutcome(filled_count, fill_price_actual, terminal, "")

            if status_str in ("canceled", "cancelled", "expired", "rejected"):
                reason = _extract_order_view_reason(order_view)
                if status_str == "rejected" and not reason:
                    # Surface the full view once so we can learn what
                    # field (if any) Kalshi populates on rejection.
                    logger.warning(
                        "get_order(%s) returned rejected with no reason; view=%s",
                        order_id, str(order_view)[:300],
                    )
                terminal_map = {
                    "canceled": "CANCELLED",
                    "cancelled": "CANCELLED",
                    "expired": "CANCELLED",
                    "rejected": "REJECTED",
                }
                return OrderOutcome(
                    0, limit_price, terminal_map[status_str], reason,
                )

            if asyncio.get_event_loop().time() >= deadline:
                break

            await asyncio.sleep(poll_every)

        # Grace window expired with no fill — cancel and report unfilled.
        try:
            await self._kalshi.cancel_order(order_id)
        except Exception as exc:
            logger.warning("cancel_order failed for %s: %s", order_id, exc)
        return OrderOutcome(0, limit_price, "TIMEOUT", "grace_expired")

    def _persist(self, order: Order) -> None:
        opp = order.opportunity
        spot_price = opp.signal.features.spot_price if opp.signal else 0.0
        signal_latency_ms = 0.0
        if opp.signal and opp.signal.timestamp:
            delta = (order.placed_at - opp.signal.timestamp).total_seconds()
            signal_latency_ms = delta * 1000.0
        realized_vol = opp.signal.features.realized_vol_long if opp.signal else 0.0
        kelly_fraction = opp.capped_fraction
        now = order.placed_at.isoformat()
        # REJECTED orders (no order_id from Kalshi) are resolved immediately
        # so they're never treated as open positions by anything downstream.
        is_rejected = order.status == OrderStatus.REJECTED
        resolution = "REJECTED" if is_rejected else None
        resolved_at = now if is_rejected else None
        pnl_usdc = 0.0 if is_rejected else None
        try:
            self._db.execute(
                """
                INSERT INTO trades (
                    order_id, ticker, title, side,
                    model_prob, market_prob, edge,
                    size_usdc, fill_price, status,
                    placed_at, filled_at,
                    spot_price_at_signal, signal_latency_ms,
                    realized_vol, kelly_fraction,
                    environment,
                    resolution, resolved_at, pnl_usdc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    opp.market.ticker,
                    opp.market.title[:200],
                    opp.side.value,
                    opp.model_prob,
                    opp.market_prob,
                    opp.edge,
                    order.size_usdc,
                    order.fill_price,
                    order.status.value,
                    now,
                    order.filled_at.isoformat() if order.filled_at else None,
                    spot_price,
                    signal_latency_ms,
                    realized_vol,
                    kelly_fraction,
                    self._env.label,
                    resolution,
                    resolved_at,
                    pnl_usdc,
                ),
            )
            self._db.commit()
        except sqlite3.Error as exc:
            logger.error("DB write error: %s", exc)

    def _init_db(self) -> sqlite3.Connection:
        # Ensure data directory exists and table is initialized
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = db_connect(str(DB_PATH), check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                ticker TEXT,
                title TEXT,
                side TEXT,
                model_prob REAL,
                market_prob REAL,
                edge REAL,
                size_usdc REAL,
                fill_price REAL,
                status TEXT,
                placed_at TEXT,
                filled_at TEXT,
                resolved_at TEXT,
                resolution TEXT,
                pnl_usdc REAL,
                spot_price_at_signal REAL,
                signal_latency_ms REAL,
                realized_vol REAL,
                kelly_fraction REAL,
                environment TEXT
            )
        """)
        # Migrate existing DBs: add new audit columns if missing
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()
        }
        for col in ("spot_price_at_signal", "signal_latency_ms", "realized_vol", "kelly_fraction"):
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} REAL")
        if "environment" not in existing_cols:
            conn.execute("ALTER TABLE trades ADD COLUMN environment TEXT")
        conn.commit()
        return conn
