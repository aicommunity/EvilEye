from typing import Dict, List, Tuple
import datetime
from collections import deque
import os
from timeit import default_timer as timer
import threading
from queue import Empty

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import box
from shapely.ops import unary_union
import scipy.spatial.distance as ssd
from scipy.cluster.hierarchy import linkage, fcluster
from sklearn.metrics.pairwise import cosine_similarity
from ..object_tracker.trackers.basetrack import TrackState
from ultralytics.trackers.bot_sort import BOTrack
from ..object_tracker.trackers.track_encoder import TrackEncoder
from ..object_tracker.trackers.cfg.utils import read_cfg
from ..object_detector.object_detection_base import DetectionResult
from ..object_detector.object_detection_base import DetectionResultList
from ..object_tracker.tracking_results import TrackingResult, TrackingResultList
from .object_multicam_tracking_base import ObjectMultiCameraTrackingBase
from .mctrack import MCTrack
from ..object_tracker.trackers.sctrack import SCTrack
from dataclasses import dataclass
from pympler import asizeof
from ..core.base_class import EvilEyeBase
from ..core.frame import Frame
from ..core.ipc_contracts import BatchMeta
from ..core.tracking_dto import TrackingDTO, TrackingObjectDTO

MC_MAX_FRAME_ID_SPREAD = 3


def _sync_tracking_result_with_frame(
    track_info: TrackingResultList,
    frame: Frame,
) -> None:
    if track_info.source_id is None:
        track_info.source_id = frame.source_id
    if track_info.frame_id is None:
        track_info.frame_id = frame.frame_id


