[![CI](https://img.shields.io/github/actions/workflow/status/nxd914/kinzie/ci.yml?branch=main&label=CI)](https://github.com/nxd914/kinzie/actions)
[![License](https://img.shields.io/github/license/nxd914/kinzie)](https://github.com/nxd914/kinzie/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org)
[![GitHub last commit](https://img.shields.io/github/last-commit/nxd914/kinzie)](https://github.com/nxd914/kinzie/commits/main)

# Kinzie

Async prediction market trading system built in Python 3.11+. Deterministic execution pipeline — no ML, no heuristics. Every decision is a closed-form function of market price and realized volatility, sized by Kelly criterion, gated behind hard risk controls.

## Architecture

```
CryptoFeedAgent ──► FeatureAgent ──► ScannerAgent ──► RiskAgent ──► ExecutionAgent ──► ResolutionAgent
                                          ▲
                                    WebsocketAgent
                                   (real-time price cache)
```

Seven concurrent async agents coordinated through typed `asyncio.Queue` instances and a read-only WebSocket price cache. No shared mutable state between agents.

## Stack

- **Runtime**: Python 3.11+, `asyncio`, frozen dataclasses throughout
- **Persistence**: SQLite audit trail — every fill records market state at signal time
- **Testing**: pytest + [Hypothesis](https://hypothesis.readthedocs.io/) property-based tests; AAA pattern; 80%+ coverage enforced in CI
- **Quality**: ruff (lint + format), mypy (strict), GitHub Actions on every push and PR across Python 3.11/3.12
- **Deployment**: Docker + Railway; structured JSON logging via `LOG_FORMAT=json`

## Repository

```
core/       Pricing and risk models — pure math, no I/O, no side effects
agents/     Async execution layer — seven concurrent agents
tests/      Pytest suite + Hypothesis property tests
research/   Replay backtester, health checks, P&L analysis
benchmarks/ Hot-path profiling
docs/       Strategy derivations, risk model, ops runbook
deploy/     Docker / Railway config
```

## Quick start

```bash
pip install -e ".[dev]"
pytest tests/
```

Requires credentials set in a `.env` at the repo root (see `CLAUDE.md`). Paper mode is the default — live trading is gated behind empirical performance thresholds enforced in `core/config.py`.

## License

Proprietary. All rights reserved.
