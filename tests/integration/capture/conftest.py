import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
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


def _has_gst_rtsp_server() -> bool:
    try:
        import gi  # noqa: F401
        gi.require_version('Gst', '1.0')
        gi.require_version('GstRtspServer', '1.0')
        from gi.repository import GstRtspServer  # noqa: F401
        return True
    except Exception:
        return False


def _ensure_rtsp_simple_server_binary() -> Path | None:
    """
    Возвращает путь к исполняемому файлу rtsp-simple-server.
    Если бинарника нет, пытается скачать его в системный временный каталог.
    """
    existing = shutil.which("rtsp-simple-server")
    if existing:
        return Path(existing)

    cache_dir = Path(tempfile.gettempdir()) / "rtsp_simple_server_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    binary_path = cache_dir / "rtsp-simple-server"
    if binary_path.exists():
        binary_path.chmod(0o755)
        return binary_path

    url = "https://github.com/aler9/rtsp-simple-server/releases/download/v0.22.3/rtsp-simple-server_v0.22.3_linux_amd64.tar.gz"
    archive_path = cache_dir / "rtsp-simple-server.tar.gz"
    try:
        urllib.request.urlretrieve(url, archive_path)
    except Exception:
        return None

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith("/rtsp-simple-server"):
                    member.name = Path(member.name).name  # strip path
                    tar.extract(member, cache_dir)
                    extracted = cache_dir / member.name
                    extracted.chmod(0o755)
                    binary_path = extracted
                    break
        if not binary_path.exists():
            return None
        return binary_path
    finally:
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)
    return None


def _probe_rtsp_stream(url: str) -> bool:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return True
    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-rtsp_transport",
                "tcp",
                "-timeout",
                "2000000",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1",
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
def local_rtsp_server(ensure_gst_initialized):
    """
    Поднимает локальный RTSP-сервер на 127.0.0.1:8554/test.
    Сначала пытаемся использовать GstRtspServer напрямую, при отсутствии — пробуем rtsp-simple-server+ffmpeg.
    """
    # Попытка 1: rtsp-simple-server (+ ffmpeg) — более надёжная для CI
    simple_server_bin = _ensure_rtsp_simple_server_binary()
    ffmpeg_bin = shutil.which("ffmpeg")
    if simple_server_bin and ffmpeg_bin:
        print("Using rtsp-simple-server fallback for RTSP fixture")
        server_proc = subprocess.Popen([str(simple_server_bin)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Дождаться старта порта
        end_time = time.time() + 5.0
        while time.time() < end_time:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", 8554)) == 0:
                    break
            if server_proc.poll() is not None:
                stdout, stderr = server_proc.communicate(timeout=1)
                pytest.skip(f"rtsp-simple-server не запустился: {stderr.decode(errors='ignore')}")
            time.sleep(0.1)
        else:
            server_proc.terminate()
            pytest.skip("rtsp-simple-server не открыл порт 8554")

        stream_url = "rtsp://127.0.0.1:8554/test"
        ffmpeg_cmd = [
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
            stream_url,
        ]
        stream_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1.0)
        if stream_proc.poll() is not None:
            stdout, stderr = stream_proc.communicate(timeout=1)
            server_proc.terminate()
            pytest.skip(f"ffmpeg не смог запустить RTSP поток: {stderr.decode(errors='ignore')}")
        if not _probe_rtsp_stream(stream_url):
            for proc in (stream_proc, server_proc):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            pytest.skip("RTSP поток через rtsp-simple-server не отвечает на ffprobe")

        try:
            yield stream_url
        finally:
            for proc in (stream_proc, server_proc):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        return

    # Попытка 2: GstRtspServer через gi
    if _has_gst_rtsp_server():
        import gi
        gi.require_version('Gst', '1.0')
        gi.require_version('GstRtspServer', '1.0')
        from gi.repository import Gst, GstRtspServer, GLib

        print("Using GstRtspServer for RTSP fixture")
        loop = GLib.MainLoop()
        server = GstRtspServer.RTSPServer.new()
        server.props.service = "8554"
        server.props.address = "127.0.0.1"
        mount_points = server.get_mount_points()
        factory = GstRtspServer.RTSPMediaFactory.new()
        factory.set_shared(True)
        factory.set_launch(
            "( videotestsrc is-live=true ! x264enc tune=zerolatency speed-preset=ultrafast bitrate=512 key-int-max=15 "
            "! rtph264pay name=pay0 pt=96 )"
        )
        mount_points.add_factory("/test", factory)
        server.attach(None)

        import threading
        t = threading.Thread(target=loop.run, daemon=True)
        t.start()
        # Дать серверу стартовать, проверяя порт
        import socket
        end_time = time.time() + 5.0
        while time.time() < end_time:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", 8554)) == 0:
                    break
            time.sleep(0.1)
        else:
            loop.quit()
            pytest.skip("GstRtspServer не открыл порт 8554")
        url = "rtsp://127.0.0.1:8554/test"
        if not _probe_rtsp_stream(url):
            try:
                loop.quit()
            except Exception:
                pass
            pytest.skip("GstRtspServer не смог предоставить поток (ffprobe)")
        try:
            yield url
        finally:
            try:
                loop.quit()
            except Exception:
                pass
        return

    pytest.skip("Нет подходящего способа запустить локальный RTSP сервер (ни GstRtspServer, ни rtsp-simple-server)")


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


