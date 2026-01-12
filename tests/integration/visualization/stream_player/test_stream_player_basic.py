#!/usr/bin/env python3
"""
Базовые тесты для плеера потоковых записей
"""

import sys
import os
from pathlib import Path

# Добавить корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import datetime
from unittest.mock import Mock, MagicMock, patch
import tempfile
import shutil

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    pyqt_version = 5

from evileye.visualization_modules.stream_player_window import StreamPlayerWindow
from evileye.visualization_modules.stream_player_components import (
    VideoGridWidget, TimelineWidget, CameraSelectorWidget, 
    SourceSelectionMenu, RecordingAvailabilityWidget
)


@pytest.fixture(scope="session")
def qapp():
    """Создать QApplication для тестов"""
    if not QApplication.instance():
        app = QApplication(sys.argv)
        yield app
        app.quit()
    else:
        yield QApplication.instance()


@pytest.fixture
def temp_base_dir():
    """Создать временную директорию для тестов"""
    temp_dir = tempfile.mkdtemp(prefix="evileye_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_params():
    """Пример параметров конфигурации"""
    return {
        'pipeline': {
            'sources': [
                {
                    'source_names': ['Cam1'],
                    'split': False,
                    'num_split': 1,
                    'src_coords': [],
                    'source_ids': [1]
                },
                {
                    'source_names': ['Cam2', 'Cam3'],
                    'split': True,
                    'num_split': 2,
                    'src_coords': [[0, 0, 640, 480], [640, 0, 640, 480]],
                    'source_ids': [2, 3]
                }
            ]
        },
        'database': {
            'image_dir': 'EvilEyeData'
        }
    }


class TestStreamPlayerWindow:
    """Тесты для StreamPlayerWindow"""
    
    def test_init(self, qapp, temp_base_dir, sample_params):
        """Тест инициализации окна плеера"""
        window = StreamPlayerWindow(base_dir=temp_base_dir, params=sample_params)
        assert window is not None
        assert window.base_dir == temp_base_dir
        assert window.params == sample_params
        assert window._playback_speed == 1.0
        assert window._is_playing == False
        window.close()
    
    def test_load_source_config(self, qapp, temp_base_dir, sample_params):
        """Тест загрузки конфигурации источников"""
        window = StreamPlayerWindow(base_dir=temp_base_dir, params=sample_params)
        assert 'Cam1' in window._source_config
        assert 'Cam2-Cam3' in window._source_config
        window.close()
    
    def test_save_and_load_state(self, qapp, temp_base_dir, sample_params):
        """Тест сохранения и загрузки состояния"""
        window = StreamPlayerWindow(base_dir=temp_base_dir, params=sample_params)
        
        # Установить состояние
        window._selected_cameras = ['Cam1']
        window._playback_speed = 2.0
        window._event_filters['camera_events'] = False
        
        # Сохранить
        window.save_state()
        
        # Проверить, что состояние сохранено
        assert 'stream_player' in window.params
        assert window.params['stream_player']['selected_cameras'] == ['Cam1']
        assert window.params['stream_player']['playback_speed'] == 2.0
        assert window.params['stream_player']['event_filters']['camera_events'] == False
        
        # Создать новое окно и загрузить состояние
        window2 = StreamPlayerWindow(base_dir=temp_base_dir, params=window.params)
        assert window2._playback_speed == 2.0
        assert window2._event_filters['camera_events'] == False
        
        window.close()
        window2.close()


class TestVideoGridWidget:
    """Тесты для VideoGridWidget"""
    
    def test_init(self, qapp):
        """Тест инициализации виджета сетки"""
        widget = VideoGridWidget()
        assert widget is not None
        assert widget._cameras == []
        assert widget._playback_speed == 1.0
    
    def test_set_cameras(self, qapp):
        """Тест установки камер"""
        widget = VideoGridWidget()
        
        cameras = ['Cam1', 'Cam2']
        camera_segments = {
            'Cam1': [(datetime.datetime(2026, 1, 1, 0, 0, 0), datetime.datetime(2026, 1, 1, 0, 5, 0), '/path/to/video1.mp4')],
            'Cam2': [(datetime.datetime(2026, 1, 1, 0, 0, 0), datetime.datetime(2026, 1, 1, 0, 5, 0), '/path/to/video2.mp4')]
        }
        source_config = {}
        
        widget.set_cameras(cameras, camera_segments, source_config)
        assert widget._cameras == cameras
        assert widget._camera_segments == camera_segments
    
    def test_grid_alignment(self, qapp):
        """Тест выравнивания ячеек сетки"""
        widget = VideoGridWidget()
        
        cameras = ['Cam1', 'Cam2', 'Cam3', 'Cam4']
        camera_segments = {
            cam: [(datetime.datetime(2026, 1, 1, 0, 0, 0), datetime.datetime(2026, 1, 1, 0, 5, 0), f'/path/to/{cam}.mp4')]
            for cam in cameras
        }
        
        widget.set_cameras(cameras, camera_segments, {})
        
        # Проверить, что stretch factors установлены
        assert widget._rows == 2
        assert widget._cols == 2
        
        # Проверить stretch для колонок
        for col in range(widget._cols):
            assert widget.grid_layout.columnStretch(col) == 1
        
        # Проверить stretch для строк
        for row in range(widget._rows):
            assert widget.grid_layout.rowStretch(row) == 1


class TestTimelineWidget:
    """Тесты для TimelineWidget"""
    
    def test_init(self, qapp):
        """Тест инициализации виджета временной шкалы"""
        widget = TimelineWidget()
        assert widget is not None
        assert widget._start_time is None
        assert widget._end_time is None
        assert widget._current_position_ms == 0
    
    def test_set_time_range(self, qapp):
        """Тест установки временного диапазона"""
        widget = TimelineWidget()
        
        start_time = datetime.datetime(2026, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2026, 1, 1, 1, 0, 0)
        segments = [
            (datetime.datetime(2026, 1, 1, 0, 10, 0), datetime.datetime(2026, 1, 1, 0, 20, 0)),
            (datetime.datetime(2026, 1, 1, 0, 30, 0), datetime.datetime(2026, 1, 1, 0, 40, 0))
        ]
        
        widget.set_time_range(start_time, end_time, segments)
        
        assert widget._start_time == start_time
        assert widget._end_time == end_time
        assert widget._recording_segments == segments
        
        # Проверить метки времени
        assert "2026-01-01 00:00:00" in widget.start_time_label.text()
        assert "2026-01-01 01:00:00" in widget.end_time_label.text()
    
    def test_seek_relative(self, qapp):
        """Тест перемотки на относительное время"""
        widget = TimelineWidget()
        
        start_time = datetime.datetime(2026, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2026, 1, 1, 1, 0, 0)
        widget.set_time_range(start_time, end_time)
        
        widget.set_position(30000)  # 30 секунд
        initial_pos = widget._current_position_ms
        
        # Перемотать на 1 минуту вперед
        widget._seek_relative(60 * 1000)
        assert widget._current_position_ms == initial_pos + 60 * 1000
        
        # Перемотать на 5 минут назад
        widget._seek_relative(-5 * 60 * 1000)
        assert widget._current_position_ms == max(0, initial_pos - 4 * 60 * 1000)


class TestSourceSelectionMenu:
    """Тесты для SourceSelectionMenu"""
    
    def test_init(self, qapp):
        """Тест инициализации меню выбора источников"""
        available_sources = ['Cam1', 'Cam2', 'Cam3']
        selected_sources = ['Cam1']
        
        menu = SourceSelectionMenu(available_sources, selected_sources)
        assert menu is not None
        assert len(menu.actions()) > 0
    
    def test_empty_sources(self, qapp):
        """Тест меню без доступных источников"""
        menu = SourceSelectionMenu([], [])
        actions = menu.actions()
        assert len(actions) == 1
        assert not actions[0].isEnabled()


class TestRecordingAvailabilityWidget:
    """Тесты для RecordingAvailabilityWidget"""
    
    def test_init(self, qapp):
        """Тест инициализации виджета доступности записей"""
        widget = RecordingAvailabilityWidget()
        assert widget is not None
        assert widget._segments == []
    
    def test_set_segments(self, qapp):
        """Тест установки сегментов записей"""
        widget = RecordingAvailabilityWidget()
        
        start_time = datetime.datetime(2026, 1, 1, 0, 0, 0)
        end_time = datetime.datetime(2026, 1, 1, 1, 0, 0)
        segments = [
            (datetime.datetime(2026, 1, 1, 0, 10, 0), datetime.datetime(2026, 1, 1, 0, 20, 0)),
            (datetime.datetime(2026, 1, 1, 0, 30, 0), datetime.datetime(2026, 1, 1, 0, 40, 0))
        ]
        
        widget.set_segments(segments, start_time, end_time)
        
        assert widget._segments == segments
        assert widget._start_time == start_time
        assert widget._end_time == end_time


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