@EvilEyeBase.register("ObjectMultiCameraTracking")
class ObjectMultiCameraTracking(ObjectMultiCameraTrackingBase):

    def __init__(self):
        super().__init__()
        self.num_cameras = 0
        self.encoders = None
        self.tracker = None
        self._perf_diag_env = os.getenv("EVILEYE_PERF_DIAG", "").strip().lower() in {"1", "true", "yes", "on"}
        self._perf_diag_every = int(os.getenv("EVILEYE_PERF_DIAG_EVERY", "60") or "60")
        self._perf_diag_counter = 0
        self._diag_waiting_for_batch = 0
        self._diag_batches = 0
        self._diag_emitted = 0
        self._diag_empty_mc_tracks = 0
        self._diag_queue_snapshots = []
        self._diag_last_batch = []
        self._diag_replaced_same_source = 0
        self._diag_partial_batches = 0
        self._pending_by_source = {}
        # Last emitted frame_id per camera to avoid re-emitting identical batches.
        self._last_emitted_frame_id_by_source: dict[int, int | None] = {}
        # Throttle emissions to avoid excessive CPU usage when inputs update fast.
        self._last_emit_time_sec: float = 0.0

        # Per-source diagnostics:
        # - how often inputs are received by MCTracker (from trackers stage)
        # - how often MCTracker emits a new frame_id vs repeats for each source
        self._diag_queue_in_gets_by_source: dict[int, int] = {}
        self._diag_frame_id_updates_by_source: dict[int, int] = {}
        self._diag_frame_id_repeats_by_source: dict[int, int] = {}
        self._pipeline_tick_batch = True
        self._diag_tick_batch_skip = 0

    def start(self):
        self.run_flag = True
        if self._pipeline_tick_batch:
            return
        super().start()

    def init_impl(self, **kwargs) -> bool:
        sources_ids = self.params.get("source_ids", [])
        encoders = kwargs.get('encoders', None)
        self.tracker = MultiCameraTracker(len(sources_ids), encoders)
        return True

    def release_impl(self):
        self.tracker = None

    def reset_impl(self) -> None:
        self.tracker.reset()
        self._pending_by_source = {}
        self._last_emitted_frame_id_by_source = {}
        self._last_emit_time_sec = 0.0
        self._diag_queue_in_gets_by_source = {}
        self._diag_frame_id_updates_by_source = {}
        self._diag_frame_id_repeats_by_source = {}

    def set_params_impl(self):
        super().set_params_impl()

    def get_params_impl(self):
        params = super().get_params_impl()
        return params

    def default(self):
        self.params.clear()

    def process_tick_batch(
        self,
        batch: dict[int, tuple[TrackingResultList, Frame]],
    ) -> list[tuple[TrackingResultList, Frame]]:
        """Process one pipeline tick: all cameras must be present and frame-aligned."""
        if not batch:
            return []

        for track_info, frame in batch.values():
            if not isinstance(track_info, TrackingResultList) or not isinstance(frame, Frame):
                self._diag_tick_batch_skip += 1
                return []
            _sync_tracking_result_with_frame(track_info, frame)

        for sid in self.source_ids:
            if sid not in batch:
                if self._perf_diag_env:
                    self._diag_partial_batches += 1
                self._diag_tick_batch_skip += 1
                return []

        frame_id_by_source: dict[int, int | None] = {}
        frame_ids: list[int] = []
        for sid in self.source_ids:
            track_info, image = batch[sid]
            frame_id = track_info.frame_id
            if frame_id is None:
                frame_id = image.frame_id
            frame_id_by_source[sid] = frame_id
            if frame_id is None:
                self._diag_tick_batch_skip += 1
                return []
            frame_ids.append(int(frame_id))

        if max(frame_ids) - min(frame_ids) > MC_MAX_FRAME_ID_SPREAD:
            self._diag_tick_batch_skip += 1
            return []

        new_sources_count = 0
        for sid in self.source_ids:
            frame_id = frame_id_by_source[sid]
            if frame_id != self._last_emitted_frame_id_by_source.get(sid):
                new_sources_count += 1
        if new_sources_count < 1:
            self._diag_tick_batch_skip += 1
            return []

        sc_track_results = [batch[sid] for sid in self.source_ids]
        is_partial = False
        outputs: list[tuple[TrackingResultList, Frame]] = []

        if not self.enable:
            for track_info, image in sc_track_results:
                item = (track_info, image)
                self._attach_batch_meta(item, frame_id_by_source, is_partial=is_partial)
                outputs.append(item)
            for sid in self.source_ids:
                self._last_emitted_frame_id_by_source[sid] = frame_id_by_source[sid]
            if self._perf_diag_env:
                self._diag_batches += 1
                self._diag_emitted += len(outputs)
            return outputs

        sc_tracks: List[List[BOTrack]] = []
        images = []
        track_infos = []
        for track_info, image in sc_track_results:
            images.append(image)
            track_infos.append(track_info)
            tracks = [t.tracking_data["track_object"] for t in track_info.tracks]
            sc_tracks.append(tracks)

        mc_tracks = self.tracker.update(sc_tracks)
        if self._perf_diag_env and not mc_tracks:
            self._diag_empty_mc_tracks += 1
        tracks_infos = self._create_tracks_info(track_infos, mc_tracks)
        for track_info, image in zip(tracks_infos, images):
            item = (track_info, image)
            self._attach_batch_meta(item, frame_id_by_source, is_partial=is_partial)
            outputs.append(item)

        for sid in self.source_ids:
            self._last_emitted_frame_id_by_source[sid] = frame_id_by_source[sid]

        if self._perf_diag_env:
            self._diag_batches += 1
            self._diag_emitted += len(outputs)
        return outputs

    def _process_impl(self):
        while self.run_flag:
            loop_start = timer()
            queue_size_before = self.queue_in.qsize()
            latest_by_source = {}
            # Детерминированное окно обновления latest_by_source.
            # Ранее попытки с env-заданием ухудшали частоту выдачи в GUI.
            collect_deadline_sec = 0.15
            collect_deadline = loop_start + collect_deadline_sec
            while self.run_flag and timer() < collect_deadline:
                timeout = max(0.01, min(0.05, collect_deadline - timer()))
                try:
                    result = self.queue_in.get(timeout=timeout)
                except Empty:
                    if len(latest_by_source) >= len(self.source_ids):
                        break
                    continue
                if result is None:
                    continue
                try:
                    track_info, image = result
                    # Контракт данных может иногда приходить с пустым `track_info.source_id`,
                    # при этом `image.source_id` заполнен. Чтобы не "терять" камеру в MC-батчинге,
                    # пробуем сначала `track_info.source_id`, затем fallback на `image.source_id`.
                    source_id = getattr(track_info, "source_id", None)
                    if source_id is None:
                        source_id = getattr(image, "source_id", None)
                        # Синхронизируем поля в объекте результата, чтобы downstream (ObjectsHandler/Visualizer)
                        # использовал корректные ключи.
                        if source_id is not None:
                            try:
                                track_info.source_id = source_id
                            except Exception:
                                pass
                    # Аналогично подстрахуемся от пропущенного frame_id.
                    track_frame_id = getattr(track_info, "frame_id", None)
                    image_frame_id = getattr(image, "frame_id", None)
                    if track_frame_id is None and image_frame_id is not None:
                        try:
                            track_info.frame_id = image_frame_id
                        except Exception:
                            pass
                except Exception:
                    source_id = None
                if source_id is None:
                    continue
                if self._perf_diag_env:
                    self._diag_queue_in_gets_by_source[source_id] = (
                            self._diag_queue_in_gets_by_source.get(source_id, 0) + 1
                    )
                if source_id in latest_by_source and self._perf_diag_env:
                    self._diag_replaced_same_source += 1
                latest_by_source[source_id] = result
                if len(latest_by_source) >= len(self.source_ids):
                    break

            for source_id, result in latest_by_source.items():
                if source_id in self._pending_by_source and self._perf_diag_env:
                    self._diag_replaced_same_source += 1
                self._pending_by_source[source_id] = result

            sc_track_results = [self._pending_by_source[source_id] for source_id in self.source_ids if
                                source_id in self._pending_by_source]

            num_sources = len(self.source_ids) or 1
            min_sources_for_batch = max(1, (num_sources // 2) + 1)
            is_partial = len(sc_track_results) < min_sources_for_batch
            if is_partial:
                if self._perf_diag_env:
                    self._diag_waiting_for_batch += 1
                    self._diag_partial_batches += 1
                continue
            # Emit only if enough cameras have new frame_id since last emission.
            # This reduces frame_id repeats (duplicate metadata) in downstream GUI.
            new_sources_count = 0
            frame_id_by_source: dict[int, int | None] = {}
            for source_id in self.source_ids:
                try:
                    track_info, image = self._pending_by_source[source_id]
                    frame_id = getattr(track_info, "frame_id", None)
                    if frame_id is None:
                        frame_id = getattr(image, "frame_id", None)
                except Exception:
                    frame_id = None
                frame_id_by_source[source_id] = frame_id
                prev_frame_id = self._last_emitted_frame_id_by_source.get(source_id)
                if frame_id != prev_frame_id:
                    new_sources_count += 1

            # K-out-of-N rule (deterministic):
            # Emit only when a strict majority of cameras have new frame_id.
            # This avoids emitting batches dominated by repeated (stale) frame_id.
            num_sources = len(self.source_ids) or 1
            required_new_sources = max(1, (num_sources // 2) + 1)

            if new_sources_count < required_new_sources:
                continue

            # Minimal interval to avoid excessive emits under high update rates.
            min_emit_interval_sec = 0.12
            now_sec = float(timer())
            if self._last_emit_time_sec > 0.0 and (now_sec - self._last_emit_time_sec) < min_emit_interval_sec:
                continue
            self._last_emit_time_sec = now_sec

            if self._perf_diag_env:
                self._diag_batches += 1

            if not self.enable:
                for track_info in sc_track_results:
                    self._attach_batch_meta(track_info, frame_id_by_source, is_partial=is_partial)
                    self._put_out_drop_oldest(track_info)
                for source_id in self.source_ids:
                    new_frame_id = frame_id_by_source.get(source_id)
                    if self._perf_diag_env:
                        prev_frame_id = self._last_emitted_frame_id_by_source.get(source_id)
                        if new_frame_id != prev_frame_id:
                            self._diag_frame_id_updates_by_source[source_id] = (
                                    self._diag_frame_id_updates_by_source.get(source_id, 0) + 1
                            )
                        else:
                            self._diag_frame_id_repeats_by_source[source_id] = (
                                    self._diag_frame_id_repeats_by_source.get(source_id, 0) + 1
                            )
                    self._last_emitted_frame_id_by_source[source_id] = new_frame_id
                continue

            sc_tracks: List[List[BOTrack]] = []
            images = []
            track_infos = []
            batch_diag = []
            for results in sc_track_results:
                track_info, image = results
                images.append(image)
                track_infos.append(track_info)
                tracks = [t.tracking_data["track_object"] for t in track_info.tracks]
                sc_tracks.append(tracks)
                try:
                    batch_diag.append(
                        {
                            "source_id": getattr(track_info, "source_id", None),
                            "frame_id": getattr(track_info, "frame_id", None),
                            "tracks": len(getattr(track_info, "tracks", []) or []),
                        }
                    )
                except Exception:
                    pass

            mc_tracks = self.tracker.update(sc_tracks)
            if self._perf_diag_env and not mc_tracks:
                self._diag_empty_mc_tracks += 1
            tracks_infos = self._create_tracks_info(track_infos, mc_tracks)
            for track_info in zip(tracks_infos, images):
                self._attach_batch_meta(track_info, frame_id_by_source, is_partial=is_partial)
                self._put_out_drop_oldest(track_info)

            # Remember emitted frame_ids for next-loop deduplication.
            for source_id in self.source_ids:
                new_frame_id = frame_id_by_source.get(source_id)
                if self._perf_diag_env:
                    prev_frame_id = self._last_emitted_frame_id_by_source.get(source_id)
                    if new_frame_id != prev_frame_id:
                        self._diag_frame_id_updates_by_source[source_id] = (
                                self._diag_frame_id_updates_by_source.get(source_id, 0) + 1
                        )
                    else:
                        self._diag_frame_id_repeats_by_source[source_id] = (
                                self._diag_frame_id_repeats_by_source.get(source_id, 0) + 1
                        )
                self._last_emitted_frame_id_by_source[source_id] = new_frame_id

            if self._perf_diag_env:
                self._diag_emitted += len(tracks_infos)
                self._diag_last_batch = batch_diag
                try:
                    self._diag_queue_snapshots.append(
                        {
                            "in_q_before": queue_size_before,
                            "out_q": self.queue_out.qsize(),
                            "mc_tracks": len(mc_tracks),
                            "emitted": len(tracks_infos),
                            "batch": batch_diag,
                            "loop_ms": (timer() - loop_start) * 1000.0,
                        }
                    )
                    if len(self._diag_queue_snapshots) > 5:
                        self._diag_queue_snapshots = self._diag_queue_snapshots[-5:]
                except Exception:
                    pass
                self._perf_diag_counter += 1
                every = max(1, int(self._perf_diag_every or 60))
                if (self._perf_diag_counter % every) == 0:
                    try:
                        self.logger.info(
                            "PerfDiag(MCTracker): loops=%d, waits=%d, batches=%d, partial=%d, tick_skip=%d, replaced=%d, empty_mc=%d, emitted=%d, in_q=%s, out_q=%s, last_batch=%s, queue_in_gets=%s, frame_updates=%s, frame_repeats=%s",
                            self._perf_diag_counter,
                            self._diag_waiting_for_batch,
                            self._diag_batches,
                            self._diag_partial_batches,
                            self._diag_tick_batch_skip,
                            self._diag_replaced_same_source,
                            self._diag_empty_mc_tracks,
                            self._diag_emitted,
                            self.queue_in.qsize(),
                            self.queue_out.qsize(),
                            self._diag_last_batch,
                            self._diag_queue_in_gets_by_source,
                            self._diag_frame_id_updates_by_source,
                            self._diag_frame_id_repeats_by_source,
                        )
                        # Reset interval counters after we publish stats.
                        self._diag_queue_in_gets_by_source = {}
                        self._diag_frame_id_updates_by_source = {}
                        self._diag_frame_id_repeats_by_source = {}
                    except Exception:
                        pass

    def _attach_batch_meta(self, track_info_with_image, frame_id_by_source, is_partial: bool):
        """Attach lightweight batch metadata for downstream diagnostics."""
        try:
            track_info, image = track_info_with_image
        except Exception:
            return
        try:
            source_id = getattr(track_info, "source_id", None)
            frame_id = getattr(track_info, "frame_id", None)
            if frame_id is None and source_id in frame_id_by_source:
                frame_id = frame_id_by_source.get(source_id)
            frame_ref = getattr(image, "frame_handle", None)
            batch_meta = {
                "payload_version": 1,
                "source_id": source_id,
                "frame_id": frame_id,
                "batch_age_ms": 0.0,
                "is_partial": bool(is_partial),
            }
            setattr(track_info, "batch_meta", batch_meta)
            setattr(
                track_info,
                "batch_meta_obj",
                BatchMeta(
                    payload_version=1,
                    source_id=source_id,
                    frame_id=frame_id,
                    batch_age_ms=0.0,
                    is_partial=bool(is_partial),
                ),
            )
            if frame_ref is not None:
                setattr(track_info, "frame_ref", frame_ref)
            setattr(track_info, "tracking_dto", self._build_tracking_dto(track_info))
        except Exception:
            return

    def _build_tracking_dto(self, track_info):
        dto = TrackingDTO(
            source_id=getattr(track_info, "source_id", None),
            frame_id=getattr(track_info, "frame_id", None),
            payload_version=1,
            tracks=[],
        )
        for tr in getattr(track_info, "tracks", []) or []:
            tracking_data = getattr(tr, "tracking_data", {}) or {}
            dto.tracks.append(
                TrackingObjectDTO(
                    track_id=int(getattr(tr, "track_id", 0)),
                    class_id=int(getattr(tr, "class_id", -1)),
                    confidence=float(getattr(tr, "confidence", 0.0)),
                    bbox_xyxy=[float(x) for x in (getattr(tr, "bounding_box", []) or [])],
                    global_id=tracking_data.get("global_id"),
                )
            )
        return dto

    def _parse_det_info(self, det_info: DetectionResultList) -> tuple:
        cam_id = det_info.source_id
        objects = det_info.detections

        if len(objects) == 0:
            return (
                cam_id,
                np.empty((0, 4), dtype=np.float64),
                np.empty((0,), dtype=np.float32),
                np.empty((0,), dtype=np.int32),
            )

        num_objects = len(objects)
        bboxes_xyxy = np.empty((num_objects, 4), dtype=np.float64)
        confidences = np.empty(num_objects, dtype=np.float32)
        class_ids = np.empty(num_objects, dtype=np.int32)

        for i, obj in enumerate(objects):
            bboxes_xyxy[i] = obj.bounding_box
            confidences[i] = obj.confidence
            class_ids[i] = obj.class_id

        # Convert XYXY input coordinates to XcYcWH
        bboxes_xcycwh = bboxes_xyxy.copy()
        bboxes_xcycwh[:, 2] -= bboxes_xcycwh[:, 0]
        bboxes_xcycwh[:, 3] -= bboxes_xcycwh[:, 1]
        bboxes_xcycwh[:, 0] += bboxes_xcycwh[:, 2] / 2
        bboxes_xcycwh[:, 1] += bboxes_xcycwh[:, 3] / 2

        return cam_id, bboxes_xcycwh, confidences, class_ids

    def _create_tracks_info(
            self,
            sc_track_results: List[TrackingResultList],
            mc_tracks: List['MCTrack']) -> List[TrackingResultList]:

        sc_tracks_by_cam = [list() for i in range(len(sc_track_results))]
        # O(1) lookup: local track_id -> index in sc_track_results[cam_id].tracks
        track_id_to_index = {
            cam_id: {t.track_id: idx for idx, t in enumerate(track_list.tracks)}
            for cam_id, track_list in enumerate(sc_track_results)
        }
        for t in mc_tracks:
            global_id = t.global_track_id
            for cam_id, track in t.sc_tracks.items():

                track_id = track.track_id
                src_track_number = track_id_to_index.get(cam_id, {}).get(track_id)

                if src_track_number is None:
                    continue

                src_track = sc_track_results[cam_id].tracks[src_track_number]
                src_track.tracking_data['global_id'] = global_id
                sc_tracks_by_cam[cam_id].append(src_track)

        for i, results in enumerate(sc_track_results):
            results.tracks = sc_tracks_by_cam[i]

        return sc_track_results


class MultiCameraTracker:
    def __init__(
            self,
            num_cameras: int,
            encoders: List[TrackEncoder],
            clustering_threshold: float = 0.5,
            confident_age: int = 0,
            exclude_overlap: bool = False,
            include_lost_tracks: bool = False,
            overlap_threshold: float = 0.5,
            max_track_len: int = 50):

        """
        :param num_cameras: Количество камер.
        :param encoder: Экстрактор признаков.
        :param clustering_threshold: Порог для иерархической кластеризации (0.7 по умолчанию).
        """
        self.num_cameras = num_cameras
        self.encoders = encoders
        self.exclude_overlap = exclude_overlap
        self.overlap_threshold = overlap_threshold
        self.confident_age = confident_age
        self.max_track_length = max_track_len
        self.clustering_threshold = clustering_threshold
        self.include_lost_tracks = include_lost_tracks

        self.mct_tracks: List[MCTrack] = []
        self.next_global_id = 0

    def update(self, sct_tracks: List[List[SCTrack]]) -> List[MCTrack]:
        """
        Обновляет трекинг по всем камерам и возвращает треки с глобальными идентификаторами.
        
        :param detections: Список результатов детекции для каждой камеры (List[Boxes]).
        :param image: Текущий кадр (numpy.ndarray).
        :return: Список numpy массивов для каждой камеры с глобальными идентификаторами.
        """

        # Если ни одна камера не обнаружила объекты, возвращаем пустой список
        if all(len(x) == 0 for x in sct_tracks):
            return []

        # Обновляем признаки глобальных треков
        for t in self.mct_tracks:
            t.update_features()

        # Выполняем иерархическую кластеризацию
        mct_tracks = self._hierarchical_clustering(sct_tracks)

        # Обновляем признаки глобальных треков
        overlaps = None
        if self.exclude_overlap:
            overlaps = self._find_overlaps(sct_tracks)
        for t in mct_tracks:
            t.update_features(overlaps)

        # Обновляем глобальные треки
        self._update_global_tracks(mct_tracks)

        activated_global_tracks = [x for x in self.mct_tracks if x.is_activated]

        return activated_global_tracks

    def _find_overlaps(self, sct_tracks: List[List[BOTrack]]) -> List[List[bool]]:
        """Находит пересечения между треками на разных камерах."""
        overlaps = {}  # cam_id -> track_id
        for cam_id, tracks in enumerate(sct_tracks):
            local_overlaps = check_overlaps(tracks, self.overlap_threshold)
            overlaps[cam_id] = []
            for i, track in enumerate(tracks):
                if not local_overlaps[i]:
                    continue

                overlaps[cam_id].append(track.track_id)

        return overlaps

    def _hierarchical_clustering(self, sct_tracks: List[List[BOTrack]]) -> List[MCTrack]:
        # Извлеекаем признаки из треков
        features = [[] for encoder in self.encoders]
        tracks = []
        cam_ids = []
        for cam_id, ts in enumerate(sct_tracks):
            for track in ts:
                if track.smooth_feat is not None:
                    for i in range(len(self.encoders)):
                        features[i].append(track.smooth_feat[i])
                tracks.append(track)
                cam_ids.append(cam_id)

        if len(features) == 0 or len(features[0]) == 0:
            return []

        # Составляем матрицу расстояний
        dists = []
        for feats in features:
            dist = self._create_distance_matrix(np.array(feats))
            dists.append(dist)

        distances = np.mean(dists, axis=0)
        distances = self._fix_distance_matrix(distances, cam_ids)
        # LOGGER.debug(f"Hierchical clustering. Distance matrix:\n{distances}")

        # Иерархическая кластеризация
        if len(distances) == 1:
            cluster_labels = [0]
        else:
            dist_array = ssd.squareform(distances)
            clustering = linkage(dist_array, method='average')
            clustering = np.clip(clustering, 0, None)
            cluster_labels = fcluster(clustering, t=self.clustering_threshold, criterion='distance')

        # Cгруппировать локальные треки по кластерам
        track_clusters = {}
        for i, label in enumerate(cluster_labels):
            if label not in track_clusters:
                track_clusters[label] = {}
            track_clusters[label][cam_ids[i]] = tracks[i]

        # Создать MCTrack объекты
        mct_tracks = [
            MCTrack(track_clusters[label], confident_age=self.confident_age, maxlen=self.max_track_length)
            for label in track_clusters
        ]
        # LOGGER.debug(f"Found clusters:\n{[t.sc_tracks for t in mct_tracks]}")

        return mct_tracks

    def _update_global_tracks(self, mct_tracks: List[MCTrack]):
        mct_tracks, global_matches = self._assign_by_track_id(mct_tracks)
        mct_tracks, global_matches = self._assign_by_features(mct_tracks, global_matches)

        self._clean_global_tracks(global_matches)
        self._init_new_global_tracks(mct_tracks)

    def _clean_global_tracks(self, global_matches: List[int]):
        matched_sc_track_ids = []
        for i, global_track in enumerate(self.mct_tracks):
            if i not in global_matches:
                continue

            matched_sc_track_ids += [
                t.track_id for i, t in self.mct_tracks[i].sc_tracks.items()
                if t.state == TrackState.Tracked
            ]

        for i, global_track in enumerate(self.mct_tracks):

            if i in global_matches:
                continue

            if not self.include_lost_tracks:
                global_track.sc_tracks = {}
                continue

            for j in list(global_track.sc_tracks.keys()):
                track = global_track.sc_tracks[j]
                if track.state != TrackState.Tracked:
                    continue
                if track.track_id in matched_sc_track_ids:
                    global_track.sc_tracks.pop(j)

    def _exclude_removed_global_tracks(self):
        filtered_mct_tracks = []
        for t in self.mct_tracks:
            if t.is_removed:
                continue
            filtered_mct_tracks.append(t)

        self.mct_tracks = filtered_mct_tracks

    def _assign_by_track_id(
            self,
            mct_tracks: List[MCTrack]
    ) -> Tuple[List[MCTrack], List[int]]:

        global_matches = []
        mct_matches = []

        # Go through all tracks and find matches
        for i, global_track in enumerate(self.mct_tracks):
            global_track_ids = set((c, t.track_id) for c, t in global_track.sc_tracks.items())

            for j, mct_track in enumerate(mct_tracks):
                if j in mct_matches:
                    continue

                mct_track_ids = set((c, t.track_id) for c, t in mct_track.sc_tracks.items())
                if mct_track_ids != global_track_ids:
                    continue

                # Update global track
                global_track.update(mct_track)
                # LOGGER.debug(
                #     f"Global track {global_track.global_track_id} "
                #     f"was updated by track is with values:\n{mct_track.sc_tracks}"
                # )

                mct_matches.append(j)
                global_matches.append(i)
                break

        unmatched_mct_tracks = [mct_tracks[i] for i in range(len(mct_tracks)) if i not in mct_matches]
        # LOGGER.debug(f"Assignment by id, unmatched tracks:\n{[t.sc_tracks for t in unmatched_mct_tracks]}")
        # LOGGER.debug(f"Assignment by id, global matches:\n{global_matches}")
        return unmatched_mct_tracks, global_matches

    def _assign_by_features(self, mct_tracks: List[MCTrack], global_matches: List[int]) -> List[MCTrack]:

        unmatched_global_ids = [i for i in range(len(self.mct_tracks)) if i not in global_matches]
        # LOGGER.debug(f"Assigning by features, unmatched_global_ids:\n{unmatched_global_ids}")
        if len(unmatched_global_ids) == 0 or len(mct_tracks) == 0:
            return mct_tracks, global_matches

        # Составляем матрицу расстояний между глобальными треками и новыми локальными треками
        global_features_list = [
            np.array([self.mct_tracks[i].smooth_feat[j] for i in unmatched_global_ids])
            for j in range(len(self.encoders))
        ]
        new_features_list = [
            np.array([t.smooth_feat[j] for t in mct_tracks])
            for j in range(len(self.encoders))
        ]

        dists = []
        for i in range(len(self.encoders)):
            global_features = global_features_list[i]
            new_features = new_features_list[i]
            dist = 1 - cosine_similarity(global_features, new_features)
            dists.append(dist)

        distances = np.mean(dists, axis=0)
        # LOGGER.debug(f"Assigning by features. Distance matrix:\n{distances}")

        # Применяем венгерский алгоритм
        row_ind, col_ind = linear_sum_assignment(distances)

        for i, j in zip(row_ind, col_ind):
            if distances[i, j] > self.clustering_threshold:
                continue

            global_id = unmatched_global_ids[i]
            self.mct_tracks[global_id].update(mct_tracks[j], self.include_lost_tracks)

            global_matches.append(global_id)
            # LOGGER.debug(
            #     f"Global track {global_id} "
            #     f"was updated by features is with values:\n{mct_tracks[j].sc_tracks}"
            # )

        unmatched_mct_tracks = [mct_tracks[j] for j in range(len(mct_tracks)) if j not in col_ind]
        return unmatched_mct_tracks, global_matches

    def _init_new_global_tracks(self, mct_tracks: List[MCTrack]):
        used_sc_tracks = {}
        for global_track in self.mct_tracks:
            for c, t in global_track.sc_tracks.items():
                if c not in used_sc_tracks:
                    used_sc_tracks[c] = []
                used_sc_tracks[c].append(t.track_id)

        for mct_track in mct_tracks:
            for c in list(mct_track.sc_tracks.keys()):
                if c not in used_sc_tracks:
                    continue
                if mct_track.sc_tracks[c].track_id in used_sc_tracks[c]:
                    mct_track.sc_tracks.pop(c)

            if len(mct_track.sc_tracks) == 0:
                continue

            mct_track.activate()
            # LOGGER.debug(f"Global track {mct_track.global_track_id} was activated with values:\n{mct_track.sc_tracks}")
            self.mct_tracks.append(mct_track)
            pass

    def _create_distance_matrix(self, appearance_features: np.ndarray) -> np.ndarray:
        distances = 1 - cosine_similarity(appearance_features)
        return distances

    def _fix_distance_matrix(self, distances: np.ndarray, cam_ids: List[int]) -> np.ndarray:
        """
        Задать рассотояние между треками, которые принадлежат одной камере, равным np.float32.max,
        чтобы избежать кластеризации треков с одной камер"""

        for i in range(len(distances)):
            for j in range(len(distances)):
                if i == j:
                    distances[i, j] = 0.0
                    continue
                if cam_ids[i] == cam_ids[j]:
                    distances[i, j] = np.finfo(np.float32).max
        return distances

    def reset(self) -> None:
        """Reset the multi-camera tracker to initial state."""
        self.mct_tracks = []
        self.next_global_id = 0


def check_overlaps(tracks: List[BOTrack], overlap_threshold: float = 0.5) -> List[bool]:
    boxes = [box(*track.xyxy) for track in tracks]
    results = []

    for i, current_box in enumerate(boxes):
        other_boxes = [b for j, b in enumerate(boxes) if j != i]
        intersections = [current_box.intersection(b) for b in other_boxes if current_box.intersects(b)]

        # Объединяем все пересечения, чтобы не было двойного счёта
        if intersections:
            total_overlap = unary_union(intersections).area
        else:
            total_overlap = 0.0

        overlap_ratio = total_overlap / current_box.area
        results.append(overlap_ratio > overlap_threshold)

    return results
