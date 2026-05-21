"""Processing-loop helpers extracted from Controller (TD-010)."""

from __future__ import annotations

import datetime
import pprint
import time

from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_tracker.tracking_results import TrackingResultList, TrackingResult
from evileye.core.tracking_dto import ensure_tracking_result_list
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList
from evileye.visualization_modules.preview_render import PreviewRenderContext

class ControllerProcessingMixin:
    def _build_preview_render_context(self, frame, objects_by_source: dict[int, ObjectResultList]) -> PreviewRenderContext:
        source_id = getattr(frame, "source_id", None)
        frame_id = getattr(frame, "frame_id", None)
        object_list = objects_by_source.get(source_id, ObjectResultList())
        track_info = object_list.find_objects_by_frame_id(frame_id, use_history=False) if object_list else []
        if not track_info and object_list:
            try:
                track_info = object_list.find_objects_near_frame_id(frame_id, max_delta=1, use_history=True)
            except Exception:
                track_info = []
        if not track_info and object_list:
            # In multiprocess mode preview may fall back to fresher source frames while
            # tracker/objects handler still holds results for a slightly older frame_id.
            # For web preview it is better to render the latest known tracks than to show
            # a completely unannotated frame.
            track_info = list(getattr(object_list, "objects", []) or [])
        event_entries = self._get_preview_event_entries(source_id)
        event_cfg = self._get_preview_event_cfg()
        vis_cfg = self._get_preview_visualizer_cfg()
        event_enabled = bool(event_cfg.get("event_signal_enabled", False))
        event_color = tuple(event_cfg.get("event_signal_color", [255, 0, 0]))
        source_duration_msecs = self.source_video_duration.get(source_id)
        if source_duration_msecs is None:
            source_duration_msecs = getattr(frame, "source_video_duration", None)
            if source_id is not None and source_duration_msecs is not None:
                try:
                    self.source_video_duration[source_id] = float(source_duration_msecs)
                except Exception:
                    pass
        return PreviewRenderContext(
            source_name=self.source_id_name_table.get(source_id, f"src{source_id}"),
            source_duration_msecs=source_duration_msecs,
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
            tracking_result = ensure_tracking_result_list(tracking_result)
                
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
    def _extract_track_ids(self, data) -> tuple[set[int], int]:
        track_ids: set[int] = set()
        missing_track_object = 0
        tracks = None
        try:
            tracks = getattr(data, "tracks", None)
        except Exception:
            tracks = None
        if tracks is None and isinstance(data, dict):
            tracks = data.get("tracks")
        if tracks is None:
            dto_obj = data.get("tracking_dto") if isinstance(data, dict) else getattr(data, "tracking_dto", None)
            tracks = getattr(dto_obj, "tracks", None) if dto_obj is not None else None
        for tr in (tracks or []):
            try:
                tid = getattr(tr, "track_id", None)
                if tid is None and isinstance(tr, dict):
                    tid = tr.get("track_id")
                if tid is not None:
                    track_ids.add(int(tid))
                tdata = getattr(tr, "tracking_data", None)
                if tdata is None and isinstance(tr, dict):
                    tdata = tr.get("tracking_data", {})
                if isinstance(tdata, dict) and "track_object" not in tdata:
                    missing_track_object += 1
            except Exception:
                continue
        return track_ids, missing_track_object
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
    def _get_preview_event_cfg(self) -> dict:
        vis_cfg = self._get_preview_visualizer_cfg()
        nested = vis_cfg.get("event_signalization", {})
        if isinstance(nested, dict) and nested:
            return nested
        return vis_cfg
    def _get_preview_event_entries(self, source_id: int) -> list[dict]:
        with self._preview_events_lock:
            return list((self._preview_active_events_by_source.get(source_id) or {}).values())
    def _get_preview_visualizer_cfg(self) -> dict:
        if isinstance(self.params, dict):
            cfg = self.params.get("visualizer", {})
            if isinstance(cfg, dict):
                return cfg
        return {}
    def _has_non_empty_payload(self, data) -> bool:
        """Return True when tracking/detection payload contains objects."""
        if data is None:
            return False
        try:
            tracks = getattr(data, "tracks", None)
            if tracks is not None:
                return bool(tracks)
            detections = getattr(data, "detections", None)
            if detections is not None:
                return bool(detections)
        except Exception:
            pass
        if isinstance(data, dict):
            if "tracks" in data:
                try:
                    return bool(data.get("tracks"))
                except Exception:
                    return False
            if "detections" in data:
                try:
                    return bool(data.get("detections"))
                except Exception:
                    return False
            dto_obj = data.get("tracking_dto")
            if dto_obj is not None:
                try:
                    return bool(getattr(dto_obj, "tracks", None))
                except Exception:
                    return False
            return False
        dto_obj = getattr(data, "tracking_dto", None)
        if dto_obj is not None:
            try:
                return bool(getattr(dto_obj, "tracks", None))
            except Exception:
                return False
        return False
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
                    has_payload = self._has_non_empty_payload(data)
                    heartbeat_every = max(1, int(self.obj_handler_empty_heartbeat_every or 3))
                    should_send = True
                    if not has_payload and source_id is not None and frame_id is not None:
                        last_sent = self._obj_handler_last_sent_frame_id.get(source_id)
                        if last_sent is not None and (frame_id - last_sent) < heartbeat_every:
                            should_send = False
                    if has_payload and source_id is not None:
                        self._update_track_continuity_diag(source_id, data)
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
    def _update_track_continuity_diag(self, source_id: int, data) -> None:
        try:
            track_ids, missing_track_object = self._extract_track_ids(data)
            if missing_track_object > 0:
                self._track_payload_without_track_object += missing_track_object
            prev = self._track_continuity_last_ids.get(source_id, set())
            if prev and track_ids and prev != track_ids:
                self._track_continuity_switches += 1
            if track_ids:
                self._track_continuity_last_ids[source_id] = track_ids
        except Exception:
            return
