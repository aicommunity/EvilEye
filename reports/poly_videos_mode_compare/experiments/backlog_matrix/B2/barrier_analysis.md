# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/experiments/backlog_matrix/B2/logs/poly-videos_opencv_process_run01.log` | process | 150.0 | 2.127 | 34 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/backlog_matrix/B2/logs/poly-videos_opencv_process_run02.log` | process | 105.56 | 2.167 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/experiments/backlog_matrix/B2/logs/poly-videos_opencv_process_run03.log` | process | 111.11 | 2.118 | 31 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| opencv | process | 3 | 122.223 | 2.137 | 32.667 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| opencv | process | 32.667 | 16.463 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
