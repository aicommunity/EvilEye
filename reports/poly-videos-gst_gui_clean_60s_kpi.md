# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_gui_clean_60s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_gui_clean_60s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 4 | 3 | -1 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 15 | +15 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 81.800 | 36.000 | -45.800 |
| Estimated pipeline Hz | 12.225 | 27.778 | +15.553 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 229.763 | 5.802 | -223.961 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
