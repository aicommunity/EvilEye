# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos_baseline_nogui_clean_60s.log`
- Candidate log: `logs/diagnostics/poly-videos_mp_nogui_clean_60s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 4 | 6 | +2 |
| Errors | 7 | 0 | -7 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 15 | +15 |
| Stop timeouts | 0 | 2 | +2 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 48.400 | 39.400 | -9.000 |
| Estimated pipeline Hz | 20.661 | 25.381 | +4.720 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 4.625 | 5.470 | +0.845 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: FAIL
- Reasons:
  - stop_timeouts=2 > 0
