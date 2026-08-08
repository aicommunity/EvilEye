from evileye.capture.video_capture_base import CaptureDeviceType, VideoCaptureBase


class _HintCapture(VideoCaptureBase):
    def init_impl(self):
        return True

    def get_frames_impl(self):
        return []

    def _grab_frames(self):
        pass

    def _retrieve_frames(self):
        pass

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def start_impl(self):
        pass

    def stop_impl(self):
        pass


def _ip_cam(url: str = "rtsp://10.245.1.200") -> _HintCapture:
    cap = _HintCapture()
    cap.source_type = CaptureDeviceType.IpCamera
    cap.source_address = url
    cap.username = "user"
    cap.password = "pass"
    return cap


def test_rtsp_hint_suppressed_for_filesystem_nameerror():
    cap = _ip_cam()
    err = NameError("name '_RecordingFilesystemError' is not defined")
    assert cap.get_ip_camera_init_hint(err) == ""


def test_rtsp_hint_suppressed_for_pipeline_wrapped_fs_error():
    cap = _ip_cam()
    err = RuntimeError(
        "All pipeline candidates failed. Last error: name "
        "'_RecordingFilesystemError' is not defined"
    )
    assert cap.get_ip_camera_init_hint(err) == ""


def test_rtsp_hint_kept_for_real_pipeline_connect_error():
    cap = _ip_cam()
    err = RuntimeError("GStreamer pipeline timeout connecting to rtsp source")
    hint = cap.get_ip_camera_init_hint(err)
    assert "incomplete" in hint.lower() or "stream path" in hint.lower()


def test_rtsp_hint_without_error_still_reports_incomplete_url():
    cap = _ip_cam()
    hint = cap.get_ip_camera_init_hint()
    assert "incomplete" in hint.lower()
