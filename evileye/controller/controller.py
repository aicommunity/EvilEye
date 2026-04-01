import threading
import os
import importlib
import inspect
import socket
import copy
from pathlib import Path
from time import sleep

from evileye.capture import video_capture_opencv
from evileye.object_detector import object_detection_yolo
from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_tracker import object_tracking_botsort
from evileye.object_tracker.trackers.onnx_encoder import OnnxEncoder
from evileye.object_tracker.tracking_results import TrackingResultList, TrackingResult
from evileye.objects_handler import objects_handler
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList
import time
from timeit import default_timer as timer
from evileye.visualization_modules.visualizer import Visualizer
from evileye.database_controller.db_adapter_objects import DatabaseAdapterObjects
from evileye.database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from evileye.database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from evileye.database_controller.db_adapter_system_events import DatabaseAdapterSystemEvents
from evileye.database_controller.db_adapter_attribute_events import DatabaseAdapterAttributeEvents
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_fov_events import JsonAdapterFovEvents
from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
from evileye.database_controller.json_adapter_cam_events import JsonAdapterCamEvents
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_system_events import JsonAdapterSystemEvents
from evileye.events_control.events_processor import EventsProcessor
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_detectors.cam_events_detector import CamEventsDetector
from evileye.events_detectors.fov_events_detector import FieldOfViewEventsDetector
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
from evileye.events_detectors.event_system import SystemEvent
import datetime
from evileye.events_detectors.system_events_detector import SystemEventsDetector
import json
import datetime
import pprint
import copy
import math
import gc
from evileye.core import ProcessorSource, ProcessorStep, ProcessorFrame
from evileye.core.class_manager import ClassManager
from evileye.pipelines import PipelineSurveillance
from evileye.core.logger import get_module_logger
from evileye.api.core.runtime_registry import update_runtime_snapshot
from evileye.api.security import load_web_auth_config
from evileye.core.system_diagnostics import SystemDiagnostics
from evileye.core.memory_monitor import MemoryMonitor
from evileye.api.core.runtime_registry import register_runtime
from evileye.visualization_modules.preview_render import PreviewRenderContext
from evileye.controller.services import (
    PipelineService,
    DatabaseService,
    EventsService,
    VisualizationService,
    ConfigurationService,
    ObjectsHandlerService,
    ServiceLocator,
)
import os


try:
    from PyQt6.QtWidgets import QMainWindow
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QMainWindow
    pyqt_version = 5

