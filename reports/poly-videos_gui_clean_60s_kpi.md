# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos_baseline_gui_clean_60s.log`
- Candidate log: `logs/diagnostics/poly-videos_mp_gui_clean_60s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 4 | 7 | +3 |
| Errors | 8 | 0 | -8 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 8 | +8 |
| Stop timeouts | 0 | 2 | +2 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 52.100 | 35.900 | -16.200 |
| Estimated pipeline Hz | 19.194 | 27.855 | +8.661 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 15.624 | 5.807 | -9.816 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: FAIL
- Reasons:
  - stop_timeouts=2 > 0
