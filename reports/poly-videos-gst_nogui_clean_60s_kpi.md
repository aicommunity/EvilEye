# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_nogui_clean_60s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_nogui_clean_60s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 5 | 7 | +2 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 13 | +13 |
| Stop timeouts | 0 | 1 | +1 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 75.000 | 64.200 | -10.800 |
| Estimated pipeline Hz | 13.333 | 15.576 | +2.243 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 217.789 | 5.460 | -212.330 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: FAIL
- Reasons:
  - stop_timeouts=1 > 0
