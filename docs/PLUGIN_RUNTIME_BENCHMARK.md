# Plugin runtime overhead microbenchmark

This benchmark isolates the per-item runtime from model inference. It compares a
single direct `process_item` call with the same external plugin running through
EvilEye's thread and spawn-process adapters. The process case declares
`accepts_frame_handle`, so the 1080p image uses the shared-frame path rather than
being pickled as part of the input item.

Run it from an EvilEye environment with the example package installed:

```bash
python scripts/benchmark_plugin_runtime_overhead.py \
  --module-id example/add-label --count 200 --warmup 20 \
  --width 1920 --height 1080 --out /tmp/plugin-runtime.json
```

The benchmark performs one request at a time, times from enqueue through returned
result, and verifies that the original frame and metadata are restored. It
includes queue handoff, frame transport and IPC in the measured adapter latency.
It excludes frame allocation, model inference, pipeline scheduling and concurrent
workers. Its throughput number is sequential round-trip rate; it is not an
end-to-end pipeline FPS result.

## Server result, 2026-10-13

Three 1920×1080 runs on Python 3.10.12 used 120–200 measured items after 10–20
warm-up items. The observed ranges were:

| Path | p50 round-trip | p95 round-trip |
| --- | ---: | ---: |
| Direct `process_item` call | 0.0012–0.0014 ms | 0.0022–0.0026 ms |
| Plugin thread adapter | 0.607–0.634 ms | 0.681–0.692 ms |
| Plugin spawn-process adapter | 6.316–6.778 ms | 7.053–7.920 ms |

A 640×480 run measured 2.156 ms p50 and 2.725 ms p95 for process mode, versus
0.613 ms p50 and 0.685 ms p95 for thread mode. Process transport cost increases
with frame size because the shared-frame path still copies image data into its
shared buffer. This is a useful per-module cost estimate, but it does not predict
a full pipeline: stages can overlap, inference and output size vary, and the
benchmark has only one worker and one in-flight item.

At 1080p, one process-mode round-trip consumes about 20% of a 30 FPS frame budget
at p50 and 24% at p95. Several such serial stages would need to be measured in
the actual configuration. The current result supports choosing thread mode for
lightweight modules unless process isolation is needed; process mode remains
appropriate where isolation or CPU parallelism offsets transport overhead.

## Interpretation and next gate

The result measures current SPI runtime cost, not regression against the old
module-specific workers. A fair migration comparison still requires the same
source frames, model weights, tracker settings, host load and target configuration
on the legacy and SPI paths. The production acceptance gate must specify target
FPS, maximum p95 latency, allowed queue drops and alarm completeness before a
full workload run is considered passing.
