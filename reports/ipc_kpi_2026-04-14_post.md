# IPC KPI Comparison

- Baseline log: `logs/20260414_164906_evileye_main.log`
- Candidate log: `logs/20260414_173200_evileye_main.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 14 | 9 | -5 |
| Errors | 1 | 0 | -1 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 4 | 0 | -4 |
| Suppressed restarts | 0 | 2 | +2 |
| Stop timeouts | 2 | 2 | +0 |
| Force-kills | 1 | 0 | -1 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

