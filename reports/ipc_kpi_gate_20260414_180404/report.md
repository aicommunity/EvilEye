# IPC KPI Gate Report

- Started at: `2026-04-14T18:04:04`
- Reports dir: `reports/ipc_kpi_gate_20260414_180404`

## Thresholds
- `max_errors`: `0`
- `max_tracebacks`: `0`
- `max_stop_timeouts`: `0`
- `max_force_kills`: `0`
- `max_restarts`: `20`
- `max_p95_pipeline_ms`: `200.0`
- `max_rss_mb`: `4096.0`
- `min_pipeline_samples`: `0`

## Results

| Config | Exit | Timeout | Warnings | Errors | Tracebacks | Restarts | Stop timeouts | Force-kills | p95 ms | Est. Hz | Avg FPS | Max RSS MB | Pipeline samples | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| configs/single_video_multiprocess.json | 124 | yes | 5 | 0 | 0 | 0 | 0 | 0 | 308.100 | 3.246 | 0.000 | 0.000 | 1 | FAIL |
| configs/poly-videos-gst.json | 124 | yes | 6 | 0 | 0 | 0 | 0 | 0 | 20.800 | 48.077 | 0.000 | 226.344 | 3 | PASS |

## Gate Verdict
- Status: FAIL

- `configs/single_video_multiprocess.json` failed:
  - p95_pipeline_ms=308.100 > 200.000

