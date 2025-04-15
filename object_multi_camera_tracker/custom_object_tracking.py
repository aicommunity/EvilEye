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
from ultralytics.trackers.bot_sort import BOTrack, TrackState
from object_tracker.trackers.bot_sort import BOTSORT, Encoder
from object_tracker.trackers.cfg.utils import read_cfg
from object_detector.object_detection_base import DetectionResult
from object_detector.object_detection_base import DetectionResultList
from object_multi_camera_tracker.object_tracking_base import TrackingResult
from object_multi_camera_tracker.object_tracking_base import TrackingResultList
from object_multi_camera_tracker.object_tracking_base import ObjectMultiCameraTrackingBase
from dataclasses import dataclass


class ObjectMultiCameraTracking(ObjectMultiCameraTrackingBase):

    def __init__(self):
        super().__init__()

    def init_impl(self):
        self.tracker = MultiCameraTracker()
        return True

    def release_impl(self):
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        pass

    def default(self):
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            sc_track_results: List[Tuple[TrackingResultList, np.ndarray]] = self.queue_in.get()
            if sc_track_results is None:
                break

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
            self.queue_out.put(list(zip(tracks_infos, images)))

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
    

class MCTrack:
    _count = 0
    
    def __init__(
            self, 
            sc_tracks: Dict[int, BOTrack]):
        
        self.global_track_id = None
        self.sc_tracks = sc_tracks
        self.features = deque([], maxlen=200)

    def update(self, new_track: 'MCTrack'):
        for cam_id, sct in new_track.sc_tracks.items():
            self.sc_tracks[cam_id] = sct

    def update_features(self, overlaps: Dict[int, List[int]] = None):
        overlaps = overlaps or {}

        for cam_id, t in self.sc_tracks.items():
            if t.curr_feat is None:
                continue

            if t.track_id in overlaps.get(cam_id, []) and len(self.features) > 0:
                continue
            
            self.features.append(t.curr_feat)

    def activate(self):
        self.global_track_id = self.next_id()

    @property
    def is_activated(self):
        return self.global_track_id is not None
    
    @property
    def is_removed(self):
        sc_track_list = list(self.sc_tracks.values())
        _is_removed = all(t.state == TrackState.Removed for t in sc_track_list)
        return _is_removed

    @property
    def smooth_feat(self) -> np.ndarray:
        smooth_feat = np.mean(self.features, axis=0)
        return smooth_feat

    def next_id(self):
        cnt = MCTrack._count
        MCTrack._count += 1
        return cnt


