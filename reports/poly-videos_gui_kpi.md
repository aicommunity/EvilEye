# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos_baseline_gui_120s.log`
- Candidate log: `logs/diagnostics/poly-videos_mp_gui_120s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 5 | 5 | +0 |
| Errors | 5 | 0 | -5 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 20 | +20 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 52.400 | 55.400 | +3.000 |
| Estimated pipeline Hz | 19.084 | 18.051 | -1.033 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 16.688 | 5.785 | -10.903 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
