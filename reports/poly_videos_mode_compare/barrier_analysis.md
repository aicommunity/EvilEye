# MP barrier analysis (poly-videos logs)

## Per-log metrics

| log | mode | pct_trk_len0 | lag_ratio | pending_max | drops | tracebacks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_process_run01.log` | process | 158.62 | 1.851 | 32 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_process_run02.log` | process | 141.38 | 2.149 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_process_run03.log` | process | 167.86 | 2.12 | 33 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_process_run04.log` | process | 160.71 | 2.036 | 32 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_process_run05.log` | process | 146.43 | 2.058 | 29 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_thread_run01.log` | thread | 166.67 | 7.937 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_thread_run02.log` | thread | 166.67 | 7.559 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_thread_run03.log` | thread | 154.55 | 7.672 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_thread_run04.log` | thread | 183.33 | 7.976 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_gst_thread_run05.log` | thread | 150.0 | 7.567 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_process_run01.log` | process | 117.39 | 2.139 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_process_run02.log` | process | 121.74 | 2.214 | 28 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_process_run03.log` | process | 127.27 | 2.139 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_process_run04.log` | process | 117.39 | 2.173 | 29 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_process_run05.log` | process | 122.73 | 2.224 | 30 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_thread_run01.log` | thread | 146.43 | 2.846 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_thread_run02.log` | thread | 139.29 | 2.845 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_thread_run03.log` | thread | 150.0 | 2.801 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_thread_run04.log` | thread | 135.71 | 2.795 | 0 | 0 | 0 |
| `reports/poly_videos_mode_compare/logs/poly-videos_opencv_thread_run05.log` | thread | 146.43 | 2.823 | 0 | 0 | 0 |

## Aggregated by capture + mode

| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | pending_max mean | drops sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| gst | process | 5 | 155.0 | 2.043 | 31.8 | 0 |
| gst | thread | 5 | 164.244 | 7.742 | 0.0 | 0 |
| opencv | process | 5 | 121.304 | 2.178 | 29.4 | 0 |
| opencv | thread | 5 | 143.572 | 2.822 | 0.0 | 0 |

## Backlog (MpBarrier)

| capture | mode | pending_max mean | pending_mean mean |
| --- | --- | ---: | ---: |
| gst | process | 31.8 | 11.752 |
| opencv | process | 29.4 | 16.21 |

## Interpretation

- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.
- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.
