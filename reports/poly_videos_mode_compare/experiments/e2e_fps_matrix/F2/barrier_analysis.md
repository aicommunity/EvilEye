# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F2/logs/poly-videos_opencv_process_run01.log` | process | 131.58 | 2.165 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F2/logs/poly-videos_opencv_process_run02.log` | process | 136.84 | 2.176 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F2/logs/poly-videos_opencv_process_run03.log` | process | 121.05 | 2.134 | 32 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| opencv | process | 3 | 129.823 | 2.158 | 32.667 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| opencv | process | 32.667 | 16.613 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
