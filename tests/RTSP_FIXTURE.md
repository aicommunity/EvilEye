# Local RTSP fixture for capture tests

The capture integration suite uses a local MediaMTX server and an FFmpeg H.264 publisher. The fixture binds its RTSP listener to loopback and a dynamically selected port. It disables MediaMTX's RTMP, HLS, WebRTC, SRT, and MoQ listeners, so it does not require those ports or generate TLS artifacts in the repository.

Tests do not download or install MediaMTX. Provision a matching executable and either put it on `PATH` as `mediamtx` or set `EVILEYE_TEST_RTSP_SERVER_BIN` to its absolute path. The test environment also needs `ffmpeg`, `ffprobe`, and an FFmpeg build with the `libx264` encoder. Missing test dependencies cause the fixture to skip with a reason.

For Linux x86_64, the fixture has been verified with MediaMTX v1.21.0. The SHA-256 from the release's `checksums.sha256` for `mediamtx_v1.21.0_linux_amd64.tar.gz` is:

```text
e02e34c3337a35f20ac9e5aa31524566108964e6e37dbc46cf8292169f6c792b
```

Download the matching archive and its checksum file from the [MediaMTX v1.21.0 release](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.0), verify the archive against the published checksum, and extract the `mediamtx` executable. For example:

```bash
sha256sum mediamtx_v1.21.0_linux_amd64.tar.gz
# Compare the output with the SHA-256 above.
tar -xzf mediamtx_v1.21.0_linux_amd64.tar.gz mediamtx
export EVILEYE_TEST_RTSP_SERVER_BIN="$PWD/mediamtx"
```

Run the source contract tests with:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/integration/capture/test_local_rtsp_sources.py
```

The test exercises the built-in OpenCV and GStreamer sources in thread and process modes. Existing capture-and-record RTSP tests can be run separately:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q \
  tests/integration/capture/opencv/test_capture_variants.py -k IpCamera \
  tests/integration/capture/gstreamer/test_capture_variants.py -k IpCamera
```

These tests only use the generated local stream; they do not read camera credentials or connect to configured cameras.
