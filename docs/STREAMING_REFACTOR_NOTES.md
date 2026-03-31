# Streaming Refactor Notes

## Current Preview Path
- `Controller` submits the latest processed frame to `StreamingService`.
- `StreamingService` keeps only the freshest pending frame per pipeline.
- `JpegEncoderBackend` turns raw `BGR ndarray` into `JPEG bytes`.
- `FrameBroker` stores the latest payload and metadata.
- `snapshot`/`stream.mjpg` continue to consume `image/jpeg`.

## Future GStreamer Encoded Path
The current codebase does not expose a reusable encoded packet path for preview streaming.

To avoid JPEG re-encode, the viable future design is:
1. Add a second `tee` branch in the GStreamer capture path before decode/appsink.
2. Publish encoded H264/H265 access units or fragmented MP4 from that branch.
3. Add a new broker channel for encoded payloads instead of overloading the MJPEG broker.
4. Expose a browser-compatible transport such as `MSE/fMP4`, `HLS`, or `WebRTC`.

Constraints:
- OpenCV capture cannot support this cleanly because it only exposes decoded raw frames.
- Existing recording paths mostly re-encode from raw frames, so they are not a drop-in source for live preview.
- The current HTTP preview API is MJPEG-specific and should remain unchanged during the first refactor stage.

## Perf And Regression Checklist
- Measure `publish_ms` before and after the refactor in controller perf logs.
- Compare controller loop latency with:
  - no preview consumers,
  - one MJPEG consumer,
  - multiple MJPEG consumers.
- Verify CPU usage while preview streaming is active.
- Verify preview freshness under load: only the newest frame should be published when encode lags.
- Verify all transport modes:
  - in-process broker,
  - `server.execution_mode == "process"`,
  - `ConfigRunManager` file-based IPC.
- Verify fallback behavior:
  - `TurboJPEG` unavailable -> OpenCV encoder is used,
  - preview disabled/no consumers -> no unnecessary encode work.
