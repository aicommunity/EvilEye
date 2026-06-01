# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_process_run01.log` | process | 164.0 | 2.279 | 31 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_process_run02.log` | process | 157.69 | 2.095 | 32 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_process_run03.log` | process | 180.0 | 2.065 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_process_run04.log` | process | 160.71 | 2.134 | 31 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_process_run05.log` | process | 175.0 | 2.251 | 27 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_thread_run01.log` | thread | 200.0 | 550.0 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_thread_run02.log` | thread | 200.0 | 577.0 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_thread_run03.log` | thread | 200.0 | 485.0 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_thread_run04.log` | thread | 200.0 | 563.0 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_gst_thread_run05.log` | thread | 200.0 | 461.0 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_process_run01.log` | process | 105.0 | 2.202 | 29 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_process_run02.log` | process | 120.0 | 2.167 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_process_run03.log` | process | 115.0 | 2.179 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_process_run04.log` | process | 130.0 | 2.238 | 28 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_process_run05.log` | process | 120.0 | 2.183 | 38 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_thread_run01.log` | thread | 157.14 | 2.88 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_thread_run02.log` | thread | 128.57 | 2.803 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_thread_run03.log` | thread | 146.43 | 2.799 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_thread_run04.log` | thread | 125.0 | 2.833 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/phase3_final/logs/poly-videos_opencv_thread_run05.log` | thread | 117.86 | 2.848 | 0 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| gst | process | 5 | 167.48 | 2.165 | 30.8 | 0 |
| gst | thread | 5 | 200.0 | 527.2 | 0.0 | 0 |
| opencv | process | 5 | 118.0 | 2.194 | 31.0 | 0 |
| opencv | thread | 5 | 135.0 | 2.833 | 0.0 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| gst | process | 30.8 | 9.544 |
| opencv | process | 31.0 | 16.47 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
