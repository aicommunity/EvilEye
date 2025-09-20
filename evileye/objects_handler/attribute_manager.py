from __future__ import annotations

from typing import Dict, Optional

from .attribute_state import AttributeState


class AttributeManager:
    """
    Агрегирует атрибуты для первичных объектов по track_id.
    Реализует FSM: none -> exists -> lost -> none.
    Порогирование по confidence и суммарному времени (min/confirm).
    """

    def __init__(self, thresholds_conf: Dict[str, float] = None, thresholds_time: Dict[str, Dict[str, int]] = None, ema_alpha: float = 0.6):
        self._attr_by_track: Dict[int, Dict[str, AttributeState]] = {}
        self._thr_conf = thresholds_conf or {}
        self._thr_time = thresholds_time or {}  # {attr: {min_time_ms, confirm_time_ms}}
        self._ema_alpha = ema_alpha
        self._primary_by_name = []
        self._primary_by_id = []
        self._configured_attrs = []

    def get_states(self, track_id: int) -> Dict[str, AttributeState]:
        return self._attr_by_track.get(track_id, {})

    def update(self, track_id: int, attr_name: str, detected: bool, confidence: float, now_ts: float, dt_ms: int):
        states = self._attr_by_track.setdefault(track_id, {})
        state = states.get(attr_name)
        if state is None:
            state = states[attr_name] = AttributeState(name=attr_name)

        thr_conf = self._thr_conf.get(attr_name, 0.5)
        thr_times = self._thr_time.get(attr_name, {"min_time_ms": 0, "confirm_time_ms": 0})
        min_time_ms = int(thr_times.get("min_time_ms", 0))
        confirm_time_ms = int(thr_times.get("confirm_time_ms", 0))

        # Сглаживание доверия - только при детекции
        if detected:
            state.confidence_smooth = self._ema(confidence, state.confidence_smooth)
        # Если не обнаружен - не изменяем confidence_smooth

        if detected and confidence >= thr_conf:
            state.frames_present += 1
            state.total_time_ms += dt_ms
            state.no_detect_time_ms = 0
            state.last_seen_ts = now_ts

            if state.state == 'none':
                if state.total_time_ms >= confirm_time_ms:
                    state.state = 'exists'
                    state.enter_count += 1
                    state.enter_ts = now_ts
            elif state.state == 'lost':
                # В lost накапливаем снова; подтверждаем при достижении confirm_time_ms
                if state.total_time_ms >= confirm_time_ms:
                    state.state = 'exists'
                    state.enter_count += 1
                    state.enter_ts = now_ts
            # exists остаётся exists
        else:
            state.no_detect_time_ms += dt_ms
            if state.state == 'exists' and state.no_detect_time_ms >= min_time_ms:
                state.state = 'lost'
            elif state.state == 'lost' and state.no_detect_time_ms >= confirm_time_ms:
                state.state = 'none'
                state.reset_presence()

    def remove_track(self, track_id: int):
        if track_id in self._attr_by_track:
            del self._attr_by_track[track_id]

    def _ema(self, new_value: float, prev_value: float) -> float:
        return self._ema_alpha * new_value + (1.0 - self._ema_alpha) * prev_value
    
    def set_params(self, attributes_detection: Dict):
        """Set parameters from attributes_detection config"""
        if not attributes_detection:
            return
            
        self._primary_by_name = attributes_detection.get('primary_by_name', [])
        self._primary_by_id = attributes_detection.get('primary_by_id', [])
        
        classifier_config = attributes_detection.get('classifier', {})
        self._thr_conf = classifier_config.get('confidence_thresholds', {})
        self._thr_time = classifier_config.get('time_thresholds', {})
        self._ema_alpha = classifier_config.get('ema_alpha', 0.7)
        
        # Store configured attributes for default creation
        self._configured_attrs = classifier_config.get('attrs', [])


