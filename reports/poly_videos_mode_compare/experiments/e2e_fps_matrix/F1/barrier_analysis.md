# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F1/logs/poly-videos_opencv_process_run01.log` | process | 125.0 | 2.147 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F1/logs/poly-videos_opencv_process_run02.log` | process | 121.05 | 2.153 | 35 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F1/logs/poly-videos_opencv_process_run03.log` | process | 120.0 | 2.196 | 38 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| opencv | process | 3 | 122.017 | 2.165 | 34.333 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| opencv | process | 34.333 | 16.703 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
