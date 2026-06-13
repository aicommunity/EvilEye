# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_gui_60s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_gui_60s_retry.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 6 | 5 | -1 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 0 | +0 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 76.400 | 44.400 | -32.000 |
| Estimated pipeline Hz | 13.089 | 22.523 | +9.434 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 221.378 | 5.781 | -215.597 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
