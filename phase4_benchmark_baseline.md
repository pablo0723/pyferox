# Phase 4 Benchmark Baseline

Snapshot date: 2026-03-18.

Command:

```bash
python benchmarks/phase4_baseline.py
```

Output:

```json
{
  "startup_ms": 0.369,
  "dispatch_rps": 156005.94,
  "http_rps": 105427.0,
  "iterations": 20000,
  "modules": 50
}
```

## Notes

- This benchmark is in-process and primarily tracks relative regressions.
- It is useful for CI trend checks, not for absolute network throughput claims.
- For external HTTP benchmarks, run `wrk`/load tests with explicit server/runtime flags.
