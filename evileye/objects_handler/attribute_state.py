from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AttributeState:
    """
    Состояние одного атрибута у первичного объекта.
    Три состояния: none, exists, lost.
    """
    name: str
    state: str = "none"  # none | exists | lost
    confidence_smooth: float = 0.0
    frames_present: int = 0
    total_time_ms: int = 0
    no_detect_time_ms: int = 0
    enter_count: int = 0
    enter_ts: Optional[float] = None
    last_seen_ts: Optional[float] = None
    
    # Новые поля для улучшенной логики состояний
    total_found_time_ms: int = 0  # Суммарное время обнаружения
    total_lost_time_ms: int = 0   # Суммарное время потери
    found_ratio: float = 0.0      # Отношение времени обнаружения к общему времени

    def reset_presence(self):
        self.frames_present = 0
        self.total_time_ms = 0
        self.enter_ts = None
        # Сбрасываем новые поля
        self.total_found_time_ms = 0
        self.total_lost_time_ms = 0
        self.found_ratio = 0.0


