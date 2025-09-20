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
            state.total_found_time_ms += dt_ms
            state.no_detect_time_ms = 0
            state.last_seen_ts = now_ts
        else:
            state.no_detect_time_ms += dt_ms
            state.total_lost_time_ms += dt_ms
        
        # Обновляем found_ratio для принятия решений
        total_time = state.total_found_time_ms + state.total_lost_time_ms
        if total_time > 0:
            state.found_ratio = state.total_found_time_ms / total_time
        else:
            state.found_ratio = 0.0
        
        # Принимаем решение о состоянии на основе улучшенной логики
        decision_state = self._calculate_decision_state(state, min_time_ms, confirm_time_ms)
        
        # Обновляем состояние только если оно изменилось
        if state.state != decision_state:
            old_state = state.state
            state.state = decision_state
            
            # Логируем переходы состояний
            if decision_state == 'exists' and old_state != 'exists':
                state.enter_count += 1
                state.enter_ts = now_ts
            elif decision_state == 'none' and old_state != 'none':
                state.reset_presence()

    def remove_track(self, track_id: int):
        if track_id in self._attr_by_track:
            del self._attr_by_track[track_id]

    def _ema(self, new_value: float, prev_value: float) -> float:
        return self._ema_alpha * new_value + (1.0 - self._ema_alpha) * prev_value
    
    def _calculate_decision_state(self, state: 'AttributeState', min_time_ms: int, confirm_time_ms: int) -> str:
        """
        Рассчитывает решение о состоянии атрибута на основе суммарного времени.
        
        Args:
            state: Состояние атрибута
            min_time_ms: Минимальное время для потери
            confirm_time_ms: Время подтверждения
            
        Returns:
            Решение о состоянии: 'none', 'exists', 'lost'
        """
        # Если нет данных - none
        if state.total_found_time_ms + state.total_lost_time_ms == 0:
            return 'none'
        
        # Если недавно обнаружен - exists
        if state.no_detect_time_ms == 0 and state.total_time_ms >= confirm_time_ms:
            return 'exists'
        
        # Если недавно потерян - lost
        if state.no_detect_time_ms > 0 and state.no_detect_time_ms < confirm_time_ms:
            return 'lost'
        
        # Принимаем решение на основе found_ratio
        if state.found_ratio >= 0.7:  # 70% времени обнаружен
            return 'exists'
        elif state.found_ratio >= 0.3:  # 30-70% времени обнаружен
            return 'lost'
        else:  # < 30% времени обнаружен
            return 'none'
    
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


