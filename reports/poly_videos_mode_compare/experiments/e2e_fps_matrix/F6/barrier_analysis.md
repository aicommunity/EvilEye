# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F6/logs/poly-videos_opencv_process_run01.log` | process | 131.58 | 2.175 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F6/logs/poly-videos_opencv_process_run02.log` | process | 121.05 | 2.159 | 32 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/F6/logs/poly-videos_opencv_process_run03.log` | process | 131.58 | 2.215 | 31 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| opencv | process | 3 | 128.07 | 2.183 | 32.0 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| opencv | process | 32.0 | 16.527 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
