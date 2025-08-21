from typing import Dict, List
import numpy as np
from collections import deque
from ..object_tracker.trackers.basetrack import TrackState
from ultralytics.trackers.bot_sort import BOTrack


class MCTrack:
    _count = 0
    sc_tracks: Dict[int, BOTrack]
    
    def __init__(
            self, 
            sc_tracks: Dict[int, BOTrack],
            confident_age: int = 5,
            maxlen: int = 50):
        
        self.global_track_id = None
        self.sc_tracks = sc_tracks
        self.maxlen = maxlen
        self.features = []
        
        self.confident_age = confident_age
        self.confidence_flags = deque([], maxlen=maxlen)
        self.track_ids = deque([], maxlen=maxlen)

    def update(self, new_track: 'MCTrack', include_lost_tracks: bool = False):
        cam_ids = list(set(self.sc_tracks.keys()) | set(new_track.sc_tracks.keys())) 
        
        for cam_id in cam_ids:
            if cam_id in new_track.sc_tracks:
                self.sc_tracks[cam_id] = new_track.sc_tracks[cam_id]
                continue
            
            if not include_lost_tracks:
                self.sc_tracks.pop(cam_id)
                continue
        
            if self.sc_tracks[cam_id].state == TrackState.Tracked:
                self.sc_tracks.pop(cam_id)
        
    def update_features(self, overlaps: Dict[int, List[int]] = None):
        overlaps = overlaps or {}

        for cam_id, t in self.sc_tracks.items():
            if t.curr_feat is None:
                continue

            if t.track_id in overlaps.get(cam_id, []) and len(self.features) > 0:
                continue

            for i, f in enumerate(t.curr_feat):
                if i >= len(self.features):
                    self.features.append(deque([], maxlen=self.maxlen))
                self.features[i].append(f)

            self.track_ids.append(t.track_id)
            is_confident = t.tracklet_len >= self.confident_age
            self.confidence_flags.append(is_confident)

            if not is_confident:
                continue

            cur_conf_flags_ids = np.nonzero(np.array(self.track_ids) == t.track_id)[0] 
            cur_conf_flags = np.array(self.confidence_flags)[cur_conf_flags_ids]
            if cur_conf_flags.min():
                continue

            for i in cur_conf_flags_ids:
                self.confidence_flags[i] = True

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
        has_confident_tracks = np.array(self.confidence_flags).max()

        if not has_confident_tracks:
            smooth_feat = [np.mean(feats, axis=0) for feats in self.features]

        else:   
            smooth_feat = [
                 np.mean(np.array(feats)[self.confidence_flags], axis=0) 
                 for feats in self.features
            ]

        return smooth_feat
    
    @property
    def age(self):
        _age = min(t.tracklet_len for t in self.sc_tracks.values())
        return _age

    @property
    def age(self) -> int:
        if len(self.sc_tracks) == 0:
            return 0
        _age = min(t.tracklet_len for t in self.sc_tracks.values())
        return _age
    
    def next_id(self):
        cnt = MCTrack._count
        MCTrack._count += 1
        return cnt
    

    