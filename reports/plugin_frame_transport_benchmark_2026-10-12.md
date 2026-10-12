# Plugin process frame transport benchmark — 2026-10-12

## Purpose

Measure the added cost of the new plugin process runtime on the tracker hot path, then compare it with the pre-plugin shared-memory tracker path. This isolates tracking and IPC; detector inference is computed once and excluded from each tracker measurement.

## Setup

- Clip: tests/data/videos/!del_139932-video_trim.mp4, first 60 frames, 3840×2160 BGR.
- YOLOv8n, imgsz=640, conf=0.4, classes [0, 1, 24, 25, 63, 66, 67]; 51 detections total. Inference took 2.83 s and is excluded.
- BoT-SORT used identical detections and frames in both modes, with ReID and GMC disabled to focus on IPC/runtime overhead.
- One item was in flight at a time. Steady FPS uses frames 11–60. Latency percentiles include all 60 replies.
- The pre-change figures below are from the immediately preceding run on the same host, clip, and detections.

## Results

| Path | Steady FPS | p50 round-trip | p95 round-trip |
|---|---:|---:|---:|
| Previous generic process adapter, pickling the full frame in and back out | 5.06 | 209.0 ms | 231.6 ms |
| Current generic plugin adapter, shared-frame descriptor | **27.13** | **37.7 ms** | **40.0 ms** |
| Previous tracker-specific shared-memory worker | 25.09 | 36.2 ms | 41.1 ms |
| Current plugin adapter, thread mode | 802.66 | 1.19 ms | 1.26 ms |

The descriptor path improved process-mode steady throughput by about **5.4×** and reduced p50 latency by about **82%** compared with the full-frame pickle path. It is now close to the tracker-specific shared-memory path: +1.5 ms at p50 and -1.1 ms at p95 in this run.

Thread and process modes returned identical rounded track signatures (SHA-256 48682f7ce90e18e52e92cae837250053ab9eaf930f569ec38fb7d435c8053d69): 46 track rows and one track ID from the same 51 detections. Neither mode dropped inputs or entered a degraded state, and process mode returned the original parent-side Frame object.

## Change made

Modules declaring the accepts_frame_handle capability now receive a lightweight Frame descriptor in process mode. The runtime copies image pixels once into shared memory, serializes only the descriptor and non-image input data, and reconnects returned frame descriptors to the parent-side Frame. The parent releases each owned segment on result, input eviction/rejection, worker error, and shutdown. Modules without this capability keep the existing serialized-item contract.

A focused test checks descriptor consumption, original-frame identity, and that the serialized input is less than 1% of the 720p image payload. Existing BoT-SORT process/thread contract tests also pass.

## Limits

This is a single 4K clip and serial one-item-in-flight measurement, not a saturated queue/load test or camera/network benchmark. It isolates the transport effect with ReID and GMC off; it does not establish tracking quality against ground truth. Small differences from the old tracker-specific path are within the expected run-to-run noise for this setup.
