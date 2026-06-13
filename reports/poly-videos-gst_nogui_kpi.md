# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_nogui_120s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_nogui_120s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 6 | 4 | -2 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 20 | +20 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 63.600 | 45.400 | -18.200 |
| Estimated pipeline Hz | 15.723 | 22.026 | +6.303 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 209.218 | 5.617 | -203.601 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
