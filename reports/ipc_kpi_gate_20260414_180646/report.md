# IPC KPI Gate Report

- Started at: `2026-04-14T18:06:46`
- Reports dir: `reports/ipc_kpi_gate_20260414_180646`

## Thresholds
- `max_errors`: `0`
- `max_tracebacks`: `0`
- `max_stop_timeouts`: `0`
- `max_force_kills`: `0`
- `max_restarts`: `20`
- `max_p95_pipeline_ms`: `350.0`
- `max_rss_mb`: `4096.0`
- `min_pipeline_samples`: `1`
- `timeout_sec`: `45`

## Results

| Config | Exit | Timeout | Warnings | Errors | Tracebacks | Restarts | Stop timeouts | Force-kills | p95 ms | Est. Hz | Avg FPS | Max RSS MB | Pipeline samples | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| configs/single_video_multiprocess.json | 124 | yes | 5 | 0 | 0 | 0 | 0 | 0 | 286.000 | 3.497 | 0.000 | 0.000 | 8 | PASS |
| configs/poly-videos-gst.json | 124 | yes | 8 | 0 | 0 | 0 | 0 | 0 | 51.800 | 19.305 | 0.000 | 209.202 | 25 | PASS |

## Gate Verdict
- Status: PASS


