import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest


def _has_opencv_ffmpeg() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def _has_gi_and_gst() -> bool:
    try:
        import gi  # noqa: F401
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst  # noqa: F401
        return True
    except Exception:
        return False


def _find_rtsp_server_binary() -> Path | None:
    """Return an explicitly provisioned MediaMTX test server binary."""
    configured = os.environ.get("EVILEYE_TEST_RTSP_SERVER_BIN")
    if configured:
        binary = Path(configured).expanduser()
        if not binary.is_file() or not os.access(binary, os.X_OK):
            pytest.fail(
                "EVILEYE_TEST_RTSP_SERVER_BIN must point to an executable MediaMTX binary"
            )
        return binary
    discovered = shutil.which("mediamtx")
    return Path(discovered) if discovered else None


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalRtspFixture:
    """Owns the RTSP server and a restartable synthetic H.264 publisher."""

    def __init__(self, url, server_proc, publisher_cmd, log_path):
        self.url = url
        self.server_proc = server_proc
        self.publisher_cmd = publisher_cmd
        self.publisher_proc = None
        self.log_path = Path(log_path)

    def start_publisher(self, *, wait_ready=True):
        self.stop_publisher()
        self.publisher_proc = subprocess.Popen(
            self.publisher_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_ready:
            return
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self.publisher_proc.poll() is not None:
                raise RuntimeError("FFmpeg RTSP publisher exited before publishing")
            if _probe_rtsp_stream(self.url):
                return
            time.sleep(0.25)
        raise RuntimeError("Synthetic RTSP stream did not become readable")

    def stop_publisher(self):
        proc = self.publisher_proc
        self.publisher_proc = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)

    def close(self):
        self.stop_publisher()
        proc = self.server_proc
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)

    def log_tail(self, limit=2000):
        try:
            return self.log_path.read_text(errors="replace")[-limit:]
        except OSError:
            return ""

def _probe_rtsp_stream(url: str) -> bool:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return False
    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-rtsp_transport",
                "tcp",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1",
                "-i",
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _gst_has(element_name: str) -> bool:
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        return Gst.ElementFactory.find(element_name) is not None
    except Exception:
        return False


@pytest.fixture(scope="session")
def ensure_gst_initialized():
    if not _has_gi_and_gst():
        pytest.skip("GStreamer (gi.repository.Gst) недоступен в окружении")
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    try:
        Gst.init(None)
    except Exception:
        pass
    yield