class MultiCameraTracker:
    def __init__(
            self, 
            clustering_threshold: float = 0.5):
        
        """
        :param num_cameras: Количество камер.
        :param clustering_threshold: Порог для иерархической кластеризации (0.7 по умолчанию).
        """
        self.clustering_threshold = clustering_threshold
        
        self.global_mc_tracks: List[MCTrack] = []
        self.next_global_id = 0

    def update(self, sct_tracks: List[BOTrack]) -> List[MCTrack]:
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
        for t in self.global_mc_tracks:
            t.update_features()

        
        #Выполняем иерархическую кластеризацию
        mct_tracks = self._hierarchical_clustering(sct_tracks)

        overlaps = self._find_overlaps(sct_tracks)
        for t in mct_tracks:
            t.update_features(overlaps)

        # Шаг 3: Обновляем глобальные треки
        self._update_global_tracks(mct_tracks)

        activated_global_tracks = [x for x in self.global_mc_tracks if x.is_activated]
        return activated_global_tracks
    
    def _find_overlaps(self, sct_tracks: List[List[BOTrack]]) -> List[List[bool]]:
        """Находит пересечения между треками на разных камерах."""
        overlaps = {} # cam_id -> track_id
        for cam_id, tracks in enumerate(sct_tracks):
            local_overlaps = check_overlaps(tracks)
            overlaps[cam_id] = []
            for i, track in enumerate(tracks):
                if not local_overlaps[i]:
                    continue
            
                overlaps[cam_id].append(track.track_id)
            
        return overlaps
    
    def _hierarchical_clustering(self, sct_tracks: List[List[BOTrack]]) -> List[MCTrack]:
        # Извлеекаем признаки из треков
        features = []
        tracks = []
        cam_ids = []
        for cam_id, ts in enumerate(sct_tracks):
            for track in ts:
                features.append(track.smooth_feat)
                tracks.append(track)
                cam_ids.append(cam_id)
        
        if len(features) == 0:
            return []
        
        # Составляем матрицу расстояний
        features = np.array(features)
        appearance_distances = self._create_appearance_distance_matrix(features)
        distances = self._fix_distance_matrix(appearance_distances, cam_ids)
        
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
        mct_tracks = [MCTrack(track_clusters[label]) for label in track_clusters]
   
        return mct_tracks

    def _update_global_tracks(self, mct_tracks: List[MCTrack]):
        # self._exclude_removed_global_tracks()
        mct_tracks, global_matches = self._assign_by_track_id(mct_tracks)
        mct_tracks = self._assign_by_features(mct_tracks, global_matches)
        self._init_new_global_tracks(mct_tracks)

    def _exclude_removed_global_tracks(self):
        filtered_mct_tracks = []
        for t in self.global_mc_tracks:
            if t.is_removed:
                continue
            filtered_mct_tracks.append(t)
        
        self.global_mc_tracks = filtered_mct_tracks

    def _assign_by_track_id(
            self, 
            mct_tracks: List[MCTrack]
        ) -> Tuple[List[MCTrack], List[int]]:
        
        global_matches = []
        mct_matches = []

        # Go through all tracks and find matches
        for i, global_track in enumerate(self.global_mc_tracks):                    
            global_track_ids = set((c, t.track_id) for c, t in global_track.sc_tracks.items())
            
            for j, mct_track in enumerate(mct_tracks):
                if j in mct_matches:
                    continue

                mct_track_ids = set((c, t.track_id) for c, t in mct_track.sc_tracks.items())
                if mct_track_ids != global_track_ids:
                    continue
                
                # Update global track
                global_track.update(mct_track)
        
                mct_matches.append(j)
                global_matches.append(i)
                break
        
        for i, global_track in enumerate(self.global_mc_tracks):
            if i not in global_matches:
                global_track.sc_tracks = {}

        unmatched_mct_tracks = [mct_tracks[i] for i in range(len(mct_tracks)) if i not in mct_matches]
        return unmatched_mct_tracks, global_matches
    
    def _assign_by_features(self, mct_tracks: List[MCTrack], global_matches: List[int]) -> List[MCTrack]:
        
        unmatched_global_ids = [i for i in range(len(self.global_mc_tracks)) if i not in global_matches]
        if len(unmatched_global_ids) == 0 or len(mct_tracks) == 0:
            return mct_tracks
        
        # Составляем матрицу расстояний между глобальными треками и новыми локальными треками
        global_features = np.array([self.global_mc_tracks[i].smooth_feat for i in unmatched_global_ids])
        new_features = np.array([t.smooth_feat for t in mct_tracks])
        distances = 1 - cosine_similarity(global_features, new_features)

        # Применяем венгерский алгоритм
        row_ind, col_ind = linear_sum_assignment(distances)
        pass
        for i, j in zip(row_ind, col_ind):
            if distances[i, j] > self.clustering_threshold:
                continue
            global_id = unmatched_global_ids[i]
            self.global_mc_tracks[global_id].update(mct_tracks[j])
        
        unmatched_mct_tracks = [mct_tracks[j] for j in range(len(mct_tracks)) if j not in col_ind]
        return unmatched_mct_tracks
                
    def _init_new_global_tracks(self, mct_tracks: List[MCTrack]):
        used_sc_tracks = {}
        for global_track in self.global_mc_tracks:
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
            self.global_mc_tracks.append(mct_track)
            pass

    def _create_appearance_distance_matrix(self, appearance_features: np.ndarray) -> np.ndarray:
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
