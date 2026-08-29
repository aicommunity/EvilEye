import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import multiprocessing as _mp

_MP_SPAWN_CHILD = _mp.parent_process() is not None

if _MP_SPAWN_CHILD:
    from evileye.core.gstreamer_runtime import ensure_gstreamer_spawn_runtime

    ensure_gstreamer_spawn_runtime()

if not _MP_SPAWN_CHILD:
    try:
        from PyQt6 import QtCore
        from PyQt6.QtWidgets import QApplication

        pyqt_version = 6
    except ImportError:
        from PyQt5 import QtCore
        from PyQt5.QtWidgets import QApplication

        pyqt_version = 5

    from evileye.core.logging_config import setup_evileye_logging, log_system_info
    from evileye.api.core.runtime_registry import allocate_pipeline_id, mark_runtime_stopped, register_runtime, \
        update_runtime_snapshot
    from evileye.core.mp_session_registry import cleanup_stale_sessions
    from evileye.core.mp_context import ensure_spawn_start_method
else:
    pyqt_version = None
    QtCore = None
    QApplication = None

    def ensure_spawn_start_method():
        from evileye.core.mp_context import ensure_spawn_start_method as _ensure

        return _ensure()


def create_args_parser():
    pars = argparse.ArgumentParser()
    pars.add_argument('--config', nargs='?', const="1", type=str,
                      help="system configuration")
    pars.add_argument('--video', type=str, default=None,
                      help="Video file path; uses default single_video config with patched source")
    pars.add_argument('--gui', action=argparse.BooleanOptionalAction, default=True,
                      help="Show gui when processing")
    pars.add_argument('--autoclose', action=argparse.BooleanOptionalAction, default=False,
                      help="Automatic close application when video ends")
    pars.add_argument('--sources_preset', nargs='?', const="", type=str,
                      help="Use preset for multiple video sources")
    # Recording is configured only via config file; no CLI overrides
    pars.add_argument('--log-level', type=str, default="INFO",
                      help="Log level: DEBUG, INFO, WARNING, ERROR")

    result = pars.parse_args()
    return result


def _config_path_for_video(video_path: str, logger) -> str:
    """Build a temp config from default single_video template with the given video path."""
    video = Path(video_path).resolve()
    if not video.is_file():
        logger.error("Video file not found: %s", video)
        sys.exit(1)
    candidates = [
        Path("configs/single_video.json"),
        Path(__file__).resolve().parent.parent / "configs/single_video.json",
        Path(__file__).resolve().parent / "samples_configs/single_video.json",
    ]
    template = next((p for p in candidates if p.is_file()), None)
    if template is None:
        logger.error("Default single_video.json template not found for --video mode")
        sys.exit(1)
    with open(template, encoding="utf-8") as f:
        cfg = json.load(f)
    sources = cfg.get("pipeline", {}).get("sources", [])
    if sources:
        sources[0]["camera"] = str(video)
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="evileye_video_")
    os.close(fd)
    tmp_path = Path(tmp)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    logger.info("Using generated config for --video: %s", tmp_path)
    return str(tmp_path)


def run_config(config_path: str, gui: bool = True, autoclose: bool = False) -> int:
    from evileye.run_config_helper import run_config as _run
    return _run(config_path=config_path, gui=gui, autoclose=autoclose)


def main():
    """Main entry point for the EvilEye process application"""
    ensure_spawn_start_method()
    args = create_args_parser()
    os.environ.setdefault("EVILEYE_SITE_DIR", str(Path.cwd().resolve()))
    # Инициализация логирования после парсинга аргументов
    logger = setup_evileye_logging(log_level=args.log_level.upper(), log_to_console=True, log_to_file=True)
    os.environ.setdefault("EVILEYE_SESSION_ID", uuid.uuid4().hex)
    try:
        cleaned = cleanup_stale_sessions()
        if cleaned:
            logger.info("Startup MP cleanup: terminated %d stale worker process(es)", cleaned)
    except Exception:
        pass

    logger.info(f"Starting system with CLI arguments: {args}")
    log_system_info(logger)

    config_path = args.config
    if config_path is None and args.video:
        config_path = _config_path_for_video(args.video, logger)
    if config_path is None:
        logger.error("Configuration file not specified (use --config or --video)")
        sys.exit(1)

    pipeline_id = os.environ.get("EVILEYE_PIPELINE_ID")
    if not pipeline_id:
        pipeline_id = str(allocate_pipeline_id())
        os.environ["EVILEYE_PIPELINE_ID"] = pipeline_id

    config_path = str(Path(config_path).resolve())
    config_name = Path(config_path).stem

    register_runtime(
        rid=int(pipeline_id),
        pid=os.getpid(),
        config_path=config_path,
        name=os.environ.get("EVILEYE_PIPELINE_NAME") or config_name,
        frame_dir=None,
        source="process",
        managed=os.environ.get("EVILEYE_MANAGED_RUN") == "1",
        state="starting",
        log_session_id=(os.environ.get("EVILEYE_LOG_SESSION_ID") or "").strip() or None,
    )
    update_runtime_snapshot(
        int(pipeline_id),
        pid=os.getpid(),
        config_path=config_path,
        state="starting",
        server_identity={
            "managed": os.environ.get("EVILEYE_MANAGED_RUN") == "1",
        },
    )

    try:
        ret = run_config(args.config, gui=args.gui, autoclose=args.autoclose)
    except Exception as exc:
        update_runtime_snapshot(int(pipeline_id), state="error", error=str(exc))
        mark_runtime_stopped(int(pipeline_id), error=str(exc))
        raise
    else:
        update_runtime_snapshot(int(pipeline_id), state="stopped")
        mark_runtime_stopped(int(pipeline_id))
        sys.exit(ret)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
