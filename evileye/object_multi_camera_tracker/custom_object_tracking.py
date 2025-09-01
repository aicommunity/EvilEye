from typing import Dict, List, Tuple
import datetime
from time import sleep
from collections import deque

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
from .object_multicam_tracking_base import TrackingResult
from .object_multicam_tracking_base import TrackingResultList
from .object_multicam_tracking_base import ObjectMultiCameraTrackingBase
from .mctrack import MCTrack
from ..object_tracker.trackers.sctrack import SCTrack
from dataclasses import dataclass
from pympler import asizeof
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectMultiCameraTracking")
class ObjectMultiCameraTracking(ObjectMultiCameraTrackingBase):

    def __init__(self):
        super().__init__()
        self.num_cameras = 0
        self.encoders = None
        self.tracker = None

    def init_impl(self, **kwargs):
        sources_ids = self.params.get("source_ids", [])
        encoders = kwargs.get('encoders', None)
        self.tracker = MultiCameraTracker(len(sources_ids), encoders)
        return True

    def release_impl(self):
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        super().set_params_impl()

    def get_params_impl(self):
        params = super().get_params_impl()
        return params

    def default(self):
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            if self.queue_in.qsize() <= len(self.source_ids):
                continue

            sc_track_results = []
            for i in range(0,len(self.source_ids)):
                sc_track_results.append(self.queue_in.get())
            if sc_track_results is None:
                continue

            if self.enable == False:
                for track_info in sc_track_results:
                    self.queue_out.put(track_info)
                continue

            sc_tracks: List[List[BOTrack]] = []
            images = []
            track_infos = []
            for results in sc_track_results:
                track_info, image = results
                images.append(image)
                track_infos.append(track_info)
                tracks = []
                for t in track_info.tracks:
                    tracks.append(t.tracking_data["track_object"])
                sc_tracks.append(tracks)

            mc_tracks = self.tracker.update(sc_tracks)
            tracks_infos = self._create_tracks_info(track_infos, mc_tracks)
            for track_info in zip(tracks_infos, images):
                self.queue_out.put(track_info)

    def _parse_det_info(self, det_info: DetectionResultList) -> tuple:
        cam_id = det_info.source_id
        objects = det_info.detections

        bboxes_xyxy = []
        confidences = []
        class_ids = []

        for obj in objects:
            bboxes_xyxy.append(obj.bounding_box)
            confidences.append(obj.confidence)
            class_ids.append(obj.class_id)

        bboxes_xyxy = np.array(bboxes_xyxy).reshape(-1, 4)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)

        bboxes_xyxy = np.array(bboxes_xyxy)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)

        # Convert XYXY input coordinates to XcYcWH
        bboxes_xcycwh = bboxes_xyxy.astype('float64')
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
        for t in mc_tracks:
            global_id = t.global_track_id
            for cam_id, track in t.sc_tracks.items():
                
                track_id = track.track_id
                src_track_number = [t.track_id for t in sc_track_results[cam_id].tracks].index(track_id)
                
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
        
        #Выполняем иерархическую кластеризацию
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
        overlaps = {} # cam_id -> track_id
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
