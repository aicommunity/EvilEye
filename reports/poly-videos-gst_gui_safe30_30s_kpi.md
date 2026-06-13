# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_gui_safe30_30s.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_safe30_gui_30s.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 4 | 4 | +0 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 0 | +0 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 82.900 | 0.000 | -82.900 |
| Estimated pipeline Hz | 12.063 | 0.000 | -12.063 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 221.354 | 17.212 | -204.142 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: FAIL
- Reasons:
  - pipeline_samples=0 < 1
