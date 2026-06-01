# IPC KPI Comparison

- Baseline log: `logs/diagnostics/poly-videos-gst_baseline_gui_fixcheck_bench45.log`
- Candidate log: `logs/diagnostics/poly-videos-gst_mp_safe30_gui_fixcheck_bench45.log`

| KPI | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Warnings | 3 | 3 | +0 |
| Errors | 0 | 0 | +0 |
| Tracebacks | 0 | 0 | +0 |
| Worker restarts | 0 | 0 | +0 |
| Suppressed restarts | 0 | 0 | +0 |
| Stop timeouts | 0 | 0 | +0 |
| Force-kills | 0 | 0 | +0 |
| p95 Pipeline loop (ms) | 103.700 | 46.000 | -57.700 |
| Estimated pipeline Hz | 9.643 | 21.739 | +12.096 |
| Average capture FPS | 0.000 | 0.000 | +0.000 |
| Max RSS (MB) | 230.527 | 17.206 | -213.321 |

## Notes
- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.
- `Suppressed restarts` indicates graceful policy behavior and is informational.

## KPI Gate
- Status: PASS