class Controller:
    @staticmethod
    def _can_bind_embedded_server(host: str, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
            return True
        except OSError:
            return False

    def __init__(self):
        self.logger = get_module_logger("controller")
        self.main_window = None
        # self.application = application
        # Run controller loop in daemon thread so app can exit even if pipeline blocks.
        self.control_thread = threading.Thread(target=self.run, daemon=True, name="ControllerMainLoop")
        self.params = None
        self.loaded_config = dict()
        self.credentials = dict()
        self.credentials_loaded = False
        self.params_path = None
        self.database_config = dict()
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.source_last_processed_frame_id = dict()
        # Вспомогательный счётчик для диагностического логирования кадров по источникам
        self._per_source_frame_debug_counter: dict[int, int] = {}
        # Throttle ObjectsHandler updates to avoid backlog under load
        self._obj_handler_last_sent_frame_id: dict[int, int] = {}
        self._preview_active_events_by_source: dict[int, dict[tuple[int, str], dict]] = {}
        self._preview_events_lock = threading.Lock()
        self._preview_zones_by_source: dict[int, list] = {}

        self.pipeline = None

        # Web server process manager (set when server.execution_mode == "process")
        self._server_process_manager = None
        self._stream_publish_fps = 5.0

        self.obj_handler = None
        self.visualizer = None
        self.pyqt_slots = None
        self.pyqt_signals = None
        self.fps = 30
        self.show_main_gui = True
        self.show_journal = False
        self.enable_close_from_gui = True
        self.skip_objects_handler = False
        self.memory_periodic_check_sec = 60*15*60
        self.max_memory_usage_mb = 1024*16
        self.show_memory_usage = False
        self.auto_restart = True
        # DB access goes through native psycopg2 code, so configs must opt in
        # explicitly. This prevents accidental crashes in scenarios like local
        # video playback where database support is not needed.
        self.use_database = False
        # Timeout for late model loading/class mapping propagation (seconds)
        self.model_loading_timeout_sec = 60

        self.events_detectors_controller = None
        self.events_processor = None
        self.cam_events_detector = None
        self.fov_events_detector = None
        self.zone_events_detector = None
        self.attr_events_detector = None
        self.system_events_detector = None

        self.db_controller = None
        self.db_adapter_obj = None
        self.db_adapter_cam_events = None
        self.db_adapter_fov_events = None
        self.db_adapter_zone_events = None
        self.db_adapter_attr_events = None
        self.db_adapter_system_events = None
        
        self.storage_monitor = None
        
        # System diagnostics and memory monitoring
        self.system_diagnostics = None
        self.memory_monitor = None
        
        # Initialize centralized class manager
        self.class_manager = ClassManager()
        
        # Initialize service locator and services
        self.service_locator = ServiceLocator()
        self.service_locator.create_all_services(class_manager=self.class_manager)
        
        # Get service references for convenience
        self._pipeline_service = self.service_locator.get_pipeline_service()
        self._database_service = self.service_locator.get_database_service()
        self._events_service = self.service_locator.get_events_service()
        self._visualization_service = self.service_locator.get_visualization_service()
        self._config_service = self.service_locator.get_config_service()
        self._objects_handler_service = self.service_locator.get_objects_handler_service()
        self._streaming_service = self.service_locator.get_streaming_service()
        self._preview_render_service = self.service_locator.get_preview_render_service()
        
        # Default COCO class mapping: class_name -> class_id
        self.class_mapping = {
            "person": 0,
            "bicycle": 1,
            "car": 2,
            "motorcycle": 3,
            "airplane": 4,
            "bus": 5,
            "train": 6,
            "truck": 7,
            "boat": 8,
            "traffic light": 9,
            "fire hydrant": 10,
            "stop sign": 11,
            "parking meter": 12,
            "bench": 13,
            "bird": 14,
            "cat": 15,
            "dog": 16,
            "horse": 17,
            "sheep": 18,
            "cow": 19,
            "elephant": 20,
            "bear": 21,
            "zebra": 22,
            "giraffe": 23,
            "backpack": 24,
            "umbrella": 25,
            "handbag": 26,
            "tie": 27,
            "suitcase": 28,
            "frisbee": 29,
            "skis": 30,
            "snowboard": 31,
            "sports ball": 32,
            "kite": 33,
            "baseball bat": 34,
            "baseball glove": 35,
            "skateboard": 36,
            "surfboard": 37,
            "tennis racket": 38,
            "bottle": 39,
            "wine glass": 40,
            "cup": 41,
            "fork": 42,
            "knife": 43,
            "spoon": 44,
            "bowl": 45,
            "banana": 46,
            "apple": 47,
            "sandwich": 48,
            "orange": 49,
            "broccoli": 50,
            "carrot": 51,
            "hot dog": 52,
            "pizza": 53,
            "donut": 54,
            "cake": 55,
            "chair": 56,
            "couch": 57,
            "potted plant": 58,
            "bed": 59,
            "dining table": 60,
            "toilet": 61,
            "tv": 62,
            "laptop": 63,
            "mouse": 64,
            "remote": 65,
            "keyboard": 66,
            "cell phone": 67,
            "microwave": 68,
            "oven": 69,
            "toaster": 70,
            "sink": 71,
            "refrigerator": 72,
            "book": 73,
            "clock": 74,
            "vase": 75,
            "scissors": 76,
            "teddy bear": 77,
            "hair drier": 78,
            "toothbrush": 79
        }

        self.run_flag = False
        self.restart_flag = False

        self.gui_enabled = True
        self.autoclose = False
        #self.multicam_reid_enabled = False

        self.current_main_widget_size = [1920, 1080]

        self.debug_info = dict()

        self.stream_pipeline_id = os.getenv('EVILEYE_PIPELINE_ID', 'default')
        self.logger.info(f"Controller initialized with stream pipeline id: {self.stream_pipeline_id}")

        # Perf diagnostics (disabled by default). Enable with env EVILEYE_PERF_DIAG=1
        # or via config controller.perf_diag=true.
        self._perf_diag_env = os.getenv("EVILEYE_PERF_DIAG", "").strip().lower() in {"1", "true", "yes", "on"}
        self._perf_diag_every = int(os.getenv("EVILEYE_PERF_DIAG_EVERY", "60") or "60")  # log once per N loops
        self._perf_diag_loop = 0

        # Periodic resource stats (RSS/threads/fds) for leak tracking.
        try:
            self._resource_stats_every_sec = float(os.getenv("EVILEYE_RESOURCE_STATS_EVERY_SEC", "60") or "60")
        except Exception:
            self._resource_stats_every_sec = 60.0
        self._resource_stats_last_ts = 0.0

        # File-based frame sharing for Config Run mode
        self._frame_dir = os.environ.get("EVILEYE_FRAME_DIR")
        if self._frame_dir:
            from pathlib import Path as _Path
            self._frame_dir = _Path(self._frame_dir)
            self._frame_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Frame file output enabled: {self._frame_dir}")
        # Event-based recording components
        self.event_buffers = {}  # source_id -> EventBuffer
        self.event_recorders = {}  # source_id -> EventRecorder
        self.event_video_paths = {}  # event_id -> relative_video_path (for storing video paths in DB)
        self.recording_params = None  # Global recording parameters

        # VideoFile timestamp normalization for event recording.
        # current_video_position resets to ~0 on loop; EventBuffer expects monotonic timestamps.
        # Track per-source offset to keep a monotonic "video time" timeline across loops.
        # source_id -> {"offset": float, "last_pos": float | None}
        self._video_ts_state: dict[int, dict[str, float | None]] = {}
    
    # ── Frame publishing ────────────────────────────────────────────

    # ── Getters ──────────────────────────────────────────────────────

    def get_fps(self) -> int:
        return self.fps

    def get_params(self):
        return self.params

    def _publish_runtime_snapshot(self, *, state: str | None = None) -> None:
        try:
            runtime_id = int(self.stream_pipeline_id)
        except Exception:
            return
        try:
            params = copy.deepcopy(self.get_params() or {})
        except Exception:
            params = {}

        sources_payload = []
        try:
            for source in self.pipeline.get_sources() or []:
                source_ids = list(getattr(source, "source_ids", []) or [])
                source_names = list(getattr(source, "source_names", []) or [])
                source_state = {
                    "source_ids": source_ids,
                    "source_names": source_names,
                    "address": getattr(source, "source_address", None),
                    "is_inited": bool(getattr(source, "is_inited", False)),
                    "is_working": bool(getattr(source, "is_working", False)),
                }
                if source_ids or source_names:
                    sources_payload.append(source_state)
        except Exception:
            sources_payload = []

        try:
            server_cfg = params.get("server", {}) if isinstance(params, dict) else {}
            journal_context = {
                "config_path": getattr(self, "config_path", None),
                "database_enabled": bool(params.get("database")) if isinstance(params, dict) else False,
                "source_names": [name for source in sources_payload for name in source.get("source_names", [])],
            }
            update_runtime_snapshot(
                runtime_id,
                pid=os.getpid(),
                state=state or ("running" if self.run_flag else "initialized"),
                config_path=getattr(self, "config_path", None),
                config=params,
                sources=sources_payload,
                module_state={
                    "pipeline_class": self.pipeline.__class__.__name__ if self.pipeline is not None else None,
                    "detector_count": len(getattr(self.pipeline, "detectors", []) or []),
                    "tracker_count": len(getattr(self.pipeline, "trackers", []) or []),
                    "database_enabled": bool(params.get("database")) if isinstance(params, dict) else False,
                    "event_detector_names": sorted((params.get("events_detectors") or {}).keys()) if isinstance(params, dict) and isinstance(params.get("events_detectors"), dict) else [],
                },
                server_identity={
                    "managed": os.environ.get("EVILEYE_MANAGED_RUN") == "1",
                    "embedded_server_enabled": bool(server_cfg.get("enabled")) if isinstance(server_cfg, dict) else False,
                    "host": server_cfg.get("host") if isinstance(server_cfg, dict) else None,
                    "port": server_cfg.get("port") if isinstance(server_cfg, dict) else None,
                },
                journal_context=journal_context,
            )
        except Exception as exc:
            self.logger.debug("Failed to publish runtime snapshot: %s", exc)

    def system_event(self, type: str, message: str):
        if self.system_events_detector:
            self.system_events_detector.emit_message(type, message)

        self.logger.info(f"System message [{type}]: {message}")

    def add_pipeline(self, pipeline_type):
        pass

    def del_pipeline(self, pipeline_type):
        pass

    def add_processor(self, processor_name: str, processor_class: str, params: dict):
        pass

    def del_processor(self, processor_name: str, id: int):
        pass

    def is_running(self):
        return self.run_flag

    def get_restart_flag(self) -> bool:
        """Check if restart is requested (e.g., due to memory leak)."""
        return self.restart_flag

    def _get_frame_timestamp_sec(self, image) -> float:
        """Получить timestamp кадра в секундах (для записи событий)."""
        try:
            # Для видеофайлов используем current_video_position (мс) для точных интервалов
            # Frame инициализирует current_video_position в __init__, поэтому прямой доступ безопасен
            if image.current_video_position is not None and image.current_video_position >= 0:
                cur = float(image.current_video_position) / 1000.0
                # Normalize to monotonic timeline across loop_play resets
                try:
                    sid = getattr(image, "source_id", None)
                    if isinstance(sid, int):
                        st = self._video_ts_state.get(sid)
                        if st is None:
                            st = {"offset": 0.0, "last_pos": None}
                            self._video_ts_state[sid] = st
                        last_pos = st.get("last_pos")
                        offset = float(st.get("offset") or 0.0)
                        # Detect wrap/reset (position went backwards noticeably)
                        if isinstance(last_pos, (int, float)) and (cur + 0.25) < float(last_pos):
                            # Add previous position as a segment length approximation
                            offset += float(last_pos)
                            st["offset"] = offset
                        st["last_pos"] = cur
                        return offset + cur
                except Exception:
                    pass
                return cur
        except Exception:
            pass
        # Для live-источников используем time_stamp, иначе текущее время
        try:
            # Frame инициализирует time_stamp в __init__, поэтому прямой доступ безопасен
            if image.time_stamp:
                return float(image.time_stamp)
        except Exception:
            pass
        return time.time()

    def _process_pipeline_results(self, pipeline_results) -> list:
        """Положить результаты пайплайна в ObjectsHandler и собрать кадры для визуализации/стриминга.

        Важно: контроллер не должен зависеть от внутренней структуры пайплайна (mc_trackers/trackers/detectors/sources).
        Пайплайн обязан вернуть результаты в единообразном виде (список элементов, где каждый элемент — либо Frame,
        либо (data, Frame)).
        """
        processing_frames = []
        try:
            n = len(pipeline_results)
        except Exception:
            n = -1
        self.logger.debug(f"Processing {n} pipeline results")
        
        for track_info in (pipeline_results or []):
            # Handle both tuples [tracking_result, image] and Frame objects
            if isinstance(track_info, (tuple, list)) and len(track_info) == 2:
                data, image = track_info
            else:
                # Assume it's a Frame object (from attributes processors)
                data = None
                image = track_info

            # Если skip_objects_handler включен, не передаем данные в obj_handler
            if not self.skip_objects_handler and self.obj_handler:
                # ObjectsHandler can become a bottleneck (heavy history/update/save logic).
                # To prevent backlog/lag, we avoid sending "empty" results for every frame.
                # - Always send when there are detections/tracks.
                # - If empty, send at most once per N frames per source as heartbeat.
                try:
                    source_id = getattr(image, "source_id", None)
                    frame_id = getattr(image, "frame_id", None)
                    has_payload = False
                    if data is not None:
                        tracks = getattr(data, "tracks", None)
                        detections = getattr(data, "detections", None)
                        if tracks is not None:
                            has_payload = bool(tracks)
                        elif detections is not None:
                            has_payload = bool(detections)
                    heartbeat_every = 10  # send empty update once per 10 frames
                    should_send = True
                    if not has_payload and source_id is not None and frame_id is not None:
                        last_sent = self._obj_handler_last_sent_frame_id.get(source_id)
                        if last_sent is not None and (frame_id - last_sent) < heartbeat_every:
                            should_send = False
                    if should_send:
                        self.obj_handler.put(track_info)
                        if source_id is not None and frame_id is not None:
                            self._obj_handler_last_sent_frame_id[source_id] = int(frame_id)
                except Exception:
                    # Never break the controller loop on obj_handler throttling errors
                    try:
                        self.obj_handler.put(track_info)
                    except Exception:
                        pass
            
            processing_frames.append(image)

            try:
                # Frame инициализирует source_id и frame_id в __init__, поэтому прямой доступ безопасен
                source_id = image.source_id
                frame_id = image.frame_id
                
                if source_id is not None and frame_id is not None:
                    self.source_last_processed_frame_id[source_id] = frame_id

                    # Диагностическое логирование прогресса кадров по каждому источнику.
                    # Помогает понять, доходят ли новые кадры до контроллера.
                    counter = self._per_source_frame_debug_counter.get(source_id, 0) + 1
                    self._per_source_frame_debug_counter[source_id] = counter
                    # Логируем не каждый кадр, чтобы не заспамить лог, а, например, каждый 150‑й
                    if counter % 150 == 0:
                        try:
                            src_name = self.source_id_name_table.get(source_id, f"src{source_id}")
                            last_id = self.source_last_processed_frame_id.get(source_id)
                            self.logger.debug(
                                f"Controller frame progress: "
                                f"source_id={source_id} ({src_name}), "
                                f"frame_id={frame_id}, "
                                f"last_processed_frame_id={last_id}"
                            )
                        except Exception:
                            # Диагностика не должна ломать основной цикл
                            pass
            except Exception:
                pass

            # Event recording: add frames into per-source buffers/recorders (if enabled)
            if self.recording_params and self.recording_params.event_recording_enabled:
                try:
                    # Frame инициализирует image и source_id в __init__, поэтому прямой доступ безопасен
                    source_id = image.source_id
                    if source_id is not None and source_id in self.event_buffers and image.image is not None:
                        ts = self._get_frame_timestamp_sec(image)
                        self.event_buffers[source_id].add_frame(image.image, ts)
                except Exception as e:
                    self.logger.debug(f"Error adding frame to event buffer: {e}")

                try:
                    # Frame инициализирует image и source_id в __init__, поэтому прямой доступ безопасен
                    source_id = image.source_id
                    if source_id is not None and source_id in self.event_recorders:
                        event_recorder = self.event_recorders[source_id]
                        if event_recorder.is_recording() and image.image is not None:
                            ts = self._get_frame_timestamp_sec(image)
                            event_recorder.add_post_event_frame(image.image, ts)
                except Exception as e:
                    self.logger.debug(f"Error adding post-event frame: {e}")

        self.logger.debug(f"Collected {len(processing_frames)} frames for processing")
        return processing_frames

    def _process_tracking_results(self, mc_tracking_results) -> list:
        """Backward compatible wrapper."""
        return self._process_pipeline_results(mc_tracking_results)

    def _process_events_once(self) -> None:
        """Считать события из EventsDetectorsController и передать в EventsProcessor."""
        try:
            if not self.events_detectors_controller:
                return
            events = self.events_detectors_controller.get()
            if events and self.events_processor:
                self.events_processor.put(events)
        except Exception:
            # Не ломаем основной цикл контроллера из-за ошибок событий
            pass

    def _collect_preview_objects_by_source(self, source_ids: set[int], objects_results) -> dict[int, ObjectResultList]:
        objects_by_source: dict[int, ObjectResultList] = {}
        if not source_ids:
            return objects_by_source
        try:
            if self.skip_objects_handler:
                converted = self._convert_results_for_visualization(objects_results or [])
                for source_id in source_ids:
                    objects_by_source[source_id] = converted.get(source_id, ObjectResultList())
            else:
                for source_id in source_ids:
                    if self.obj_handler:
                        objects_by_source[source_id] = self.obj_handler.get("active", source_id)
                    else:
                        objects_by_source[source_id] = ObjectResultList()
        except Exception:
            for source_id in source_ids:
                objects_by_source.setdefault(source_id, ObjectResultList())
        return objects_by_source

    def _get_preview_event_entries(self, source_id: int) -> list[dict]:
        with self._preview_events_lock:
            return list((self._preview_active_events_by_source.get(source_id) or {}).values())

    def _get_preview_visualizer_cfg(self) -> dict:
        if isinstance(self.params, dict):
            cfg = self.params.get("visualizer", {})
            if isinstance(cfg, dict):
                return cfg
        return {}

    def _get_preview_event_cfg(self) -> dict:
        vis_cfg = self._get_preview_visualizer_cfg()
        nested = vis_cfg.get("event_signalization", {})
        if isinstance(nested, dict) and nested:
            return nested
        return vis_cfg

    def _extract_preview_zones(self) -> dict[int, list]:
        zones_cfg = (((self.params or {}).get('events_detectors', {}) or {}).get('ZoneEventsDetector', {}) or {}).get('sources', {})
        sources_zones: dict[int, list] = {}
        if not isinstance(zones_cfg, dict):
            return sources_zones
        for key, zone_list in zones_cfg.items():
            try:
                source_id = int(key)
            except Exception:
                continue
            prepared = []
            for coords in (zone_list or []):
                if isinstance(coords, list) and coords:
                    prepared.append(['poly', coords, None])
            if prepared:
                sources_zones[source_id] = prepared
        return sources_zones

    def _build_preview_render_context(self, frame, objects_by_source: dict[int, ObjectResultList]) -> PreviewRenderContext:
        source_id = getattr(frame, "source_id", None)
        frame_id = getattr(frame, "frame_id", None)
        object_list = objects_by_source.get(source_id, ObjectResultList())
        track_info = object_list.find_objects_by_frame_id(frame_id, use_history=False) if object_list else []
        event_entries = self._get_preview_event_entries(source_id)
        event_cfg = self._get_preview_event_cfg()
        vis_cfg = self._get_preview_visualizer_cfg()
        event_enabled = bool(event_cfg.get("event_signal_enabled", False))
        event_color = tuple(event_cfg.get("event_signal_color", [255, 0, 0]))
        return PreviewRenderContext(
            source_name=self.source_id_name_table.get(source_id, f"src{source_id}"),
            source_duration_msecs=self.source_video_duration.get(source_id),
            track_info=track_info,
            debug_info=self.debug_info,
            show_debug_info=bool(vis_cfg.get("show_debug_info", False)),
            text_config=vis_cfg.get("text_config", {}) or {},
            class_mapping=self.class_mapping or {},
            event_signal_enabled=event_enabled,
            event_color_rgb=event_color,
            event_active_obj_ids={entry["object_id"] for entry in event_entries if entry.get("object_id") is not None},
            active_event_labels=[
                f'{entry.get("event_name", "Event")} [{entry.get("object_id")}]'
                for entry in event_entries
            ],
            zones=self._preview_zones_by_source.get(source_id, []),
        )

    def _publish_latest_frame_to_broker(self, processing_frames: list, objects_results=None) -> None:
        """Опубликовать последние кадры всех sources в web broker/shared files."""
        try:
            if not processing_frames:
                self.logger.debug("No processing frames available for publishing")
                return
            interested_frames = []
            interested_source_ids: set[int] = set()
            for frame in processing_frames:
                if getattr(frame, "image", None) is None:
                    continue
                source_id = getattr(frame, "source_id", None)
                if self._preview_render_service is not None:
                    if not self._preview_render_service.wants_frame(source_id):
                        continue
                interested_frames.append(frame)
                if source_id is not None:
                    interested_source_ids.add(source_id)
            if not interested_frames:
                self.logger.debug("No frames currently requested for preview publish")
                return
            objects_by_source = self._collect_preview_objects_by_source(interested_source_ids, objects_results)
            published = 0
            for frame in interested_frames:
                accepted = False
                if self._preview_render_service is not None:
                    render_context = self._build_preview_render_context(frame, objects_by_source)
                    accepted = self._preview_render_service.submit_frame(frame, render_context)
                elif self._streaming_service:
                    accepted = self._streaming_service.submit_frame(frame)
                if accepted:
                    published += 1
                    self.logger.debug(
                        "Submitted frame for async streaming publish: pipeline=%s source=%s frame=%s",
                        self.stream_pipeline_id,
                        getattr(frame, "source_id", None),
                        getattr(frame, "frame_id", None),
                    )
            if published == 0:
                self.logger.debug("No frames were accepted for async streaming publish")
        except Exception as e:
            # Do not break controller loop if streaming is not initialized
            self.logger.debug(f"Frame publish failed: {e}")

    def _check_memory_and_maybe_stop(self) -> bool:
        """Периодически проверять память; если лимит превышен — остановить цикл.

        Returns:
            True если цикл нужно прервать (run_flag уже сброшен).
        """
        try:
            needs_check = (
                not self.debug_info.get("controller")
                or not self.debug_info["controller"].get("timestamp")
                or (
                    (
                        datetime.datetime.now() - self.debug_info["controller"]["timestamp"]
                    ).total_seconds()
                    > self.memory_periodic_check_sec
                )
            )
            if not needs_check:
                return False

            self.collect_memory_consumption()
            if self.show_memory_usage:
                pprint.pprint(self.debug_info)

            total_memory_usage_mb = None
            if self.debug_info.get("controller"):
                total_memory_usage_mb = self.debug_info["controller"].get("total_memory_usage_mb")
            if total_memory_usage_mb and total_memory_usage_mb >= self.max_memory_usage_mb:
                self.logger.warning(
                    f"Memory usage exceeded: {total_memory_usage_mb:.2f} Mb "
                    f"(maximum: {self.max_memory_usage_mb:.2f} Mb)"
                )
                self.logger.debug(f"Debug info: {pprint.pformat(self.debug_info)}")
                if self.auto_restart:
                    self.restart_flag = True
                self.run_flag = False
                return True
            return False
        except Exception:
            return False

    def _convert_results_for_visualization(self, mc_tracking_results) -> dict[int, ObjectResultList]:
        """
        Конвертировать результаты детекции/трекинга в ObjectResultList для визуализации.
        
        Args:
            mc_tracking_results: Список результатов из пайплайна [TrackingResultList/DetectionResultList, image]
            
        Returns:
            dict[source_id, ObjectResultList] - объекты по source_id
        """
        result_by_source = {}
        
        for track_info in mc_tracking_results:
            if isinstance(track_info, (tuple, list)) and len(track_info) == 2:
                tracking_result, image = track_info
            else:
                continue
                
            if image is None:
                continue
                
            source_id = image.source_id
            
            if source_id not in result_by_source:
                result_by_source[source_id] = ObjectResultList()
            
            # Конвертировать в зависимости от типа
            if isinstance(tracking_result, DetectionResultList):
                # Конвертировать DetectionResultList
                for detection in tracking_result.detections:
                    obj = self._create_object_from_detection(detection, tracking_result, image)
                    result_by_source[source_id].objects.append(obj)
            elif isinstance(tracking_result, TrackingResultList):
                # Конвертировать TrackingResultList
                for track in tracking_result.tracks:
                    obj = self._create_object_from_track(track, tracking_result, image)
                    result_by_source[source_id].objects.append(obj)
        
        return result_by_source

    def _create_object_from_detection(self, detection, detection_list, image):
        """Создать ObjectResult из DetectionResult"""
        obj = ObjectResult()
        obj.frame_id = detection_list.frame_id
        obj.source_id = detection_list.source_id
        obj.class_id = detection.class_id
        # Конвертировать timestamp в datetime если нужно
        if detection_list.time_stamp is not None:
            if isinstance(detection_list.time_stamp, (int, float)):
                obj.time_stamp = datetime.datetime.fromtimestamp(detection_list.time_stamp)
            elif isinstance(detection_list.time_stamp, datetime.datetime):
                obj.time_stamp = detection_list.time_stamp
            else:
                obj.time_stamp = datetime.datetime.now()
        else:
            obj.time_stamp = datetime.datetime.now()
        obj.time_detected = obj.time_stamp
        
        # Создать временный TrackingResult
        track = TrackingResult()
        track.track_id = detection_list.frame_id if detection_list.frame_id is not None else 0  # Временный ID
        track.bounding_box = detection.bounding_box
        track.confidence = detection.confidence
        track.class_id = detection.class_id
        track.tracking_data = {}
        
        obj.track = track
        return obj

    def _create_object_from_track(self, track, tracking_list, image):
        """Создать ObjectResult из TrackingResult"""
        obj = ObjectResult()
        obj.frame_id = tracking_list.frame_id
        obj.source_id = tracking_list.source_id
        obj.class_id = track.class_id
        # Конвертировать timestamp в datetime если нужно
        if tracking_list.time_stamp is not None:
            if isinstance(tracking_list.time_stamp, (int, float)):
                obj.time_stamp = datetime.datetime.fromtimestamp(tracking_list.time_stamp)
            elif isinstance(tracking_list.time_stamp, datetime.datetime):
                obj.time_stamp = tracking_list.time_stamp
            else:
                obj.time_stamp = datetime.datetime.now()
        else:
            obj.time_stamp = datetime.datetime.now()
        obj.time_detected = obj.time_stamp
        obj.track = track
        obj.global_id = track.tracking_data.get('global_id', None) if track.tracking_data else None
        return obj

    def _maybe_update_visualization(self, processing_frames: list, dropped_frames) -> None:
        """Обновить визуализацию (если GUI включен)."""
        if not (self.show_main_gui and self.gui_enabled and self.visualizer):
            return
        try:
            objects = []
            if self.skip_objects_handler:
                # Конвертируем результаты напрямую из пайплайна для визуализации
                pipeline_results = self.pipeline.peek_latest_result()
                if pipeline_results is not None:
                    final_results_name = self.pipeline.get_final_results_name()
                    mc_tracking_results = pipeline_results.get(final_results_name, [])
                    converted_objects = self._convert_results_for_visualization(mc_tracking_results)
                    # Создаем список ObjectResultList в порядке source_ids визуализатора
                    for source_id in self.visualizer.source_ids:
                        objects.append(converted_objects.get(source_id, ObjectResultList()))
                else:
                    # Если результатов нет, создаем пустые списки
                    for source_id in self.visualizer.source_ids:
                        objects.append(ObjectResultList())
            else:
                # Стандартная обработка - получаем из obj_handler
                for source_id in self.visualizer.source_ids:
                    if self.obj_handler:
                        objects.append(self.obj_handler.get("active", source_id))
                    else:
                        objects.append(ObjectResultList())
            self.visualizer.update(
                processing_frames,
                self.source_last_processed_frame_id,
                objects,
                dropped_frames,
                self.debug_info,
            )
        except Exception:
            # Визуализация не должна падать весь цикл
            pass

    def run(self):
        self.logger.info(f"Controller main loop started, stream_pipeline_id: {self.stream_pipeline_id}")
        # Emit system started via detector (unified path)
        if self.system_events_detector:
            self.system_events_detector.emit_started()
        while self.run_flag:
            try:
                # Periodic process-level resource stats to correlate slow RSS growth.
                try:
                    if self.params and isinstance(self.params, dict):
                        ctrl_cfg = (self.params.get("controller", {}) or {})
                        if "resource_stats_interval_sec" in ctrl_cfg:
                            try:
                                self._resource_stats_every_sec = float(
                                    ctrl_cfg.get("resource_stats_interval_sec") or self._resource_stats_every_sec
                                )
                            except Exception:
                                pass
                    now_ts = time.time()
                    every = float(self._resource_stats_every_sec or 0.0)
                    if every > 0 and (self._resource_stats_last_ts <= 0 or (now_ts - self._resource_stats_last_ts) >= every):
                        self._resource_stats_last_ts = now_ts
                        self._log_resource_stats(context="periodic")
                except Exception:
                    pass

                perf_diag_enabled = self._perf_diag_env
                try:
                    if self.params and isinstance(self.params, dict):
                        cfg = (self.params.get("controller", {}) or {})
                        if bool(cfg.get("perf_diag", False)):
                            perf_diag_enabled = True
                        if "perf_diag_every" in cfg:
                            self._perf_diag_every = int(cfg.get("perf_diag_every") or self._perf_diag_every)
                except Exception:
                    pass

                begin_it = timer()
                t0 = timer() if perf_diag_enabled else None
                self.pipeline.process()
                t1 = timer() if perf_diag_enabled else None
                all_sources_finished = self.pipeline.check_all_sources_finished()

                objects_results = self.pipeline.get_latest_objects_results()
                vis_frames = self.pipeline.get_latest_visualization_frames()
                t2 = timer() if perf_diag_enabled else None
                try:
                    self.logger.debug(
                        f"Visualization frames count: {len(vis_frames)}; "
                        f"objects_results_count: {len(objects_results) if objects_results is not None else -1}"
                    )
                except Exception:
                    pass

                self.pipeline.insert_debug_info_by_id(self.debug_info)

                if self.autoclose and all_sources_finished:
                    self.run_flag = False

                fallback_processing_frames = self._process_pipeline_results(objects_results)

                processing_frames = []
                try:
                    for item in (vis_frames or []):
                        if isinstance(item, (tuple, list)) and len(item) == 2:
                            _, img = item
                            processing_frames.append(img)
                        else:
                            processing_frames.append(item)
                except Exception:
                    processing_frames = []
                if not processing_frames:
                    processing_frames = list(fallback_processing_frames or [])

                t3 = timer() if perf_diag_enabled else None
                self._process_events_once()

                dropped_frames = self.pipeline.get_dropped_ids()

                if self._check_memory_and_maybe_stop():
                    continue

                self._maybe_update_visualization(processing_frames, dropped_frames)
                self._publish_latest_frame_to_broker(processing_frames, objects_results)
                t4 = timer() if perf_diag_enabled else None
                t5 = timer() if perf_diag_enabled else None

                end_it = timer()
                elapsed_seconds = end_it - begin_it

                if self.fps:
                    sleep_seconds = 1. / self.fps - elapsed_seconds
                    if sleep_seconds <= 0.0:
                        sleep_seconds = 0.001
                else:
                    sleep_seconds = 0.03

                time.sleep(sleep_seconds)

                if perf_diag_enabled:
                    self._perf_diag_loop += 1
                    every = max(1, int(self._perf_diag_every or 60))
                    if (self._perf_diag_loop % every) == 0:
                        lag_ms = None
                        try:
                            if processing_frames:
                                fr = processing_frames[-1]
                                now = time.time()
                                if getattr(fr, "current_video_position", None) is None or fr.current_video_position < 0:
                                    ts = getattr(fr, "time_stamp", None)
                                    if isinstance(ts, (int, float)) and ts > 0:
                                        lag_ms = (now - float(ts)) * 1000.0
                        except Exception:
                            pass
                        try:
                            self.logger.info(
                                "PerfDiag: loop=%d, frames=%d, "
                                "pipeline_ms=%.1f, select_ms=%.1f, proc_ms=%.1f, publish_ms=%.1f, viz_ms=%.1f, total_ms=%.1f%s",
                                self._perf_diag_loop,
                                (len(processing_frames) if processing_frames else 0),
                                ((t1 - t0) * 1000.0 if (t0 is not None and t1 is not None) else -1.0),
                                ((t2 - t1) * 1000.0 if (t1 is not None and t2 is not None) else -1.0),
                                ((t3 - t2) * 1000.0 if (t2 is not None and t3 is not None) else -1.0),
                                ((t4 - t3) * 1000.0 if (t3 is not None and t4 is not None) else -1.0),
                                ((t5 - t4) * 1000.0 if (t4 is not None and t5 is not None) else -1.0),
                                ((t5 - t0) * 1000.0 if (t0 is not None and t5 is not None) else -1.0),
                                (f", lag_ms={lag_ms:.1f}" if lag_ms is not None else ""),
                            )
                        except Exception:
                            pass
            except Exception as exc:
                self.logger.error("Unhandled error in control loop iteration: %s", exc, exc_info=True)
                time.sleep(0.1)

        if self.system_events_detector:
            self.system_events_detector.emit_stopped()
            time.sleep(0.2)

    def _log_resource_stats(self, context: str) -> None:
        """Log lightweight RSS/threads/FD metrics for the current process."""
        pid = None
        try:
            pid = os.getpid()
        except Exception:
            pid = None

        rss_mb = None
        num_threads = None
        num_fds = None
        open_files = None
        try:
            import psutil  # type: ignore
            proc = psutil.Process(pid) if pid else psutil.Process()
            mem = proc.memory_info()
            rss_mb = mem.rss / (1024 * 1024)
            try:
                num_threads = proc.num_threads()
            except Exception:
                num_threads = None
            try:
                num_fds = proc.num_fds()
            except Exception:
                num_fds = None
            try:
                open_files = len(proc.open_files())
            except Exception:
                open_files = None
        except Exception:
            return

        try:
            log_method = self.logger.debug if context == "periodic" else self.logger.info
            log_method(
                "ResourceStats[%s] pid=%s rss_mb=%s threads=%s fds=%s open_files=%s%s",
                context,
                pid,
                (f"{rss_mb:.3f}" if isinstance(rss_mb, (int, float)) else "n/a"),
                (str(num_threads) if num_threads is not None else "n/a"),
                (str(num_fds) if num_fds is not None else "n/a"),
                (str(open_files) if open_files is not None else "n/a"),
                self._format_source_restart_counters(),
            )
        except Exception:
            pass

    def _format_source_restart_counters(self) -> str:
        """Best-effort: append per-source capture restart counters (loop_play restarts)."""
        try:
            sources = []
            try:
                if getattr(self, "_pipeline_service", None):
                    sources = self._pipeline_service.get_sources() or []
            except Exception:
                sources = []
            if not sources:
                try:
                    if self.pipeline is not None and hasattr(self.pipeline, "get_sources"):
                        sources = self.pipeline.get_sources() or []
                except Exception:
                    sources = []

            parts: list[str] = []
            for src in sources:
                if src is None:
                    continue
                try:
                    # Name label
                    names = getattr(src, "source_names", None)
                    ids = getattr(src, "source_ids", None)
                    if names:
                        label = "-".join(str(x) for x in names)
                    elif ids:
                        label = "-".join(str(x) for x in ids)
                    else:
                        label = type(src).__name__

                    # Counter
                    cnt = None
                    for attr in ("_restart_counter", "restart_counter"):
                        if hasattr(src, attr):
                            try:
                                cnt = int(getattr(src, attr))
                            except Exception:
                                cnt = None
                            break
                    if cnt is None:
                        continue
                    parts.append(f"{label}:{cnt}")
                except Exception:
                    continue
            if not parts:
                return ""
            # Keep it compact; it's already a periodic log line.
            return " restarts={" + ",".join(parts) + "}"
        except Exception:
            return ""

    def start(self):
        # Start pipeline через PipelineService
        self._pipeline_service.start_pipeline()
        
        # Start ObjectsHandler через ObjectsHandlerService
        if self.obj_handler:
            self._objects_handler_service.start_objects_handler()
        
        # Start visualizer через VisualizationService
        if self.visualizer:
            self._visualization_service.start_visualizer()
        
        # Start system diagnostics and memory monitoring
        if self.memory_monitor:
            self.memory_monitor.start()
        if self.system_diagnostics:
            self.system_diagnostics.start()
        
        # Start database adapters через DatabaseService
        if self.use_database and self._database_service.is_connected():
            self._database_service.start_adapters()
            self.db_controller = self._database_service.get_db_controller()
            try:
                import platform
                import sys
                
                # Логируем попытку подключения к БД
                # DatabaseController инициализирует params через set_params, проверяем наличие
                db_params = self.db_controller.params if hasattr(self.db_controller, 'params') else {}
                self.logger.info(f"Attempting to connect to database at startup: "
                               f"host={db_params.get('host_name', 'unknown')}, "
                               f"port={db_params.get('port', 'unknown')}, "
                               f"database={db_params.get('database_name', 'unknown')}, "
                               f"platform={platform.system()} {platform.release()}")
                
                # Пытаемся подключиться к БД
                self.db_controller.connect()
                
                # Проверяем, что подключение действительно установлено
                if not self.db_controller.is_connected():
                    raise Exception("Database connection failed: connection pool is None")
                
                self.logger.info("Database connected successfully at startup")
                
            except Exception as e:
                # Детальное логирование ошибки подключения к БД
                import platform
                import sys
                
                error_context = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'platform': f"{platform.system()} {platform.release()}",
                    'python_version': sys.version.split()[0]
                }
                
                if self.db_controller:
                    # DatabaseController инициализирует params через set_params, проверяем наличие
                    db_params = (self.db_controller.params if hasattr(self.db_controller, 'params') else {}) or {}
                    error_context.update({
                        'host': db_params.get('host_name', 'unknown'),
                        'port': db_params.get('port', 'unknown'),
                        'database': db_params.get('database_name', 'unknown'),
                        'user': db_params.get('user_name', 'unknown')
                    })
                
                self.logger.warning(f"Database connection error at startup. Disabling database functionality. Reason: {e}")
                self.logger.debug(f"Database connection context: {error_context}")
                self.logger.info("System will continue operating in JSON-only mode. "
                              "Events will be saved to JSON files.")
                
                # Полностью отключаем функциональность БД
                self.use_database = False
                # Останавливаем адаптеры БД, если они были запущены
                try:
                    if self.db_adapter_obj:
                        self.db_adapter_obj.stop()
                    if self.db_adapter_zone_events:
                        self.db_adapter_zone_events.stop()
                    if self.db_adapter_fov_events:
                        self.db_adapter_fov_events.stop()
                    if self.db_adapter_cam_events:
                        self.db_adapter_cam_events.stop()
                    if self.db_adapter_attr_events:
                        self.db_adapter_attr_events.stop()
                    if self.db_adapter_system_events:
                        self.db_adapter_system_events.stop()
                except Exception:
                    pass  # Игнорируем ошибки при остановке адаптеров
                
                # Убеждаемся, что контроллер БД в безопасном состоянии
                if self.db_controller:
                    self.db_controller.conn_pool = None
                self.db_controller = None
        
        # Start events detectors и processor через EventsService
        if self._events_service:
            self._events_service.start_detectors()
            if self.events_detectors_controller:
                self.events_detectors_controller.start()
            if self.events_processor:
                self.events_processor.start()
        
        # Start storage monitor
        if self.storage_monitor:
            try:
                self.storage_monitor.start()
            except Exception as e:
                self.logger.warning(f"Failed to start storage monitor: {e}", exc_info=True)

        self.run_flag = True
        try:
            register_runtime(
                rid=int(self.stream_pipeline_id),
                pid=os.getpid(),
                config_path=None,
                name=None,
                frame_dir=None,
                source="process",
                managed=os.environ.get("EVILEYE_MANAGED_RUN") == "1",
                state="running",
            )
        except Exception:
            pass
        self._publish_runtime_snapshot(state="running")
        self.logger.info(f"Starting control thread for stream_pipeline_id: {self.stream_pipeline_id}")
        self.control_thread.start()
        self.logger.info(f"Control thread started successfully")

    def stop(self):
        self.run_flag = False
        self._publish_runtime_snapshot(state="stopping")
        self.logger.info("Controller shutdown: stopping pipeline")
        # Stop pipeline first (detectors/trackers/captures) so source reconnect and
        # recorder loops cannot continue while the rest of shutdown is still running.
        self._pipeline_service.stop_pipeline()
        self.logger.info("Controller shutdown: pipeline stop requested")
        if self.control_thread and self.control_thread.is_alive():
            # Don't block shutdown forever if pipeline.process() is stuck.
            self.control_thread.join(timeout=3.0)
            if self.control_thread.is_alive():
                try:
                    self.logger.warning("Controller control_thread did not stop within 3s; continuing shutdown")
                except Exception:
                    pass

        # Stop ObjectsHandler через ObjectsHandlerService
        if self.obj_handler:
            self.logger.info("Controller shutdown: stopping objects handler")
            self._objects_handler_service.stop_objects_handler()

        # Stop visualizer через VisualizationService
        if self.visualizer:
            self.logger.info("Controller shutdown: stopping visualizer")
            self._visualization_service.stop_visualizer()

        # Stop events detectors через EventsService
        if self._events_service:
            self.logger.info("Controller shutdown: stopping events subsystem")
            self._events_service.stop_detectors()
            # Flush events controller once before stopping
            if self.events_detectors_controller:
                self.events_detectors_controller.flush_once()
                events = self.events_detectors_controller.get()
                if events and self.events_processor:
                    self.events_processor.put(events)
                self.events_detectors_controller.stop()
            if self.events_processor:
                self.events_processor.stop()
        
        # Stop event recording
        self.logger.info("Controller shutdown: stopping event recorders")
        for source_id, event_recorder in self.event_recorders.items():
            try:
                if event_recorder.is_recording():
                    event_recorder.stop_event_recording()
            except Exception:
                pass
        self.event_recorders.clear()
        self.event_buffers.clear()

        # Stop database adapters через DatabaseService
        if self.use_database and self._database_service.is_connected():
            self.logger.info("Controller shutdown: stopping database adapters")
            self._database_service.stop_adapters()
            if self.db_controller:
                self.db_controller.disconnect()
        
        # Stop storage monitor
        if self.storage_monitor:
            self.logger.info("Controller shutdown: stopping storage monitor")
            try:
                self.storage_monitor.stop()
            except Exception as e:
                self.logger.warning(f"Error stopping storage monitor: {e}", exc_info=True)
        
        # Stop system diagnostics and memory monitoring
        self.logger.info("Controller shutdown: stopping diagnostics")
        if self.system_diagnostics:
            self.system_diagnostics.stop()
        if self.memory_monitor:
            self.memory_monitor.stop()

        # Stop web server process if running
        if self._server_process_manager is not None:
            self.logger.info("Controller shutdown: stopping embedded web server")
            try:
                self._server_process_manager.stop()
            except Exception as e:
                self.logger.warning(f"Error stopping server process: {e}")
            self._server_process_manager = None
        if self._preview_render_service is not None:
            self.logger.info("Controller shutdown: stopping preview render service")
            self._preview_render_service.stop()
        if self._streaming_service is not None:
            self.logger.info("Controller shutdown: stopping streaming service")
            self._streaming_service.stop()
        self.logger.info('All controller components stopped')

    def init(self, params):
        self.params = params
        # Сохраняем исходный конфиг для правил частичного сохранения
        try:
            import copy as _copy
            self.loaded_config = _copy.deepcopy(params) if isinstance(params, dict) else dict()
        except Exception:
            self.loaded_config = dict()

        if 'controller' in self.params.keys():
            self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
            self.fps = self.params['controller'].get("fps", self.fps)
            self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
            self.gui_enabled = self.params['controller'].get("gui_enabled", self.gui_enabled)
            self.skip_objects_handler = self.params['controller'].get("skip_objects_handler", self.skip_objects_handler)

            self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
            self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
            # Handle both old class_names format and new class_mapping format
            if "class_mapping" in self.params['controller']:
                self.class_mapping = self.params['controller'].get("class_mapping", {})
            elif "class_names" in self.params['controller']:
                # Convert old class_names list to class_mapping dict
                class_names = self.params['controller'].get("class_names", [])
                self.class_mapping = {name: idx for idx, name in enumerate(class_names)}
            else:
                # Keep default class_mapping if neither is specified
                pass
            # Optional: override late model loading timeout
            self.model_loading_timeout_sec = self.params['controller'].get("model_loading_timeout_sec", self.model_loading_timeout_sec)
            self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
            self.show_memory_usage = self.params['controller'].get("show_memory_usage", self.show_memory_usage)
            self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
            self.auto_restart = self.params['controller'].get("auto_restart", self.auto_restart)
            self.use_database = self.params['controller'].get("use_database", self.use_database)

        server_cfg = self.params.get("server", {}) if isinstance(self.params, dict) else {}
        if isinstance(server_cfg, dict):
            self._stream_publish_fps = float(server_cfg.get("publish_fps", self._stream_publish_fps) or 0.0)

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
                self.credentials_loaded = True
        except FileNotFoundError as ex:
            self.credentials_loaded = False

        # Initialize processing pipeline (sources, preprocessors, detectors, trackers)
        pipeline_params = self.params.get("pipeline", {})
        # Propagate global recording config into each source (so capture can access it)
        try:
            record_cfg = (self.params or {}).get("record", {}) or {}
            if isinstance(record_cfg, dict) and record_cfg:
                # Recording base dir policy:
                # - By default, base path is database.image_dir (even if record.out_dir is set)
                # - For backward compatibility (tests/custom setups), set record.allow_custom_out_dir=true
                allow_custom_out_dir = bool(record_cfg.get("allow_custom_out_dir", False))
                db_image_dir = (((self.params or {}).get('database', {}) or {}).get('image_dir')) or 'EvilEyeData'
                # Base path for ALL recordings (continuous and event-based): image_dir
                # Resolve relative paths relative to working directory, keep absolute paths as-is
                # Concrete recorders add their own subfolders: Streams/... or Events/.../Videos/...
                image_dir_path = Path(db_image_dir)
                if image_dir_path.is_absolute():
                    default_out_dir = str(image_dir_path)
                else:
                    # Resolve relative path relative to current working directory
                    default_out_dir = str(image_dir_path.resolve())

                srcs = pipeline_params.get("sources", []) or []
                enabled_list = record_cfg.get("enabled_sources")
                for idx, s in enumerate(srcs):
                    if not isinstance(s, dict):
                        continue
                    # Merge: keep per-source overrides, fill missing from root
                    per = dict(s.get("record", {})) if isinstance(s.get("record", {}), dict) else {}
                    merged = {**record_cfg, **per}
                    # Ensure out_dir:
                    # - default behavior: always force Streams under database.image_dir
                    # - compatibility: if allow_custom_out_dir=true, keep existing out_dir if provided
                    if allow_custom_out_dir:
                        if not merged.get('out_dir'):
                            merged['out_dir'] = default_out_dir
                    else:
                        merged['out_dir'] = default_out_dir
                    # Apply enabled per source if list provided
                    if enabled_list and len(enabled_list) > 0:
                        # If enabled_sources list is provided, only enable matching sources
                        enabled = False
                        # Match by numeric source id (first in source_ids) or by source_names
                        try:
                            sid = (s.get('source_ids') or [idx])[0]
                        except Exception:
                            sid = idx
                        sname = None
                        try:
                            sname = (s.get('source_names') or [None])[0]
                        except Exception:
                            sname = None
                        for it in enabled_list:
                            if isinstance(it, int) and it == sid:
                                enabled = True
                                break
                            if isinstance(it, str) and sname and it == sname:
                                enabled = True
                                break
                        merged['enabled'] = enabled
                    else:
                        # If enabled_sources is empty/None, use root enabled flag
                        # Backward compatibility:
                        # - If only legacy `enabled` is provided (no new flags), treat it as continuous recording.
                        # New behavior:
                        # - `enabled` is a master switch and MUST NOT implicitly enable continuous/event when new flags exist.
                        has_new_flags = ('continuous_recording_enabled' in merged) or ('event_recording_enabled' in merged)
                        if not has_new_flags:
                            # Legacy mode: enabled -> continuous_recording_enabled
                            if 'enabled' in merged:
                                merged['continuous_recording_enabled'] = bool(merged.get('enabled', False))
                                merged['event_recording_enabled'] = False
                            else:
                                # No record config at all -> default to disabled
                                merged['enabled'] = False
                                merged['continuous_recording_enabled'] = False
                                merged['event_recording_enabled'] = False
                        else:
                            # New mode: ensure master flag exists, but do not derive it from new flags.
                            if 'enabled' not in merged:
                                merged['enabled'] = True
                    s['record'] = merged
                    try:
                        sid_log = (s.get('source_ids') or [idx])[0]
                        sname_log = (s.get('source_names') or [None])[0]
                        self.logger.info(f"Record config for source id={sid_log} name={sname_log}: enabled={merged.get('enabled')} out_dir={merged.get('out_dir')} container={merged.get('container')}")
                    except Exception:
                        pass
        except Exception:
            pass
        # Инициализация pipeline через PipelineService
        pipeline_class_name = pipeline_params.get("pipeline_class")
        self.logger.info(f"Using EVILEYE_PIPELINE_ID for streaming: {self.stream_pipeline_id}")
        
        self.pipeline = self._pipeline_service.create_pipeline(pipeline_class_name)
        self.pipeline = self._pipeline_service.initialize_pipeline(
            pipeline=self.pipeline,
            pipeline_params=pipeline_params,
            credentials=self.credentials,
        )
        
        # Preload controller's class mapping into centralized ClassManager
        try:
            if self.class_mapping:
                self.class_manager.add_class_mapping(self.class_mapping, 'controller_default')
        except Exception:
            pass

        # Update class_mapping from detectors after pipeline initialization
        self.update_class_mapping_from_detectors()

        # Fill source maps for visualizer and bookkeeping
        sources = self._pipeline_service.get_sources()
        if sources:
            for source in sources:
                # VideoCaptureBase инициализирует source_ids, source_names, video_duration в __init__, поэтому прямой доступ безопасен
                if source.source_ids and source.source_names:
                    for source_id, source_name in zip(source.source_ids, source.source_names):
                        self.source_id_name_table[source_id] = source_name
                        if source.video_duration is not None:
                            self.source_video_duration[source_id] = source.video_duration
                        self.source_last_processed_frame_id[source_id] = 0

        # Инициализация БД через DatabaseService
        from evileye.utils.database_config_utils import compute_database_config
        self.database_config = compute_database_config(
            use_database=self.use_database,
            credentials=self.credentials,
            params=self.params
        )

        db_initialized = False
        if self.use_database:
            db_initialized = self._database_service.initialize_database(
                db_config=self.database_config['database'],
                system_params=self.params
            )
            if db_initialized:
                self._database_service.initialize_adapters(self.database_config['database_adapters'])
                self.db_controller = self._database_service.get_db_controller()
                # Сохраняем ссылки на адаптеры для обратной совместимости
                self.db_adapter_obj = self._database_service.get_adapter('DatabaseAdapterObjects')
                self.db_adapter_cam_events = self._database_service.get_adapter('DatabaseAdapterCamEvents')
                self.db_adapter_fov_events = self._database_service.get_adapter('DatabaseAdapterFieldOfViewEvents')
                self.db_adapter_zone_events = self._database_service.get_adapter('DatabaseAdapterZoneEvents')
                self.db_adapter_attr_events = self._database_service.get_adapter('DatabaseAdapterAttributeEvents')
                self.db_adapter_system_events = self._database_service.get_adapter('DatabaseAdapterSystemEvents')
            else:
                # Fallback to no-database mode
                self.use_database = False
                self.db_controller = None
                self.database_config = {"database": {}, "database_adapters": {}}
        
        # Инициализация ObjectsHandler через ObjectsHandlerService
        if db_initialized:
            db_adapter_obj = self._database_service.get_adapter('DatabaseAdapterObjects')
            self.obj_handler = self._objects_handler_service.create_objects_handler(
                db_controller=self.db_controller,
                db_adapter=db_adapter_obj,
            )
            self.obj_handler = self._objects_handler_service.initialize_objects_handler(
                objects_handler=self.obj_handler,
                params=params.get('objects_handler') or dict(),
                pipeline=self.pipeline,
            )
            # Инициализация событий через EventsService
            self._events_service.initialize_detectors(
                params=self.params.get('events_detectors', dict()),
                pipeline=self.pipeline,
                objects_handler=self.obj_handler,
                use_database=True,
            )
            # Сохраняем ссылки для обратной совместимости
            self.cam_events_detector = self._events_service.get_detector('CamEventsDetector')
            self.fov_events_detector = self._events_service.get_detector('FieldOfViewEventsDetector')
            self.zone_events_detector = self._events_service.get_detector('ZoneEventsDetector')
            self.attr_events_detector = self._events_service.get_detector('AttributeEventsDetector')
            self.system_events_detector = self._events_service.get_detector('SystemEventsDetector')
            
            # Инициализация атрибутных процессоров
            self._events_service.initialize_attribute_processors(
                pipeline=self.pipeline,
                objects_handler=self.obj_handler,
                params=self.params,
            )
            
            self._events_service.initialize_controller(self.params.get('events_detectors', dict()))
            self.events_detectors_controller = self._events_service.get_detectors_controller()
            
            # Инициализация процессора событий
            adapters = self._get_event_adapters()
            self._events_service.initialize_processor(
                params=self.params.get('events_processor', dict()),
                adapters=adapters,
                db_controller=self.db_controller,
                ui_callback=self._on_event_signalization,
            )
            self.events_processor = self._events_service.get_events_processor()
        else:
            self.logger.info("Database functionality disabled. Working without database connection.")
            # Инициализация ObjectsHandler без БД через ObjectsHandlerService
            self.obj_handler = self._objects_handler_service.create_objects_handler(
                db_controller=None,
                db_adapter=None,
            )
            self.obj_handler = self._objects_handler_service.initialize_objects_handler(
                objects_handler=self.obj_handler,
                params=params.get('objects_handler') or dict(),
                pipeline=self.pipeline,
            )
            # Инициализация событий без БД через EventsService
            self._events_service.initialize_detectors(
                params=self.params.get('events_detectors', dict()),
                pipeline=self.pipeline,
                objects_handler=self.obj_handler,
                use_database=False,
            )
            # Сохраняем ссылки для обратной совместимости
            self.cam_events_detector = self._events_service.get_detector('CamEventsDetector')
            self.fov_events_detector = self._events_service.get_detector('FieldOfViewEventsDetector')
            self.zone_events_detector = self._events_service.get_detector('ZoneEventsDetector')
            self.attr_events_detector = self._events_service.get_detector('AttributeEventsDetector')
            self.system_events_detector = self._events_service.get_detector('SystemEventsDetector')
            
            # Инициализация атрибутных процессоров
            self._events_service.initialize_attribute_processors(
                pipeline=self.pipeline,
                objects_handler=self.obj_handler,
                params=self.params,
            )
            
            self._events_service.initialize_controller(self.params.get('events_detectors', dict()))
            self.events_detectors_controller = self._events_service.get_detectors_controller()
            
            # Инициализация процессора событий без БД
            adapters = self._get_event_adapters()
            self._events_service.initialize_processor(
                params=self.params.get('events_processor', dict()),
                adapters=adapters,
                db_controller=None,
                ui_callback=self._on_event_signalization,
            )
            self.events_processor = self._events_service.get_events_processor()
        
        # Initialize event-based recording components
        self._init_event_recording(params)

        server_cfg = self.params.get("server", {}) if isinstance(self.params, dict) else {}
        relay_base_url = os.environ.get("EVILEYE_WEB_API_BASE")
        relay_token = os.environ.get("EVILEYE_INTERNAL_TOKEN") or load_web_auth_config().internal_token
        if self._streaming_service is not None:
            self._streaming_service.configure(
                pipeline_id=self.stream_pipeline_id,
                publish_fps=self._stream_publish_fps,
                server_process_manager=self._server_process_manager,
                relay_base_url=relay_base_url,
                relay_token=relay_token,
                encoder_backend=server_cfg.get("preview_encoder", "auto"),
                jpeg_quality=server_cfg.get("preview_jpeg_quality", 85),
                num_workers=server_cfg.get("preview_encode_workers", 1),
            )
        self._preview_zones_by_source = self._extract_preview_zones()
        if self._preview_render_service is not None:
            self._preview_render_service.configure(
                streaming_service=self._streaming_service,
                num_workers=server_cfg.get("preview_render_workers", 1),
            )

        # Managed API runs already have an outer web server; do not start another one inside the child runtime.
        managed_run = os.environ.get("EVILEYE_MANAGED_RUN") == "1"
        # Initialize web server in a separate process if configured
        if managed_run and server_cfg.get("enabled", False):
            self.logger.info("Skipping embedded web server for managed runtime launch")
            if self._streaming_service is not None and relay_base_url:
                self._streaming_service.set_frame_relay(relay_base_url, relay_token)
        elif server_cfg.get("execution_mode") == "process" and server_cfg.get("enabled", False):
            host = server_cfg.get("host", "127.0.0.1")
            port = int(server_cfg.get("port", 8080))
            scheme = "https" if server_cfg.get("ssl_certfile") or server_cfg.get("ssl_keyfile") else "http"
            inferred_base_url = relay_base_url or f"{scheme}://{host}:{port}/api/v1"
            if not self._can_bind_embedded_server(host, port):
                self.logger.info(
                    "Skipping embedded web server because %s:%s is already in use",
                    host,
                    port,
                )
                if self._streaming_service is not None:
                    self._streaming_service.set_frame_relay(inferred_base_url, relay_token)
            else:
                from evileye.server import ServerProcessManager
                self._server_process_manager = ServerProcessManager()
                self._server_process_manager.start(
                    host=host,
                    port=port,
                    log_level=server_cfg.get("log_level", "info"),
                )
                if self._streaming_service is not None:
                    self._streaming_service.set_server_process_manager(self._server_process_manager)
                self.logger.info("Web server started in a separate process")

        self._publish_runtime_snapshot(state="initialized")

    def init_main_window(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self._init_visualizer(self.params.get('visualizer', dict()))

    def release(self):
        self.stop()
        # Release pipeline components
        self.pipeline.release()
        self.logger.info('All controller components released')

    def update_params(self):
        self.params['controller'] = dict()
        self.params['controller']["autoclose"] = self.autoclose
        self.params['controller']["fps"] = self.fps
        self.params['controller']["show_main_gui"] = self.show_main_gui
        self.params['controller']["gui_enabled"] = self.gui_enabled
        self.params['controller']["show_journal"] = self.show_journal
        self.params['controller']["enable_close_from_gui"] = self.enable_close_from_gui
        # Сохраняем class_mapping только если он присутствовал в исходной конфигурации
        try:
            orig_ctrl = (self.loaded_config or {}).get('controller', {})
            had_class_mapping = isinstance(orig_ctrl, dict) and (('class_mapping' in orig_ctrl) or ('class_names' in orig_ctrl))
        except Exception:
            had_class_mapping = True
        if had_class_mapping:
            self.params['controller']["class_mapping"] = self.class_mapping
        self.params['controller']["memory_periodic_check_sec"] = self.memory_periodic_check_sec
        self.params['controller']["show_memory_usage"] = self.show_memory_usage

        self.params['controller']["max_memory_usage_mb"] = self.max_memory_usage_mb
        self.params['controller']["auto_restart"] = self.auto_restart
        self.params['controller']["use_database"] = self.use_database
        
        # Сохраняем scheduled_restart: сначала из текущих params, затем из loaded_config
        try:
            scheduled_restart = None
            # Сначала проверяем текущие params
            if isinstance(self.params, dict):
                current_ctrl = self.params.get('controller', {})
                if isinstance(current_ctrl, dict) and 'scheduled_restart' in current_ctrl:
                    scheduled_restart = current_ctrl['scheduled_restart']
            # Если не нашли в params, проверяем loaded_config
            if scheduled_restart is None:
                orig_ctrl = (self.loaded_config or {}).get('controller', {})
                if isinstance(orig_ctrl, dict) and 'scheduled_restart' in orig_ctrl:
                    scheduled_restart = orig_ctrl['scheduled_restart']
            # Если нашли, сохраняем
            if scheduled_restart is not None:
                self.params['controller']["scheduled_restart"] = scheduled_restart
        except Exception:
            pass

        # Get pipeline parameters
        pipeline_params = self.pipeline.get_params()
        self.params['pipeline'] = pipeline_params

        # Очистка корня параметров от секций пайплайна (не дублируем их вне 'pipeline')
        try:
            pipeline_section_names = [
                'sources', 'preprocessors', 'detectors', 'trackers', 'mc_trackers',
                'attributes_roi', 'attributes_classifier'
            ]
            for key in pipeline_section_names:
                if key in self.params:
                    try:
                        del self.params[key]
                    except Exception:
                        pass
        except Exception:
            pass

        # Collect objects_handler params with safe fallback to existing/loaded config
        try:
            if self.obj_handler:
                oh_params = self.obj_handler.get_params()
            else:
                oh_params = None
        except Exception:
            oh_params = None
        if not isinstance(oh_params, dict) or not oh_params:
            # Fallback to previously stored or originally loaded config
            oh_params = (self.params.get('objects_handler') if isinstance(self.params, dict) else None) or \
                        ((self.loaded_config or {}).get('objects_handler') if isinstance(self.loaded_config, dict) else None) or {}
        self.params['objects_handler'] = oh_params

        self.params['events_detectors'] = dict()
        self.params['events_detectors']['CamEventsDetector'] = self.cam_events_detector.get_params()
        self.params['events_detectors']['FieldOfViewEventsDetector'] = self.fov_events_detector.get_params()
        self.params['events_detectors']['ZoneEventsDetector'] = self.zone_events_detector.get_params()
        if self.attr_events_detector:
            self.params['events_detectors']['AttributeEventsDetector'] = self.attr_events_detector.get_params()

        self.params['events_processor'] = self.events_processor.get_params()
        
        # Only update database config if database is enabled
        if self.use_database and self.db_controller:
            self.database_config = self.db_controller.get_params()

            self.params['database'] = {}
            self.params['database']['database_name'] = self.database_config.get('database_name', 'evil_eye_db')
            self.params['database']['host_name'] = self.database_config.get('host_name', 'localhost')
            self.params['database']['port'] = self.database_config.get('port', 5432)
            self.params['database']['admin_user_name'] = self.database_config.get('admin_user_name', 'postgres')
            self.params['database']['admin_password'] = self.database_config.get('admin_password', '')
            self.params['database']['image_dir'] = self.database_config.get('image_dir', 'EvilEyeData')
            self.params['database']['preview_width'] = self.database_config.get('preview_width', 300)
            self.params['database']['preview_height'] = self.database_config.get('preview_height', 150)
        else:
            # Set empty database config when database is disabled
            self.params['database'] = {}
        
        # Initialize storage monitor (enabled by default)
        try:
            from evileye.core.storage_monitor import StorageMonitor
            storage_monitor_config = self.params.get('storage_monitor', {})
            # Ensure enabled by default if not explicitly set
            if not storage_monitor_config or 'enabled' not in storage_monitor_config:
                if not storage_monitor_config:
                    storage_monitor_config = {}
                storage_monitor_config['enabled'] = True
            # Get image_dir from database config or use default
            image_dir = self.params.get('database', {}).get('image_dir', 'EvilEyeData')
            self.storage_monitor = StorageMonitor(image_dir, storage_monitor_config)
        except Exception as e:
            self.logger.warning(f"Failed to initialize storage monitor: {e}", exc_info=True)
            self.storage_monitor = None

        # Collect visualizer params with safe fallback
        vis_params = None
        try:
            if self.visualizer:
                vis_params = self.visualizer.get_params()
        except Exception:
            vis_params = None
        if not isinstance(vis_params, dict) or not vis_params:
            vis_params = (self.params.get('visualizer') if isinstance(self.params, dict) else None) or \
                         ((self.loaded_config or {}).get('visualizer') if isinstance(self.loaded_config, dict) else None) or {}
        self.params['visualizer'] = vis_params

        # Text configuration is now part of visualizer section
        # No need to add separate text_config here

        # Дополнительная защита: сразу после обновления параметров удаляем чувствительные поля,
        # model_class_mapping и ограничиваем секцию database ключами исходной конфигурации
        try:
            self._reconcile_credentials_fields(self.params, self.loaded_config, self.credentials_loaded)
        except Exception:
            pass
        try:
            self._filter_model_class_mapping(self.params, self.loaded_config)
        except Exception:
            pass
        try:
            if isinstance(self.loaded_config, dict) and self.loaded_config:
                self._restrict_database_keys(self.params, self.loaded_config)
        except Exception:
            pass

    def _atomic_json_dump(self, path: str, data: dict) -> bool:
        try:
            if not path:
                self.logger.error("No config file path specified for saving")
                return False
            import tempfile
            dir_name = os.path.dirname(path) or "."
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=dir_name, prefix=".tmp_") as tf:
                json.dump(data, tf, indent=4, ensure_ascii=False)
                temp_path = tf.name
            os.replace(temp_path, path)
            return True
        except Exception as e:
            try:
                self.logger.error(f"Failed to save configuration atomically: {e}")
            except Exception:
                pass
            return False

    def _restrict_database_keys(self, params: dict, loaded_config: dict) -> None:
        try:
            orig_db = (loaded_config or {}).get('database', {}) or {}
            if not isinstance(orig_db, dict):
                return
            current_db = params.get('database', {}) or {}
            if not isinstance(current_db, dict):
                params['database'] = {}
                return
            allowed_keys = set(orig_db.keys())
            params['database'] = {k: current_db[k] for k in current_db.keys() if k in allowed_keys}
        except Exception:
            # В случае ошибки не модифицируем секцию
            pass

    def _reconcile_credentials_fields(self, params: dict, loaded_config: dict, credentials_loaded: bool) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            sources = pipeline.get('sources', []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return

            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_sources = orig_pipeline.get('sources', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_sources = []

            CRED_KEYS = {
                'user_name', 'username', 'password', 'pwd', 'login', 'token',
                'rtsp_user', 'rtsp_password', 'auth', 'api_key', 'camera_login', 'camera_password'
            }

            def _strip_userinfo_from_url(url: str) -> str:
                try:
                    from urllib.parse import urlsplit, urlunsplit
                    parts = urlsplit(url)
                    netloc = parts.netloc
                    if '@' in netloc:
                        # remove userinfo
                        hostport = netloc.split('@', 1)[1]
                        new_parts = (parts.scheme, hostport, parts.path, parts.query, parts.fragment)
                        return urlunsplit(new_parts)
                    return url
                except Exception:
                    return url

            def _has_userinfo(url: str) -> bool:
                try:
                    from urllib.parse import urlsplit
                    parts = urlsplit(url)
                    return ('@' in parts.netloc)
                except Exception:
                    return ('@' in (url or ''))

            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = orig_sources[idx] if idx < len(orig_sources) and isinstance(orig_sources[idx], dict) else {}
                orig_cred_keys = {k for k in (orig_src.keys() if isinstance(orig_src, dict) else []) if k in CRED_KEYS}
                keys_to_remove = set()
                for k in list(src.keys()):
                    if k in CRED_KEYS and k not in orig_cred_keys:
                        keys_to_remove.add(k)
                for k in keys_to_remove:
                    try:
                        del src[k]
                    except Exception:
                        pass

                # Additionally: handle embedded credentials in camera URL
                try:
                    cam_now = src.get('camera')
                    cam_orig = orig_src.get('camera') if isinstance(orig_src, dict) else None
                    if isinstance(cam_now, str):
                        # If original didn't have userinfo in URL, strip userinfo from current
                        if not isinstance(cam_orig, str) or not _has_userinfo(cam_orig):
                            src['camera'] = _strip_userinfo_from_url(cam_now)
                        else:
                            # original had userinfo -> keep presence allowed; do not alter
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_api_preference(self, params: dict, loaded_config: dict) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            sources = pipeline.get('sources', []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return
            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_sources = orig_pipeline.get('sources', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_sources = []
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = orig_sources[idx] if idx < len(orig_sources) and isinstance(orig_sources[idx], dict) else {}
                if isinstance(orig_src, dict) and ('apiPreference' in orig_src):
                    src['apiPreference'] = orig_src.get('apiPreference')
        except Exception:
            pass

    def _filter_model_class_mapping(self, params: dict, loaded_config: dict) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            detectors = pipeline.get('detectors', []) if isinstance(pipeline, dict) else []
            if not isinstance(detectors, list) or not detectors:
                return
            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_detectors = orig_pipeline.get('detectors', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_detectors = []
            for idx, det in enumerate(detectors):
                if not isinstance(det, dict):
                    continue
                orig_det = orig_detectors[idx] if idx < len(orig_detectors) and isinstance(orig_detectors[idx], dict) else {}
                if 'model_class_mapping' in det and ('model_class_mapping' not in orig_det):
                    try:
                        del det['model_class_mapping']
                    except Exception:
                        pass
        except Exception:
            pass

    def save_config(self, file_path: str | None = None) -> bool:
        try:
            self.update_params()
        except Exception:
            pass

        try:
            import copy as _copy
            final_params = _copy.deepcopy(self.params) if isinstance(self.params, dict) else {}
        except Exception:
            final_params = self.params if isinstance(self.params, dict) else {}

        try:
            self._reconcile_credentials_fields(final_params, self.loaded_config, self.credentials_loaded)
        except Exception:
            pass

        try:
            if isinstance(self.loaded_config, dict) and self.loaded_config:
                self._restrict_database_keys(final_params, self.loaded_config)
        except Exception:
            pass

        # Отфильтровать model_class_mapping перед записью
        try:
            self._filter_model_class_mapping(final_params, self.loaded_config)
        except Exception:
            pass

        # Финальная защита: убрать любые секции пайплайна с корня перед записью
        try:
            pipe_keys = [
                'sources', 'preprocessors', 'detectors', 'trackers', 'mc_trackers',
                'attributes_roi', 'attributes_classifier'
            ]
            for k in pipe_keys:
                if k in final_params:
                    try:
                        del final_params[k]
                    except Exception:
                        pass
        except Exception:
            pass

        # params_path инициализируется в __init__ контроллера, поэтому прямой доступ безопасен
        path = file_path or self.params_path
        ok = self._atomic_json_dump(path, final_params)
        if ok:
            try:
                self.logger.info(f"Configuration saved by controller to: {path}")
            except Exception:
                pass

        if ok and self.use_database and self.db_controller:
            try:
                self.db_controller.save_job_configuration_info(final_params)
            except Exception as e:
                try:
                    self.logger.warning(f"Failed to update job config in DB: {e}")
                except Exception:
                    pass
        return ok

    def set_current_main_widget_size(self, width, height):
        self.current_main_widget_size = [width, height]
        self.visualizer.set_current_main_widget_size(width, height)

    def _init_object_handler(self, db_controller, params):
        """DEPRECATED: Используйте ObjectsHandlerService вместо этого метода."""
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=db_controller, db_adapter=self.db_adapter_obj)
        safe_params = params or {}
        self.obj_handler.set_params(**safe_params)
        # Set class manager for ObjectsHandler
        self.obj_handler.class_manager = self.class_manager
        self.obj_handler.init()

    def _init_object_handler_without_db(self, params):
        """DEPRECATED: Используйте ObjectsHandlerService вместо этого метода."""
        """Initialize object handler without database connection."""
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=None, db_adapter=None)
        
        # Set cameras parameters from pipeline sources
        # PipelineBase определяет get_sources как абстрактный метод, поэтому прямой вызов безопасен
        sources = self.pipeline.get_sources()
        if sources:
            cameras_params = []
            for source in sources:
                # VideoCaptureBase инициализирует source_ids, source_names в __init__, поэтому прямой доступ безопасен
                if source.source_ids and source.source_names:
                    camera_param = {
                        'source_ids': source.source_ids,
                        'source_names': source.source_names,
                        'camera': source.source_address if source.source_address else ''
                    }
                    cameras_params.append(camera_param)
                
                # Set cameras params in obj_handler using инкапсулированный API
                try:
                    self.obj_handler.set_cameras_params(cameras_params)
                except Exception:
                    # Fallback для старого API
                    self.obj_handler.cameras_params = cameras_params
        
        safe_params = params or {}
        self.obj_handler.set_params(**safe_params)
        # Set class manager for ObjectsHandler
        self.obj_handler.class_manager = self.class_manager
        self.obj_handler.init()

    def _init_db_controller(self, params, system_params):
        """DEPRECATED: Используйте DatabaseService вместо этого метода."""
        self.db_controller = DatabaseControllerPg(system_params)
        self.db_controller.set_params(**params)
        self.db_controller.init()

    def _init_db_adapters(self, params):
        """DEPRECATED: Используйте DatabaseService вместо этого метода."""
        self.db_adapter_obj = DatabaseAdapterObjects(self.db_controller)
        self.db_adapter_obj.set_params(**params['DatabaseAdapterObjects'])
        self.db_adapter_obj.init()

        self.db_adapter_cam_events = DatabaseAdapterCamEvents(self.db_controller)
        self.db_adapter_cam_events.set_params(**params['DatabaseAdapterCamEvents'])
        self.db_adapter_cam_events.init()

        self.db_adapter_fov_events = DatabaseAdapterFieldOfViewEvents(self.db_controller)
        self.db_adapter_fov_events.set_params(**params['DatabaseAdapterFieldOfViewEvents'])
        self.db_adapter_fov_events.init()

        self.db_adapter_zone_events = DatabaseAdapterZoneEvents(self.db_controller)
        self.db_adapter_zone_events.set_params(**params['DatabaseAdapterZoneEvents'])
        self.db_adapter_zone_events.init()

        self.db_adapter_attr_events = DatabaseAdapterAttributeEvents(self.db_controller)
        self.db_adapter_attr_events.set_params(**params['DatabaseAdapterAttributeEvents'])
        self.db_adapter_attr_events.init()

        self.db_adapter_system_events = DatabaseAdapterSystemEvents(self.db_controller)
        self.db_adapter_system_events.set_params(**params['DatabaseAdapterSystemEvents'])
        self.db_adapter_system_events.init()

    def _init_events_detectors(self, params):
        """DEPRECATED: Используйте EventsService вместо этого метода."""
        self.cam_events_detector = CamEventsDetector(self.pipeline.get_sources())
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
        self.zone_events_detector.init()

        # Initialize AttributeEventsDetector
        self.attr_events_detector = AttributeEventsDetector(self.obj_handler)
        self.attr_events_detector.set_params(**params.get('AttributeEventsDetector', dict()))
        self.attr_events_detector.init()

        # Initialize SystemEventsDetector
        self.system_events_detector = SystemEventsDetector()
        self.system_events_detector.set_params(**params.get('SystemEventsDetector', dict()))
        self.system_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector, self.attr_events_detector)
        for source in self.pipeline.get_sources():
            source.subscribe(self.cam_events_detector)
        
        # Инициализация атрибутных процессоров, если они есть в пайплайне
        self._init_attributes_processors(params)

    def _init_attributes_processors(self, params):
        """DEPRECATED: Используйте EventsService.initialize_attribute_processors вместо этого метода."""
        # Проверяем, есть ли атрибутные процессоры в пайплайне
        # PipelineProcessors инициализирует processors в __init__, поэтому прямой доступ безопасен
        if hasattr(self.pipeline, 'processors') and self.pipeline.processors:
            for processor in self.pipeline.processors:
                # ProcessorBase определяет get_name как метод, поэтому прямой вызов безопасен
                proc_name = processor.get_name()
                if proc_name in ['attributes_roi', 'attributes_classifier']:
                        # Получаем параметры для атрибутных процессоров
                        attr_params = params.get('attributes_detection', {})
                        if attr_params:
                            # Прокидываем параметры в ObjectsHandler
                            if 'objects_handler' not in self.obj_handler.params:
                                self.obj_handler.params['objects_handler'] = {}
                            self.obj_handler.params['objects_handler']['attributes_detection'] = attr_params
                            self.obj_handler.set_params_impl()
                            self.logger.info(f"Attribute detection configured for {proc_name}")

    def _init_events_detectors_without_db(self, params):
        """DEPRECATED: Используйте EventsService вместо этого метода."""
        self.cam_events_detector = CamEventsDetector(self.pipeline.get_sources())
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        # Initialize FOV and Zone detectors without database functionality
        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
        self.zone_events_detector.init()

        # Initialize AttributeEventsDetector
        self.attr_events_detector = AttributeEventsDetector(self.obj_handler)
        self.attr_events_detector.set_params(**params.get('AttributeEventsDetector', dict()))
        self.attr_events_detector.init()

        # Initialize SystemEventsDetector
        self.system_events_detector = SystemEventsDetector()
        self.system_events_detector.set_params(**params.get('SystemEventsDetector', dict()))
        self.system_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector, self.attr_events_detector)
        for source in self.pipeline.get_sources():
            source.subscribe(self.cam_events_detector)

    def _init_events_detectors_controller(self, params):
        detectors = [self.cam_events_detector, self.fov_events_detector, self.zone_events_detector]
        if self.attr_events_detector:
            detectors.append(self.attr_events_detector)
        if self.system_events_detector:
            detectors.append(self.system_events_detector)
        self.events_detectors_controller = EventsDetectorsController(detectors)
        self.events_detectors_controller.set_params(**params)
        self.events_detectors_controller.init()

    def _init_events_processor(self, params):
        # Backward-compatible: delegate to unified initializer
        self._init_events_processor_unified(params)

    def _init_events_processor_without_db(self, params):
        """Initialize events processor without database connection."""
        # Backward-compatible: delegate to unified initializer
        self._init_events_processor_unified(params)

    def _get_event_adapters(self):
        """Build list of event adapters depending on database mode."""
        adapters = []
        
        # DB adapters if database enabled AND connected
        if self.use_database and self.db_controller and self.db_controller.is_connected():
            adapters.extend([self.db_adapter_fov_events, self.db_adapter_cam_events, self.db_adapter_zone_events])
            if self.db_adapter_attr_events:
                adapters.append(self.db_adapter_attr_events)
            if self.db_adapter_system_events:
                adapters.append(self.db_adapter_system_events)
            try:
                self.logger.info(f"DB adapters: {[a.get_event_name() for a in adapters if a]}")
            except Exception:
                pass
        elif self.use_database and self.db_controller:
            # БД была включена, но подключение не удалось - работаем только в JSON режиме
            self.logger.info("Database was enabled but connection failed. Using JSON-only mode for events.")
        
        # JSON adapters - always add for JSON metadata backup (parallel to DB)
        img_dir = self.params.get('database', {}).get('image_dir', 'EvilEyeData')
        for adapter_cls in (JsonAdapterAttributeEvents, JsonAdapterFovEvents, JsonAdapterZoneEvents, JsonAdapterCamEvents, JsonAdapterSystemEvents):
            try:
                adapter = adapter_cls(None)
                adapter.set_params(image_dir=img_dir)
                adapter.init()
                adapter.start()
                adapters.append(adapter)
                try:
                    self.logger.info(f"JSON adapter started: {adapter.get_event_name()} -> image_dir={img_dir}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.logger.error(f"Failed to start JSON adapter {adapter_cls.__name__}: {e}")
                except Exception:
                    pass
        
        return adapters

    def _init_events_processor_unified(self, params):
        """Unified initializer for EventsProcessor for both DB and JSON modes."""
        adapters = self._get_event_adapters()
        db_ctrl = self.db_controller if (self.use_database and self.db_controller) else None
        self.events_processor = EventsProcessor(adapters, db_ctrl)
        self.events_processor.set_params(**params)
        self.events_processor.init()
        # Wire UI callback for online signalization
        try:
            self.events_processor.set_ui_callback(self._on_event_signalization)
        except Exception:
            pass

    def _on_event_signalization(self, source_id: int, object_id: int, event_name: str, is_on: bool, bbox_px: list | None = None):
        """Relay event signalization to main window (per source)."""
        try:
            with self._preview_events_lock:
                source_events = self._preview_active_events_by_source.setdefault(source_id, {})
                key = (object_id, event_name)
                if is_on:
                    source_events[key] = {
                        "object_id": object_id,
                        "event_name": event_name,
                        "bbox_px": bbox_px,
                    }
                else:
                    source_events.pop(key, None)
                    if not source_events:
                        self._preview_active_events_by_source.pop(source_id, None)
            # Diagnostics logging removed
            # Route directly via visualizer
            # Visualizer имеет метод set_event_state в классе, поэтому прямой вызов безопасен
            if self.visualizer:
                self.visualizer.set_event_state(source_id, object_id, event_name, is_on, bbox_px)
        except Exception:
            pass
    
    def _init_event_recording(self, params):
        """Initialize event-based recording components (EventBuffer and EventRecorder)."""
        try:
            from evileye.video_recorder.recording_params import RecordingParams
            from evileye.video_recorder.event_buffer import EventBuffer
            from evileye.video_recorder.event_recorder import EventRecorder
            from evileye.video_recorder.recorder_base import SourceMeta
            
            # Load recording parameters
            self.recording_params = RecordingParams.from_config(params)
            
            # Override out_dir with database.image_dir if available (always use image_dir as base)
            # Resolve relative paths relative to working directory, keep absolute paths as-is
            db_image_dir = (((params or {}).get('database', {}) or {}).get('image_dir')) or 'EvilEyeData'
            image_dir_path = Path(db_image_dir)
            if image_dir_path.is_absolute():
                self.recording_params.out_dir = str(image_dir_path)
            else:
                # Resolve relative path relative to current working directory
                self.recording_params.out_dir = str(image_dir_path.resolve())
            self.logger.info(f"Event recording out_dir set to database.image_dir: {self.recording_params.out_dir}")

            # Pre-validate out_dir early to avoid capture init failures / reconnect log flood.
            # If path is not writable/available (e.g. missing mount), disable recording and continue.
            try:
                ok, reason = self.recording_params.check_out_dir_writable()
                if not ok:
                    # Disable both event and continuous recording (global params)
                    self.recording_params.enabled = False
                    self.recording_params.continuous_recording_enabled = False
                    self.recording_params.event_recording_enabled = False
                    self.logger.warning(
                        f"Recording disabled because out_dir is not writable/available: {self.recording_params.out_dir} "
                        f"(reason: {reason})"
                    )
            except Exception:
                # Never block controller init on validation errors
                pass
            
            # `enabled` is a master switch; event recording must be explicitly enabled.
            if not (self.recording_params.enabled and self.recording_params.event_recording_enabled):
                self.logger.info("Event-based recording is disabled")
                return
            
            # Get sources from pipeline
            # PipelineBase определяет get_sources как абстрактный метод, поэтому прямой вызов безопасен
            sources = self.pipeline.get_sources()
            if not sources:
                self.logger.warning("No sources found, event recording disabled")
                return
            
            # Initialize EventBuffer and EventRecorder for each source
            max_buffer_duration = self.recording_params.event_pre_seconds + self.recording_params.event_post_seconds + 5.0  # 5s margin
            
            for source in sources:
                # VideoCaptureBase инициализирует source_ids в __init__, поэтому прямой доступ безопасен
                if not source.source_ids:
                    continue
                
                # Get source metadata
                source_id = source.source_ids[0] if source.source_ids else 0
                # VideoCaptureBase инициализирует source_names в __init__, поэтому прямой доступ безопасен
                source_name = source.source_names[0] if source.source_names else f"source_{source_id}"
                
                # Get FPS for buffer
                buffer_fps = self.recording_params.event_buffer_fps
                if buffer_fps is None:
                    # Defaulting to full source FPS makes EventBuffer extremely memory-hungry
                    # because it stores full-frame numpy copies. Cap it by default.
                    try:
                        import os as _os
                        max_buf_fps = float(_os.environ.get('EVILEYE_EVENT_BUFFER_FPS_MAX', '5') or 5.0)
                    except Exception:
                        max_buf_fps = 5.0
                    try:
                        src_fps = float(source.source_fps) if source.source_fps else 25.0
                    except Exception:
                        src_fps = 25.0
                    buffer_fps = min(src_fps, max_buf_fps)
                
                # Create EventBuffer
                event_buffer = EventBuffer(max_buffer_duration, buffer_fps)
                self.event_buffers[source_id] = event_buffer
                
                # Create SourceMeta for EventRecorder
                # VideoCaptureBase инициализирует все эти атрибуты в __init__, поэтому прямой доступ безопасен
                source_meta = SourceMeta(
                    source_name=source_name,
                    source_address=source.source_address,
                    source_type=str(source.source_type) if source.source_type else 'unknown',
                    width=None,  # VideoCaptureBase не инициализирует width/height в __init__, используем None
                    height=None,
                    fps=buffer_fps,
                    username=source.username,
                    password=source.password,
                    source_names=source.source_names,
                    source_ids=source.source_ids,
                )
                
                # Create EventRecorder
                event_recorder = EventRecorder(source_meta, self.recording_params, event_buffer)
                self.event_recorders[source_id] = event_recorder
                
                self.logger.info(f"Initialized event recording for source {source_id} ({source_name}): "
                               f"buffer_duration={max_buffer_duration}s, fps={buffer_fps}")
            
            # Set callback for EventsProcessor
            if self.events_processor:
                self.events_processor.set_event_recording_callback(self._on_event_recording)
                self.logger.info("Event recording callback registered with EventsProcessor")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize event recording: {e}", exc_info=True)
            # Clear partial initialization
            self.event_buffers.clear()
            self.event_recorders.clear()
    
    def _init_system_diagnostics(self) -> None:
        """Initialize system diagnostics and memory monitoring."""
        try:
            # Find latest debug log file
            from pathlib import Path
            import glob
            logs_dir = Path("logs")
            if logs_dir.exists():
                log_files = sorted(glob.glob(str(logs_dir / "*_evileye_debug.log")), reverse=True)
                log_file = log_files[0] if log_files else None
            else:
                log_file = None
            
            # Create memory monitor
            self.memory_monitor = MemoryMonitor(
                check_interval=30.0,
                leak_threshold_mb=50.0,
                leak_window_samples=20,
                auto_cleanup=True
            )
            
            # Create system diagnostics
            self.system_diagnostics = SystemDiagnostics(
                log_file=log_file,
                check_interval=30.0,
                auto_fix=True
            )
            
            # Set callbacks
            self.system_diagnostics.set_pipeline_getter(lambda: self.pipeline)
            self.system_diagnostics.set_event_buffer_getter(lambda: self.event_buffers)
            self.system_diagnostics.set_memory_monitor(self.memory_monitor)
            
            # Add cleanup callback to memory monitor
            def cleanup_callback():
                """Cleanup callback for memory monitor."""
                # Force GC
                gc.collect()
                # Clear old frames from event buffers if they're too large
                for source_id, buffer in self.event_buffers.items():
                    if buffer and buffer.size() > 500:
                        removed = buffer.clear_old_frames(older_than_seconds=buffer.max_duration_seconds / 2)
                        if removed > 0:
                            self.logger.info(f"Memory cleanup: cleared {removed} frames from EventBuffer for source {source_id}")
            
            self.memory_monitor.add_cleanup_callback(cleanup_callback)
            
            self.logger.info("System diagnostics and memory monitoring initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize system diagnostics: {e}", exc_info=True)
            self.system_diagnostics = None
            self.memory_monitor = None
    
    def _on_event_recording(self, event_id: int, event_name: str, event_timestamp: float, 
                           source_id: int, is_on: bool, bbox: list | None = None):
        """Callback for event-based recording from EventsProcessor.
        
        Also stores video path in event object if available, and in event_video_paths dict.
        """
        try:
            if source_id not in self.event_recorders:
                return
            
            event_recorder = self.event_recorders[source_id]
            
            # Convert timestamp to float (seconds) if it's datetime.datetime
            if isinstance(event_timestamp, datetime.datetime):
                event_timestamp = event_timestamp.timestamp()
            elif not isinstance(event_timestamp, (int, float)):
                # Try to convert to float
                try:
                    event_timestamp = float(event_timestamp)
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid timestamp type for event {event_id}: {type(event_timestamp)}")
                    return
            
            if is_on:
                # Event started - start recording
                if not event_recorder.is_recording():
                    success, relative_video_path = event_recorder.start_event_recording(
                        event_id, event_name, event_timestamp, source_id, bbox
                    )
                    if success and relative_video_path:
                        # Store video path for this event_id
                        self.event_video_paths[event_id] = relative_video_path
                        self.logger.debug(f"Stored video path for event {event_id}: {relative_video_path}")
                        
                        # Try to store video path in event object if available
                        if self.events_processor:
                            # Find event in long_term_events
                            for event_type, events_list in self.events_processor.long_term_events.items():
                                for event in events_list:
                                    if event.event_id == event_id:
                                        # Store video path based on event type
                                        if event_name == 'ZoneEvent':
                                            event.video_path_entered = relative_video_path
                                        elif event_name == 'AttributeEvent':
                                            event.video_path_found = relative_video_path
                                        elif event_name == 'FOVEvent':
                                            event.video_path = relative_video_path
                                        self.logger.debug(f"Stored video path in event object {event_id}: {relative_video_path}")
                                        break
            else:
                # Event ended - stop recording
                if event_recorder.is_recording():
                    video_path = event_recorder.stop_event_recording()
                    # If video was deleted due to small size, remove from dict
                    if video_path is None and event_id in self.event_video_paths:
                        del self.event_video_paths[event_id]
                        self.logger.debug(f"Removed video path for event {event_id} (file deleted)")
                    elif video_path is not None:
                        # Update video path for finished events (e.g., video_path_left for ZoneEvent)
                        if self.events_processor:
                            # Find event in finished_events or long_term_events
                            for event_type, events_list in list(self.events_processor.finished_events.items()) + list(self.events_processor.long_term_events.items()):
                                for event in events_list:
                                    if event.event_id == event_id:
                                        # Store video path for finished event based on event type
                                        if event_name == 'ZoneEvent':
                                            event.video_path_left = self.event_video_paths.get(event_id)
                                        elif event_name == 'AttributeEvent':
                                            event.video_path_finished = self.event_video_paths.get(event_id)
                                        elif event_name == 'FOVEvent':
                                            event.video_path_lost = self.event_video_paths.get(event_id)
                                        break
        except Exception as e:
            try:
                self.logger.error(f"Error in event recording callback: {e}", exc_info=True)
            except Exception:
                pass

    def _init_visualizer(self, params):
        # Инициализация визуализатора через VisualizationService
        self.visualizer = self._visualization_service.initialize_visualizer(
            params=params,
            pyqt_slots=self.pyqt_slots,
            pyqt_signals=self.pyqt_signals,
            source_id_name_table=self.source_id_name_table,
            source_video_duration=self.source_video_duration,
            class_mapping=self.class_mapping,
        )
        # If persistent zones display requested, push existing zones to threads immediately
        try:
            vis_wants_zones = bool(self.visualizer.get_params().get('display_zones', False))
        except Exception:
            vis_wants_zones = False
        if vis_wants_zones:
            try:
                zones_cfg = (((self.params or {}).get('events_detectors', {}) or {}).get('ZoneEventsDetector', {}) or {}).get('sources', {})
                sources_zones = {}
                if isinstance(zones_cfg, dict):
                    for k, zone_list in zones_cfg.items():
                        try:
                            sid = int(k)
                        except Exception:
                            continue
                        sources_zones[sid] = []
                        for coords in (zone_list or []):
                            # expected: ['poly', coords, None]
                            if isinstance(coords, list) and coords:
                                sources_zones[sid].append(['poly', coords, None])
                if sources_zones:
                    try:
                        self.pyqt_signals['display_zones_signal'].emit(sources_zones)
                    except Exception:
                        pass
            except Exception:
                pass

    def collect_memory_consumption(self):
        total_memory_usage = 0
        # Calculate memory consumption for pipeline components
        self.pipeline.calc_memory_consumption()
        total_memory_usage += self.pipeline.memory_measure_results

        self.obj_handler.calc_memory_consumption()
        comp_debug_info = self.obj_handler.insert_debug_info_by_id(self.debug_info.setdefault("obj_handler", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.events_processor.calc_memory_consumption()
        comp_debug_info = self.events_processor.insert_debug_info_by_id(self.debug_info.setdefault("events_processor", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.events_detectors_controller.calc_memory_consumption()
        comp_debug_info = self.events_detectors_controller.insert_debug_info_by_id(self.debug_info.setdefault("events_detectors_controller", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.cam_events_detector.calc_memory_consumption()
        comp_debug_info = self.cam_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("cam_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.fov_events_detector.calc_memory_consumption()
        comp_debug_info = self.fov_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("fov_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.zone_events_detector.calc_memory_consumption()
        comp_debug_info = self.zone_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("zone_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        if self.visualizer:
            self.visualizer.calc_memory_consumption()
            comp_debug_info = self.visualizer.insert_debug_info_by_id(self.debug_info.setdefault("visualizer", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

        # Only collect database memory if database is enabled
        if self.use_database and self.db_controller:
            self.db_controller.calc_memory_consumption()
            comp_debug_info = self.db_controller.insert_debug_info_by_id(self.debug_info.setdefault("db_controller", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

            self.db_adapter_obj.calc_memory_consumption()
            comp_debug_info = self.db_adapter_obj.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_obj", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

            self.db_adapter_cam_events.calc_memory_consumption()
            comp_debug_info = self.db_adapter_cam_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_cam_events", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

            self.db_adapter_fov_events.calc_memory_consumption()
            comp_debug_info = self.db_adapter_fov_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_fov_events", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

            self.db_adapter_zone_events.calc_memory_consumption()
            comp_debug_info = self.db_adapter_zone_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_zone_events", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

        self.debug_info["controller"] = dict()
        self.debug_info["controller"]["timestamp"] = datetime.datetime.now()
        self.debug_info["controller"]["total_memory_usage_mb"] = total_memory_usage/(1024.0*1024.0)

    def _discover_pipeline_classes(self):
        """Discover all pipeline classes from packages and current directory"""
        pipeline_classes = {}
        
        # Search in evileye.pipelines package
        try:
            pipelines_module = importlib.import_module('evileye.pipelines')
            for name, obj in inspect.getmembers(pipelines_module):
                # __bases__ - встроенный атрибут всех классов Python, getattr безопаснее и быстрее inspect.getmro
                bases = getattr(obj, '__bases__', None)
                if (inspect.isclass(obj) and 
                    bases and 
                    any('Pipeline' in base.__name__ for base in bases)):
                    pipeline_classes[name] = obj
        except ImportError as e:
            self.logger.warning(f"Failed to import evileye.pipelines: {e}")
        
        # Search in current working directory pipelines folder
        current_dir = Path.cwd()
        pipelines_dir = current_dir / "pipelines"
        if pipelines_dir.exists() and pipelines_dir.is_dir():
            try:
                # Add current directory to Python path
                import sys
                sys.path.insert(0, str(current_dir))
                
                # Try to import pipelines module from current directory
                pipelines_module = importlib.import_module('pipelines')
                for name, obj in inspect.getmembers(pipelines_module):
                    # __bases__ - встроенный атрибут всех классов Python, getattr безопаснее и быстрее inspect.getmro
                    bases = getattr(obj, '__bases__', None)
                    if (inspect.isclass(obj) and 
                        bases and 
                        any('Pipeline' in base.__name__ for base in bases)):
                        pipeline_classes[name] = obj
                
                # Remove from path
                sys.path.pop(0)
            except ImportError as e:
                self.logger.warning(f"Failed to import local pipelines: {e}")
        
        return pipeline_classes
    
    def _create_pipeline_instance(self, pipeline_class_name: str):
        """Create pipeline instance by class name"""
        pipeline_classes = self._discover_pipeline_classes()
        
        if pipeline_class_name not in pipeline_classes:
            available_classes = list(pipeline_classes.keys())
            raise ValueError(f"Pipeline class '{pipeline_class_name}' not found. Available classes: {available_classes}")
        
        pipeline_class = pipeline_classes[pipeline_class_name]
        return pipeline_class()
    
    def get_available_pipeline_classes(self):
        """Get list of available pipeline classes"""
        return list(self._discover_pipeline_classes().keys())
    
    def get_class_name(self, class_id: int) -> str:
        """Get class name from class ID using class_mapping"""
        for name, cid in self.class_mapping.items():
            if cid == class_id:
                return name
        return f"class_{class_id}"
    
    def get_class_id(self, class_name: str) -> int:
        """Get class ID from class name using class_mapping"""
        return self.class_mapping.get(class_name, -1)
    
    def get_class_names_list(self) -> list:
        """Get list of class names in order of their IDs"""
        sorted_classes = sorted(self.class_mapping.items(), key=lambda x: x[1])
        return [name for name, _ in sorted_classes]
    
    def update_class_mapping_from_detectors(self):
        """Update class_mapping from all detectors in the pipeline using ClassManager"""
        if not self.pipeline:
            return
            
        # Get all detectors from pipeline
        detectors = []
        # PipelineProcessors инициализирует processors в __init__, поэтому прямой доступ безопасен
        if hasattr(self.pipeline, 'processors') and self.pipeline.processors:
            for processor in self.pipeline.processors:
                # ProcessorFrame имеет метод get_processors, проверяем наличие метода
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        # ObjectDetectorBase имеет метод get_model_class_mapping, проверяем наличие метода
                        if hasattr(proc, 'get_model_class_mapping'):
                            detectors.append(proc)
        
        # Collect class mappings from all detectors using ClassManager
        for detector in detectors:
            mapping = detector.get_model_class_mapping()
            if mapping:
                detector_name = detector.__class__.__name__
                success = self.class_manager.add_class_mapping(mapping, detector_name)
                if not success:
                    self.logger.warning(f"Conflicts detected when adding mapping from {detector_name}")
                
                # CRITICAL: Force update classes after getting model mapping
                # Проверяем наличие метода, так как не все детекторы могут его иметь
                if hasattr(detector, '_update_classes_after_model_loading'):
                    detector._update_classes_after_model_loading()
            else:
                # Model not loaded yet, try to get mapping (this will trigger late update if model is loaded)
                detector.get_model_class_mapping()
        
        # Update controller's class_mapping from ClassManager
        if self.class_manager.class_mapping:
            self.class_mapping = self.class_manager.get_class_mapping()
            self.logger.info(f"Updated controller class_mapping with {len(self.class_mapping)} classes from {len(detectors)} detectors")
            
            # Update visualizer if available
            if self.visualizer:
                self.visualizer.class_mapping = self.class_mapping
                self.logger.info("Updated visualizer class_mapping")
            
            # Set class manager for all detectors
            for detector in detectors:
                # Проверяем наличие метода, так как не все детекторы могут его иметь
                if hasattr(detector, 'set_class_manager'):
                    detector.set_class_manager(self.class_manager)
            
            # Report conflicts if any
            if self.class_manager.has_conflicts():
                self.logger.warning("Class mapping conflicts detected:")
                for conflict in self.class_manager.get_conflicts():
                    self.logger.warning(f"   - {conflict}")
                self.logger.info("Using first occurrence for each class name/ID pair.")
        else:
            self.logger.warning("Class mappings not found in detectors")
            
        # Schedule periodic check for late model loading
        self._schedule_periodic_class_update()
    
    def _schedule_periodic_class_update(self):
        """Schedule periodic check for classes update after model loading"""
        import threading
        import time
        
        def periodic_check():
            """Periodically check and update classes"""
            # Check once per second up to configured timeout
            max_attempts = max(1, int(self.model_loading_timeout_sec))
            attempt = 0
            
            while attempt < max_attempts:
                time.sleep(1)  # Wait 1 second
                attempt += 1
                
                # Check if we have detectors
                if not self.pipeline:
                    continue
                    
                # Get all detectors from pipeline
                detectors = []
                # PipelineProcessors инициализирует processors в __init__, поэтому прямой доступ безопасен
                if hasattr(self.pipeline, 'processors') and self.pipeline.processors:
                    for processor in self.pipeline.processors:
                        # ProcessorFrame имеет метод get_processors, проверяем наличие метода
                        if hasattr(processor, 'get_processors'):
                            for proc in processor.get_processors():
                                # ObjectDetectorBase имеет метод get_model_class_mapping, проверяем наличие метода
                                if hasattr(proc, 'get_model_class_mapping'):
                                    detectors.append(proc)
                
                # Check each detector
                updated = False
                for detector in detectors:
                    mapping = detector.get_model_class_mapping()
                    # Проверяем наличие метода, так как не все детекторы могут его иметь
                    if mapping and hasattr(detector, '_check_and_update_classes_if_needed'):
                        detector._check_and_update_classes_if_needed()
                        updated = True
                
                if updated:
                    self.logger.info("Late model loading detected, classes updated")
                    break
                    
            if attempt >= max_attempts:
                self.logger.warning("Model loading timeout, some classes may not update")
        
        # Start periodic check in background thread
        check_thread = threading.Thread(target=periodic_check, daemon=True)
        check_thread.start()
    
    def create_config(self, num_sources: int, pipeline_class: str | None, 
                     source_type: str = 'video_file', detector_params: dict | None = None,
                     tracker_params: dict | None = None, database_params: dict | None = None):
        """Create configuration with specified pipeline class and optional parameters"""
        self.init({})

        # Create pipeline instance if class name is provided
        if pipeline_class:
            try:
                self.pipeline = self._create_pipeline_instance(pipeline_class)
                self.logger.info(f"Created pipeline instance: {pipeline_class}")
            except Exception as e:
                self.logger.warning(f"Failed to create pipeline '{pipeline_class}': {e}")
                self.logger.info("Using default pipeline")
                self.pipeline = PipelineSurveillance()
        else:
            # Use default pipeline
            self.pipeline = PipelineSurveillance()

        if self.pipeline:
            self.pipeline.generate_default_structure(num_sources)

        # Apply source type configuration
        # Проверяем наличие атрибута sources, так как не все pipeline могут его иметь
        if num_sources > 0 and hasattr(self.pipeline, 'sources') and self.pipeline.sources:
            source_type_mapping = {
                'video_file': {'source': 'video_file', 'camera': 'path/to/video.mp4'},
                'ip_camera': {'source': 'ip_camera', 'camera': 'rtsp://user:password@ip:port/stream'},
                'device': {'source': 'device', 'camera': 0}
            }
            
            if source_type in source_type_mapping:
                source_config = source_type_mapping[source_type]
                for source in self.pipeline.sources:
                    # VideoCaptureBase имеет source_type и source_address, проверяем наличие
                    if hasattr(source, 'source_type') and hasattr(source, 'source_address'):
                        # Устанавливаем через set_params, а не напрямую
                        # Это требует рефакторинга, но пока оставляем как есть
                        self.logger.info(f"Applied source type '{source_type}' to source")

        # Apply detector parameters if provided
        # PipelineProcessors инициализирует processors в __init__, поэтому прямой доступ безопасен
        if detector_params and hasattr(self.pipeline, 'processors') and self.pipeline.processors:
            for processor in self.pipeline.processors:
                # ProcessorFrame имеет метод get_processors, проверяем наличие метода
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        # ProcessorBase определяет get_name как метод, поэтому прямой вызов безопасен
                        if 'detector' in proc.get_name().lower():
                            try:
                                proc.set_params(**detector_params)
                                self.logger.info(f"Applied detector parameters: {detector_params}")
                            except Exception as e:
                                self.logger.warning(f"Failed to apply detector parameters: {e}")

        # Apply tracker parameters if provided
        # PipelineProcessors инициализирует processors в __init__, поэтому прямой доступ безопасен
        if tracker_params and hasattr(self.pipeline, 'processors') and self.pipeline.processors:
            for processor in self.pipeline.processors:
                # ProcessorFrame имеет метод get_processors, проверяем наличие метода
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        # ProcessorBase определяет get_name как метод, поэтому прямой вызов безопасен
                        if 'tracker' in proc.get_name().lower():
                            try:
                                proc.set_params(**tracker_params)
                                self.logger.info(f"Applied tracker parameters: {tracker_params}")
                            except Exception as e:
                                self.logger.warning(f"Failed to apply tracker parameters: {e}")

        config_data = {}
        self.update_params()
        
        # Get parameters safely, avoiding non-serializable objects
        config_data = self.get_params()

        # Apply database parameters (only safe parameters, no credentials)
        if database_params:
            # Only store safe database parameters (no credentials)
            safe_db_params = {}
            safe_keys = ['image_dir', 'preview_width', 'preview_height']
            for key in safe_keys:
                if key in database_params:
                    safe_db_params[key] = database_params[key]
            
            # Set default safe values if not provided
            if not safe_db_params:
                safe_db_params = {
                    "image_dir": "EvilEyeData",
                    "preview_width": 300,
                    "preview_height": 150
                }
            
            # Replace entire database section with only safe parameters
            config_data['database'] = safe_db_params
            self.logger.info(f"Applied safe database parameters: {safe_db_params}")
        else:
            # If no database_params provided, ensure database section contains only safe parameters
            if 'database' in config_data:
                # Keep only safe parameters, remove credentials
                safe_db_params = {
                    "image_dir": "EvilEyeData",
                    "preview_width": 300,
                    "preview_height": 150
                }
                config_data['database'] = safe_db_params
                self.logger.info(f"Removed database credentials, kept only safe parameters: {safe_db_params}")

        config_data['visualizer'] = {}
        if num_sources and num_sources > 0:
            num_width = math.ceil(math.sqrt(num_sources))
            num_height = math.ceil(num_sources / num_width)

            config_data['visualizer']['num_width'] = num_width
            config_data['visualizer']['num_height'] = num_height
        else:
            config_data['visualizer']['num_width'] = 1
            config_data['visualizer']['num_height'] = 1

        config_data['visualizer']['visual_buffer_num_frames'] = 10
        if num_sources and num_sources > 0:
            config_data['visualizer']['source_ids'] = list(range(num_sources))
            config_data['visualizer']['fps'] = [5]*num_sources
        else:
            config_data['visualizer']['source_ids'] = []
            config_data['visualizer']['fps'] = []
        config_data['visualizer']['gui_enabled'] = False
        config_data['visualizer']['show_debug_info'] = True
        config_data['visualizer']['objects_journal_enabled'] = True

        self.stop()
        self.release()
        return config_data
    # def _save_video_duration(self):
    #     self.db_controller.update_video_dur(self.source_video_duration)