@pytest.fixture(scope="session")
def test_video_mp4(tmp_path_factory):
    """
    Генерирует короткое mp4-видео (3-5 секунд) для тестов.
    При наличии OpenCV/FFMPEG — кодирует через cv2.VideoWriter.
    """
    if not _has_opencv_ffmpeg():
        pytest.skip("OpenCV/FFMPEG недоступен для генерации тестового видео")
    import cv2
    import numpy as np

    tmp_dir = tmp_path_factory.mktemp("media")
    video_path = tmp_dir / "sample.mp4"
    width, height, fps, duration_sec = 320, 240, 15, 3
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        pytest.skip("Не удалось открыть VideoWriter для mp4")

    num_frames = fps * duration_sec
    for i in range(num_frames):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(img, f"frame {i}", (10, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.rectangle(img, (10 + (i % (width - 30)), 30), (30 + (i % (width - 30)), 50), (255, 0, 0), -1)
        writer.write(img)
    writer.release()
    return str(video_path)


@pytest.fixture(scope="session")
def images_sequence(tmp_path_factory, ensure_gst_initialized):
    """
    Создаёт последовательность изображений и возвращает шаблон пути frame_%03d.png.
    """
    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
    except Exception:
        pytest.skip("OpenCV/NumPy недоступны для генерации изображений")

    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst

    if Gst.ElementFactory.find("jpegdec") is None and Gst.ElementFactory.find("pngdec") is None:
        pytest.skip("Нет GStreamer-декодеров jpeg/png для ImageSequence")

    import cv2
    import numpy as np
    base = tmp_path_factory.mktemp("images_seq")
    total_frames = 180
    for i in range(total_frames):
        img = np.full((240, 320, 3), 0, dtype=np.uint8)
        cv2.putText(img, f"img {i}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 2, cv2.LINE_AA)
        cv2.circle(img, (20 + (i * 10) % 300, 60 + (i * 5) % 100), 15, (0, 255, 0), -1)
        cv2.imwrite(str(base / f"frame_{i:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return str(base / "frame_%03d.jpg")


@pytest.fixture(scope="session")
def local_rtsp_fixture(tmp_path_factory):
    """Run a local MediaMTX server with a restartable synthetic H.264 stream.

    The server is a test-only dependency. Tests never download or install it;
    configure EVILEYE_TEST_RTSP_SERVER_BIN or put ``mediamtx`` on PATH.
    """
    server_bin = _find_rtsp_server_binary()
    if server_bin is None:
        pytest.skip(
            "MediaMTX test binary is unavailable; see tests/RTSP_FIXTURE.md"
        )
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        pytest.skip("ffmpeg is required for the local RTSP fixture")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe is required to verify the local RTSP publisher")

    work_dir = tmp_path_factory.mktemp("local_rtsp")
    port = _free_tcp_port()
    config_path = work_dir / "mediamtx.yml"
    config_path.write_text(
        f"rtsp: true\n"
        f"rtspTransports: [tcp]\n"
        f"rtspAddress: 127.0.0.1:{port}\n"
        "rtmp: false\n"
        "hls: false\n"
        "webrtc: false\n"
        "srt: false\n"
        "moq: false\n"
        "paths:\n  all_others: {}\n",
        encoding="utf-8",
    )
    log_path = work_dir / "mediamtx.log"
    log_file = log_path.open("wb")
    server_proc = subprocess.Popen(
        [str(server_bin), str(config_path)],
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=work_dir,
    )
    url = f"rtsp://127.0.0.1:{port}/test"
    fixture = LocalRtspFixture(url, server_proc, [], log_path)
    try:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if server_proc.poll() is not None:
                pytest.fail(
                    "MediaMTX exited during startup: " + fixture.log_tail()
                )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            pytest.fail(
                "MediaMTX did not open its RTSP port: " + fixture.log_tail()
            )

        fixture.publisher_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-re",
            "-f", "lavfi",
            "-i", "testsrc=size=320x240:rate=15",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-g", "30",
            "-f", "rtsp",
            url,
        ]
        fixture.start_publisher()
        yield fixture
    except RuntimeError as exc:
        pytest.fail(f"Could not start synthetic RTSP publisher: {exc}; {fixture.log_tail()}")
    finally:
        fixture.close()
        log_file.close()


@pytest.fixture(scope="session")
def local_rtsp_server(local_rtsp_fixture):
    """Compatibility URL fixture for existing capture integration tests."""
    return local_rtsp_fixture.url

def skip_if_missing_gst_recording_elements():
    missing = []
    for elem in ("splitmuxsink", "x264enc", "videoconvert", "queue"):
        if not _gst_has(elem):
            missing.append(elem)
    if missing:
        pytest.skip(f"GStreamer элементы для записи отсутствуют: {missing}")


@pytest.fixture(scope="session")
def require_gst_recording_elements(ensure_gst_initialized):
    """
    Прерывает тесты, если отсутствуют элементы записи GStreamer.
    """
    missing = []
    for elem in ("splitmuxsink", "x264enc", "videoconvert", "queue"):
        if not _gst_has(elem):
            missing.append(elem)
    if missing:
        pytest.skip(f"GStreamer элементы для записи отсутствуют: {missing}")


def _detect_v4l2_device():
    base = Path("/dev")
    if not base.exists():
        return None
    for dev in sorted(base.glob("video*")):
        if os.access(dev, os.R_OK | os.W_OK):
            suffix = dev.name.replace("video", "")
            if suffix.isdigit():
                return suffix
    return None


@pytest.fixture(scope="session")
def v4l2_test_device():
    """
    Возвращает индекс V4L2-устройства для тестов. Если реального устройства нет,
    пытается создать виртуальное через v4l2loopback и подать поток с помощью GStreamer.
    """
    existing = _detect_v4l2_device()
    if existing is not None:
        yield existing
        return

    modprobe = shutil.which("modprobe")
    gst_launch = shutil.which("gst-launch-1.0")
    if not modprobe or not gst_launch:
        pytest.skip("Нет доступа к реальному V4L2 устройству и отсутствуют modprobe/gst-launch для эмуляции")

    device_nr = "20"
    load_cmd = [
        modprobe,
        "v4l2loopback",
        f"devices=1",
        f"video_nr={device_nr}",
        "card_label=EvilEyeLoopback",
        "exclusive_caps=1",
    ]
    load_result = subprocess.run(load_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if load_result.returncode != 0:
        pytest.skip(f"Не удалось загрузить v4l2loopback: {load_result.stderr.decode(errors='ignore')}")

    device_path = Path(f"/dev/video{device_nr}")
    start_time = time.time()
    while time.time() - start_time < 3.0:
        if device_path.exists():
            break
        time.sleep(0.1)
    else:
        subprocess.run(["modprobe", "-r", "v4l2loopback"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pytest.skip("v4l2loopback не создал устройство /dev/video20")

    gst_cmd = [
        gst_launch,
        "videotestsrc", "is-live=true", "pattern=ball",
        "!", "video/x-raw,format=YUY2,width=640,height=480,framerate=15/1",
        "!", "v4l2sink", f"device={device_path}", "sync=false",
    ]
    gst_proc = subprocess.Popen(gst_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.0)
    if gst_proc.poll() is not None:
        stdout, stderr = gst_proc.communicate(timeout=1)
        subprocess.run(["modprobe", "-r", "v4l2loopback"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pytest.skip(f"Не удалось запустить поток в v4l2loopback: {stderr.decode(errors='ignore')}")

    try:
        yield device_nr
    finally:
        if gst_proc.poll() is None:
            gst_proc.terminate()
            try:
                gst_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                gst_proc.kill()
        subprocess.run(["modprobe", "-r", "v4l2loopback"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def assert_recording_created(out_dir: Path):
    """
    Проверяет, что запись создала хотя бы один видеофайл в структуре директорий.
    """
    date_dirs = list(out_dir.glob("*/"))
    assert len(date_dirs) > 0, f"Не создана папка с датой записи в {out_dir}"
    files = []
    for date_dir in date_dirs:
        files.extend(list(date_dir.glob("*.mp4")))
        files.extend(list(date_dir.glob("*.mkv")))
        for camera_dir in date_dir.glob("*/"):
            files.extend(list(camera_dir.glob("*.mp4")))
            files.extend(list(camera_dir.glob("*.mkv")))
    assert len(files) >= 1, f"Файлы записи не найдены. Проверено: {out_dir}, date_dirs: {date_dirs}"


