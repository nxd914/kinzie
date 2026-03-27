# Roadmap

## 1. Wedge

Build the system as a desktop-first B2B SaaS product for finance and venue operations teams.

Do not spend time on a mobile app now. Mobile is only useful later for alerting and approvals.

## 2. Product sequence

1. Get processor ingestion correct.
2. Normalize all exports into one ledger.
3. Add deterministic rules and explainable actions.
4. Add expected-sales comparison using POS, ticketing, and settlement totals.
5. Add role-based review workflow and audit trail.
6. Add LLM classification only for unresolved exceptions.
7. Deploy to Google Cloud Run with Cloud SQL or Postgres.
8. Add SSO, audit logging, and customer isolation.
9. Pilot with one venue.
10. Turn pilot wins into a case study and sell into adjacent venues.

## 3. Technical milestones

### Local prototype

- synthetic exports
- unified ledger generation
- discrepancy queue
- local browser dashboard

### Pilot-ready product

- secure upload flow
- persistent database
- venue-specific processor mappings
- CSV and PDF export
- agent recommendations with human approval

### Scale-ready product

- customer-specific connectors
- GL integrations
- automated chargeback workflows
- SLA monitoring
- SOC 2 controls

## 4. What to do next from here

1. Replace the synthetic files with your best memory of real Shift4, FreedomPay, and Amazon headers.
2. Add one more "expected source of truth" feed, ideally POS or ticketing sales.
3. Define 10-15 discrepancy categories that actually matter to finance.
4. Start collecting screenshots of the manual Excel process and map each pain point to a product screen.
5. Push the repo to GitHub and iterate in public or privately, depending on your employment/IP risk.

