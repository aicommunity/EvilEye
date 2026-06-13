# IPC KPI Comparison

- Baseline log: `logs/20260414_164906_evileye_main.log`
- Candidate log: `logs/20260414_174432_evileye_main.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 14 | 6 | -8 |
| Errors | 1 | 0 | -1 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 4 | 0 | -4 |
| Suppressed restarts | 0 | 1 | +1 |
| Stop timeouts | 2 | 0 | -2 |
| Force-kills | 1 | 0 | -1 |
| p95 Pipeline loop (ms) | 0.000 | 0.000 | +0.000 |
| Estimated pipeline Hz | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 0.000 | 0.000 | +0.000 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

