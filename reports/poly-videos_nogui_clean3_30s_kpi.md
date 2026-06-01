# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos_baseline_nogui_clean3_30s.log`
- Candidate log: `logs/diagnostics/poly-videos_mp_nogui_clean3_30s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 4 | 4 | +0 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 20 | +20 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 35.000 | 46.100 | +11.100 |
| Estimated pipeline Hz | 28.571 | 21.692 | -6.879 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 4.626 | 5.467 | +0.840 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
