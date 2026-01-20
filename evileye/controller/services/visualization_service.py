"""Сервис управления визуализацией."""

from __future__ import annotations

from typing import Any, Dict, Optional

from evileye.core.interfaces import IVisualizer
from evileye.core.logger import get_module_logger
from evileye.visualization_modules.visualizer import Visualizer


class VisualizationService:
    """Сервис для управления визуализацией результатов обработки."""

    def __init__(self):
        """Инициализация сервиса."""
        self.logger = get_module_logger("visualization_service")
        self._visualizer: Optional[IVisualizer] = None

    def initialize_visualizer(
        self,
        params: Dict[str, Any],
        pyqt_slots: Dict[str, Any],
        pyqt_signals: Dict[str, Any],
        source_id_name_table: Optional[Dict[int, str]] = None,
        source_video_duration: Optional[Dict[int, float]] = None,
        class_mapping: Optional[Dict[str, int]] = None,
    ) -> IVisualizer:
        """Инициализировать визуализатор.

        Args:
            params: Параметры конфигурации визуализатора
            pyqt_slots: Слоты PyQt для подключения сигналов
            pyqt_signals: Сигналы PyQt для подключения
            source_id_name_table: Таблица соответствия ID источников и их имен
            source_video_duration: Длительность видео для каждого источника
            class_mapping: Маппинг классов для отображения

        Returns:
            Инициализированный визуализатор
        """
        self._visualizer = Visualizer(pyqt_slots, pyqt_signals)
        self._visualizer.set_params(**params)

        # Установка дополнительных параметров через инкапсулированный API
        if source_id_name_table is not None or source_video_duration is not None or class_mapping is not None:
            self._visualizer.set_source_metadata(
                id_name_table=source_id_name_table,
                video_duration=source_video_duration,
                class_mapping=class_mapping,
            )

        self._visualizer.init()
        self.logger.info("Visualizer initialized")
        return self._visualizer

    def get_visualizer(self) -> Optional[IVisualizer]:
        """Получить визуализатор.

        Returns:
            Визуализатор или None
        """
        return self._visualizer

    def start_visualizer(self) -> None:
        """Запустить визуализатор."""
        if self._visualizer:
            self._visualizer.start()
            self.logger.info("Visualizer started")
        else:
            self.logger.warning("Cannot start visualizer: visualizer not initialized")

    def stop_visualizer(self) -> None:
        """Остановить визуализатор."""
        if self._visualizer:
            self._visualizer.stop()
            self.logger.info("Visualizer stopped")

    def set_main_widget_size(self, width: int, height: int) -> None:
        """Установить размер главного виджета.

        Args:
            width: Ширина виджета
            height: Высота виджета
        """
        if self._visualizer and hasattr(self._visualizer, 'set_current_main_widget_size'):
            self._visualizer.set_current_main_widget_size(width, height)

    def release(self) -> None:
        """Освободить ресурсы визуализатора."""
        if self._visualizer:
            self._visualizer.stop()
            self._visualizer = None
            self.logger.info("Visualization service released")
