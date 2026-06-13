# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos_baseline_nogui_120s.log`
- Candidate log: `logs/diagnostics/poly-videos_mp_nogui_120s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 5 | 6 | +1 |
| Errors | 3 | 0 | -3 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 20 | +20 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 62.200 | 98.500 | +36.300 |
| Estimated pipeline Hz | 16.077 | 10.152 | -5.925 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 4.615 | 5.447 | +0.832 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
