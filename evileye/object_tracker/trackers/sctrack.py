import numpy as np
from collections import deque
from typing import List
from ultralytics.trackers.bot_sort import BOTrack
from .basetrack import TrackState
from .byte_tracker import STrack


class SCTrack(STrack):
    features: List[deque[np.ndarray]]
    feat_history: int
    curr_feat: np.ndarray | None
    smooth_feat: np.ndarray | None

    def __init__(self, tlwh, score, cls, feat=None, feat_history=50):
        super().__init__(tlwh, score, cls)
        self.smooth_feat = None
        self.curr_feat = None
        self.feat_history = feat_history
        
        if feat is not None:
            self.update_features(feat)
        self.features = []
        self.alpha = 0.9
    
    def update(self, new_track: 'SCTrack', frame_id: int):
        """Updates the YOLOv8 instance with new track information and the current frame ID."""
        if new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)
        super().update(new_track, frame_id)

    def update_features(self, feat: List[np.ndarray], ov: bool = False):
        """Update the feature vector and apply exponential moving average smoothing.

        :param feat: Array (NxE)
        """

        # Normalize
        for f in feat:
            f /= np.linalg.norm(f)
        
        # Update currect feature
        self.curr_feat = feat
        if len(self.curr_feat) == 2:
            pass

        # Update smooth feature
        if self.smooth_feat is None:
            self.smooth_feat = feat
        elif ov is False:
            self.smooth_feat = [
                self.alpha * self.smooth_feat[i] + (1 - self.alpha) * feat[i] 
                for i in range(len(feat))
            ]
        for i in range(len(feat)):
            self.smooth_feat[i] /= np.linalg.norm(self.smooth_feat[i])

        # Update features deque
        for i in range(len(feat)):
            if i >= len(self.features):
                self.features.append(deque([], maxlen=self.feat_history))

            self.features[i].append(feat[i])
    
    def predict(self):
        """Predicts the object's future state using the Kalman filter to update its mean and covariance."""
        mean_state = self.mean.copy()
        if self.state != TrackState.Tracked:
            mean_state[6] = 0
            mean_state[7] = 0

        self.mean, self.covariance = self.kalman_filter.predict(mean_state, self.covariance)

    def re_activate(self, new_track, frame_id, new_id=False):
        """Reactivates a track with updated features and optionally assigns a new ID."""
        if new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)
        super().re_activate(new_track, frame_id, new_id)

    @property
    def tlwh(self):
        """Returns the current bounding box position in `(top left x, top left y, width, height)` format."""
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[:2] -= ret[2:] / 2
        return ret

    @staticmethod
    def multi_predict(stracks):
        """Predicts the mean and covariance for multiple object tracks using a shared Kalman filter."""
        if len(stracks) <= 0:
            return
        multi_mean = np.asarray([st.mean.copy() for st in stracks])
        multi_covariance = np.asarray([st.covariance for st in stracks])
        for i, st in enumerate(stracks):
            if st.state != TrackState.Tracked:
                multi_mean[i][6] = 0
                multi_mean[i][7] = 0
        multi_mean, multi_covariance = BOTrack.shared_kalman.multi_predict(multi_mean, multi_covariance)
        for i, (mean, cov) in enumerate(zip(multi_mean, multi_covariance)):
            stracks[i].mean = mean
            stracks[i].covariance = cov

    def convert_coords(self, tlwh):
        """Converts tlwh bounding box coordinates to xywh format."""
        return self.tlwh_to_xywh(tlwh)

    @staticmethod
    def tlwh_to_xywh(tlwh):
        """Convert bounding box from tlwh (top-left-width-height) to xywh (center-x-center-y-width-height) format."""
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        return ret
