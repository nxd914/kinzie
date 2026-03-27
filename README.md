# ClearLine Agent

ClearLine Agent is an engine-first prototype for reconciling fragmented payment processor exports in sports and live venue operations.

The wedge is straightforward: finance teams often receive separate settlement files from Shift4, FreedomPay, Amazon JWO / Tap and Go, and other processors, then manually stitch them together in spreadsheets just to answer one question:

Did yesterday's money actually settle the way it should have?

This repo turns that workflow into a product foundation.

## What it does today

- ingests synthetic settlement exports from Shift4, FreedomPay, and Amazon JWO
- normalizes them into a unified ledger
- flags deterministic exceptions like unsettled rows, missing auth codes, duplicate references, refunds, and high-value reviews
- generates machine-readable outputs for downstream systems
- serves a local browser dashboard for an action queue and processor-level summary

## Product direction

This is meant to become a desktop-first B2B SaaS product, not a mobile-first consumer app.

The real value is not a pretty dashboard. The value is:

- reducing manual reconciliation time
- catching missed settlement issues faster
- creating a clean audit trail
- preparing unresolved exceptions for an agentic review layer later

## Current stack

- Engine: Python 3.13 + pandas
- Server: Python standard library HTTP server
- Frontend: static HTML, CSS, and JavaScript
- Data: synthetic CSV exports in `data/raw/`

No external web framework is required for the current prototype.

## Quick start

Generate the latest ledger and discrepancy outputs:

```bash
cd /Users/noahdonovan/clear-line
PYTHONPATH=src python -m clearline.pipeline
```

Start the local dashboard:

```bash
cd /Users/noahdonovan/clear-line
PYTHONPATH=src python -m clearline.server
```

Then open `http://127.0.0.1:8000`.

## Demo flow

1. Drop processor exports into `data/raw/`.
2. Run the reconciliation pipeline.
3. Review:
   - unified ledger output
   - discrepancy queue
   - processor-level risk summary
4. Use the action queue as the basis for human review or future LLM classification.

## Repository structure

- `data/raw/`
  Synthetic processor exports for Shift4, FreedomPay, and Amazon JWO.
- `data/output/`
  Generated unified ledger, discrepancy CSV, and dashboard JSON.
- `src/clearline/`
  Core reconciliation logic, normalization rules, and local HTTP server.
- `web/static/`
  Desktop-first dashboard UI.
- `docs/roadmap.md`
  Product sequence from prototype to pilot-ready company.

## Current outputs

The pipeline currently produces:

- `data/output/unified_ledger.csv`
- `data/output/discrepancies.csv`
- `data/output/dashboard.json`

## What should come next

- swap the synthetic CSV headers for processor exports that match your real operating environment
- add a source-of-truth sales feed from POS, ticketing, or internal finance systems
- move rule configuration out of code and into venue-specific mappings
- add an LLM classification step only for unresolved discrepancies
- deploy to Google Cloud Run with authentication and persistent storage
- connect downstream systems like NetSuite, Workday, or internal finance workflows

## Why this can become a company

The initial product is software.

The company is the layer that sits between processors and finance teams, becomes system-of-record for reconciliation decisions, and eventually learns settlement behavior across venues well enough to automate exception handling safely.
