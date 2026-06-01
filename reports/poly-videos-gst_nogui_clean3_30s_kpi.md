# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_nogui_clean3_30s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_nogui_clean3_30s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 3 | 3 | +0 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 15 | +15 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 59.000 | 37.000 | -22.000 |
| Estimated pipeline Hz | 16.949 | 27.027 | +10.078 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 209.282 | 5.461 | -203.821 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
