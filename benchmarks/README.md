# Benchmarks

Phase 4 benchmark suite provides reproducible baseline measurements for core hot paths.

## Run Phase 4 Baseline

```bash
python benchmarks/phase4_baseline.py
```

Optional tuning:

```bash
python benchmarks/phase4_baseline.py --iterations 30000 --modules 100
```

## Metrics Produced

- app startup and module registration time
- in-process dispatch throughput (`app.execute`)
- HTTP adapter in-process throughput (`HTTPAdapter` ASGI call path)

The script prints JSON for easy copy into reports/CI artifacts.
