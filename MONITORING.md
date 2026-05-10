# Microstructure Ingestion Monitoring

Microstructure monitors data ingestion health, snapshot freshness, and research-data quality.

## Logs

```bash
python3 -m strategies.crypto.daemon
```

Expected startup line:

```text
Microstructure L2 ingestion running | symbols=BTC,ETH | depth=10 | jsonl=data/l2
```

For a systemd deployment:

```bash
journalctl -fu microstructure
```

## Metrics To Watch

- WebSocket reconnect warnings from `CryptoFeedAgent`.
- Snapshot write rate in `data/l2/*.jsonl`.
- Queue pressure if the feed blocks on `SNAPSHOT_QUEUE_SIZE`.
- Freshness of latest JSONL file modification time.
- Per-symbol sequence monotonicity in `L2Snapshot.sequence`.

## Basic Checks

```bash
ls -lh data/l2
tail -n 3 data/l2/*.jsonl
pytest tests/test_crypto_l2_feed.py tests/test_l2_datamodule.py tests/test_deeplob.py
```

## Failure Modes

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| No JSONL files | Writer disabled or WebSocket not connected | Check `L2_PERSIST_JSONL` and daemon logs |
| Frequent reconnects | Network or Kraken WebSocket issue | Confirm internet access and retry backoff |
| Queue saturated | Disk writes too slow or consumer stopped | Increase queue size or move output to faster disk |
| NaN targets | Invalid book prices or empty book side | Inspect raw snapshots and feed parser tests |
