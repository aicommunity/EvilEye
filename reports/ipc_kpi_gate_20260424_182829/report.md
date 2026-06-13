# IPC KPI Gate Report

- Started at: `2026-04-24T18:28:29`
- Reports dir: `reports/ipc_kpi_gate_20260424_182829`

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
| configs/single_video_multiprocess.json | 0 | no | 4 | 0 | 0 | 1 | 0 | 0 | 2.500 | 400.000 | 0.000 | 0.000 | 9 | PASS |
| configs/poly-videos-gst.json | 124 | yes | 5 | 0 | 0 | 0 | 0 | 0 | 91.400 | 10.941 | 0.000 | 217.776 | 23 | PASS |

## Gate Verdict
- Status: PASS


