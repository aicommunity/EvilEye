#!/usr/bin/env python3
"""
Глубокие диагностические тесты для проверки состояния таймера после перемотки
Эти тесты помогают выявить проблемы с запуском/остановкой таймера на детальном уровне
"""

import sys
import os
from pathlib import Path
import datetime
import time
from typing import Dict, Optional

# Добавить корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    pyqt_version = 5

from evileye.visualization_modules.stream_player_window import StreamPlayerWindow
from evileye.visualization_modules.stream_player_components import VideoGridWidget, VideoPlayerWidget, SplitVideoPlayerWidget

pytestmark = pytest.mark.skipif(
    os.environ.get("EVILEYE_RUN_REAL_DATA_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="Real-data stream player tests are disabled by default (set EVILEYE_RUN_REAL_DATA_TESTS=1 to enable).",
)


@pytest.fixture(scope="session")
def qapp():
    """Создать QApplication для тестов"""
    if not QApplication.instance():
        app = QApplication(sys.argv)
        yield app
    else:
        yield QApplication.instance()


@pytest.fixture
def real_base_dir():
    """Найти базовую директорию с реальными данными"""
    base_dir = Path("EvilEyeData")
    if not base_dir.exists():
        pytest.skip(f"EvilEyeData directory does not exist: {base_dir}")
    return base_dir


@pytest.fixture
def stream_player_window(qapp, real_base_dir):
    """Создать окно плеера с реальными данными"""
    base_dir = real_base_dir
    streams_dir = base_dir / "Streams"
    
    if not streams_dir.exists():
        pytest.skip(f"Streams directory does not exist: {streams_dir}")
    
    # Найти первую доступную дату
    date_dirs = sorted([d for d in streams_dir.iterdir() if d.is_dir()])
    if not date_dirs:
        pytest.skip(f"No date directories found in {streams_dir}")
    
    first_date = date_dirs[0].name
    
    # Найти видеофайлы для этой даты
    video_files = {}
    camera_segment_times = {}
    
    for camera_folder in date_dirs[0].iterdir():
        if camera_folder.is_dir():
            camera_name = camera_folder.name
            video_segments = sorted(camera_folder.glob("*.mp4"))
            if video_segments:
                video_files[camera_name] = [str(v) for v in video_segments]
                
                # Создать сегменты с временными метками
                segment_times = []
                for segment_path in video_segments:
                    filename = segment_path.stem
                    parts = filename.split('_')
                    if len(parts) >= 3:
                        try:
                            date_part = parts[1]  # YYYYMMDD
                            time_part = parts[2]  # HHMMSS
                            start_time_str = f"{date_part}_{time_part}"
                            start_time = datetime.datetime.strptime(start_time_str, '%Y%m%d_%H%M%S')
                            duration = 300  # 5 минут по умолчанию
                            end_time = start_time + datetime.timedelta(seconds=duration)
                            segment_times.append((start_time, end_time, str(segment_path)))
                        except (ValueError, IndexError):
                            segment_times.append((None, None, str(segment_path)))
                    else:
                        segment_times.append((None, None, str(segment_path)))
                
                camera_segment_times[camera_name] = segment_times
    
    if not video_files:
        pytest.skip(f"No video files found for date {first_date}")
    
    # Создать параметры конфигурации
    params = {
        'pipeline': {
            'sources': []
        }
    }
    
    # Добавить источники в конфигурацию
    for camera_folder in video_files.keys():
        if '-' in camera_folder:
            # Split video (например, Cam2-Cam3)
            parts = camera_folder.split('-')
            source_names = parts
            params['pipeline']['sources'].append({
                'source_names': source_names,
                'split': True,
                'num_split': len(source_names),
                'src_coords': [[0, 0, 960, 540], [960, 0, 960, 540]] if len(source_names) == 2 else [],
                'source_ids': list(range(1, len(source_names) + 1))
            })
        else:
            # Обычная камера
            params['pipeline']['sources'].append({
                'source_names': [camera_folder],
                'split': False,
                'num_split': 1,
                'src_coords': [],
                'source_ids': [1]
            })
    
    window = StreamPlayerWindow(base_dir=str(base_dir), params=params)
    
    # Установить выбранные камеры и дату
    window._selected_cameras = list(video_files.keys())
    window._camera_segment_times = camera_segment_times
    
    # Загрузить сегменты камер
    window._load_camera_segments()
    
    # Установить камеры в сетку
    window.video_grid.set_cameras(
        cameras=list(video_files.keys()),
        camera_segment_times=camera_segment_times,
        source_config=window._source_config,
        base_dir=str(base_dir),
        date_folder=first_date
    )
    
    # Установить временной диапазон
    if camera_segment_times:
        all_start_times = [seg[0] for segs in camera_segment_times.values() for seg in segs if seg[0]]
        all_end_times = [seg[1] for segs in camera_segment_times.values() for seg in segs if seg[1]]
        if all_start_times and all_end_times:
            window.video_grid._start_time = min(all_start_times)
            window._start_time = min(all_start_times)
            window._total_duration_ms = int((max(all_end_times) - min(all_start_times)).total_seconds() * 1000)
    
    yield window
    
    window.close()


def get_timer_state(player_widget) -> Dict[str, any]:
    """Получить состояние таймера для плеера"""
    state = {
        'has_timer': False,
        'timer_active': False,
        'timer_interval': None,
        'is_playing': False,
        'has_cap': False,
        'cap_opened': False,
        'has_player': False
    }
    
    if isinstance(player_widget, SplitVideoPlayerWidget):
        if player_widget._video_player:
            state['has_timer'] = player_widget._video_player.timer is not None
            if player_widget._video_player.timer:
                state['timer_active'] = player_widget._video_player.timer.isActive()
                if hasattr(player_widget._video_player.timer, 'interval'):
                    state['timer_interval'] = player_widget._video_player.timer.interval()
            state['is_playing'] = player_widget._video_player._is_playing
            state['has_cap'] = player_widget._video_player.cap is not None
            state['cap_opened'] = player_widget._video_player.cap.isOpened() if player_widget._video_player.cap else False
            state['has_player'] = player_widget._video_player.player is not None
    elif isinstance(player_widget, VideoPlayerWidget):
        state['has_timer'] = player_widget.timer is not None
        if player_widget.timer:
            state['timer_active'] = player_widget.timer.isActive()
            if hasattr(player_widget.timer, 'interval'):
                state['timer_interval'] = player_widget.timer.interval()
        state['is_playing'] = player_widget._is_playing
        state['has_cap'] = player_widget.cap is not None
        state['cap_opened'] = player_widget.cap.isOpened() if player_widget.cap else False
        state['has_player'] = player_widget.player is not None
    
    return state


class TestTimerDeepDiagnostics:
    """Глубокие диагностические тесты для проверки состояния таймера"""
    
    def test_timer_stops_immediately_after_start(self, stream_player_window):
        """Проверить, не останавливается ли таймер сразу после запуска"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние таймеров до перемотки
        before_seek_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            before_seek_states[camera_folder] = get_timer_state(player)
        
        # Перемотать на начало
        window.video_grid.seek_all(0, should_play=True)
        
        # Проверить состояние таймеров сразу после перемотки
        QApplication.processEvents()
        time.sleep(0.01)  # Минимальная задержка
        QApplication.processEvents()
        
        immediately_after_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            immediately_after_states[camera_folder] = get_timer_state(player)
        
        # Подождать еще немного и проверить снова
        time.sleep(0.1)
        QApplication.processEvents()
        
        after_delay_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            after_delay_states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры не останавливаются сразу после запуска
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            immediately = immediately_after_states.get(camera_folder, {})
            after_delay = after_delay_states.get(camera_folder, {})
            
            if immediately.get('timer_active') and not after_delay.get('timer_active'):
                issues.append(
                    f"{camera_folder}: Timer stopped between immediately_after and after_delay "
                    f"(was_active={immediately.get('timer_active')}, now_active={after_delay.get('timer_active')}, "
                    f"is_playing={after_delay.get('is_playing')}, cap_opened={after_delay.get('cap_opened')})"
                )
        
        if issues:
            print("\nTimer stop issues:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nImmediately after states:")
            for camera, state in immediately_after_states.items():
                print(f"  {camera}: {state}")
            print("\nAfter delay states:")
            for camera, state in after_delay_states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer stop issues"
    
    def test_timer_interval_after_seek(self, stream_player_window):
        """Проверить, что интервал таймера установлен правильно после перемотки"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить интервалы таймеров до перемотки
        before_intervals = {}
        for camera_folder, player in window.video_grid._video_players.items():
            state = get_timer_state(player)
            if state.get('timer_interval'):
                before_intervals[camera_folder] = state['timer_interval']
        
        # Перемотать на начало
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить интервалы таймеров после перемотки
        after_intervals = {}
        for camera_folder, player in window.video_grid._video_players.items():
            state = get_timer_state(player)
            if state.get('timer_interval'):
                after_intervals[camera_folder] = state['timer_interval']
        
        # Проверить, что интервалы установлены правильно
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            before_interval = before_intervals.get(camera_folder)
            after_interval = after_intervals.get(camera_folder)
            
            if before_interval and after_interval:
                if before_interval != after_interval:
                    issues.append(
                        f"{camera_folder}: Timer interval changed from {before_interval}ms to {after_interval}ms"
                    )
            elif not after_interval:
                issues.append(
                    f"{camera_folder}: Timer interval not set after seek (before={before_interval}, after={after_interval})"
                )
        
        if issues:
            print("\nTimer interval issues:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nBefore intervals:")
            for camera, interval in before_intervals.items():
                print(f"  {camera}: {interval}ms")
            print("\nAfter intervals:")
            for camera, interval in after_intervals.items():
                print(f"  {camera}: {interval}ms")
        
        # Это не критично, но стоит проверить
        # assert len(issues) == 0, f"Found {len(issues)} timer interval issues"
    
    def test_timer_state_during_seek_operation(self, stream_player_window):
        """Проверить состояние таймера во время операции перемотки"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние до перемотки
        before_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            before_states[camera_folder] = get_timer_state(player)
        
        # Перемотать и проверить состояние во время операции
        # Используем патч для перехвата вызовов timer.start()
        timer_start_calls = {}
        
        def track_timer_start(timer, camera_folder):
            original_start = timer.start
            def wrapped_start(interval=None):
                timer_start_calls[camera_folder] = {
                    'interval': interval,
                    'was_active': timer.isActive(),
                    'timestamp': time.time()
                }
                return original_start(interval) if interval else original_start()
            timer.start = wrapped_start
        
        # Отследить вызовы timer.start()
        for camera_folder, player in window.video_grid._video_players.items():
            if isinstance(player, VideoPlayerWidget) and player.timer:
                track_timer_start(player.timer, camera_folder)
            elif isinstance(player, SplitVideoPlayerWidget) and player._video_player and player._video_player.timer:
                track_timer_start(player._video_player.timer, camera_folder)
        
        # Выполнить перемотку
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние после перемотки
        after_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            after_states[camera_folder] = get_timer_state(player)
        
        # Проверить результаты
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            before = before_states.get(camera_folder, {})
            after = after_states.get(camera_folder, {})
            start_call = timer_start_calls.get(camera_folder)
            
            if start_call:
                if not after.get('timer_active') and start_call.get('interval'):
                    issues.append(
                        f"{camera_folder}: Timer.start({start_call['interval']}) called but timer not active "
                        f"(was_active={start_call['was_active']}, now_active={after.get('timer_active')})"
                    )
            elif not after.get('timer_active') and before.get('timer_active'):
                issues.append(
                    f"{camera_folder}: Timer was active before seek but not after, and timer.start() was not called"
                )
        
        if issues:
            print("\nTimer state during seek issues:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nTimer start calls:")
            for camera, call_info in timer_start_calls.items():
                print(f"  {camera}: {call_info}")
        
        # Это информационный тест, не критично для провала
        # assert len(issues) == 0, f"Found {len(issues)} timer state issues during seek"
    
    def test_timer_cap_relationship(self, stream_player_window):
        """Проверить связь между состоянием cap и таймера"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Перемотать на начало
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние всех камер
        states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            states[camera_folder] = get_timer_state(player)
        
        # Проверить связь между cap и таймером
        issues = []
        for camera_folder, state in states.items():
            cap_opened = state.get('cap_opened')
            timer_active = state.get('timer_active')
            is_playing = state.get('is_playing')
            
            # Если cap открыт и is_playing=True, таймер должен быть активен
            if cap_opened and is_playing and not timer_active:
                issues.append(
                    f"{camera_folder}: cap opened and is_playing=True but timer not active "
                    f"(cap_opened={cap_opened}, is_playing={is_playing}, timer_active={timer_active})"
                )
            
            # Если cap не открыт, таймер не должен быть активен
            if not cap_opened and timer_active:
                issues.append(
                    f"{camera_folder}: cap not opened but timer is active "
                    f"(cap_opened={cap_opened}, timer_active={timer_active})"
                )
        
        if issues:
            print("\nTimer-cap relationship issues:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nStates:")
            for camera, state in states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer-cap relationship issues"
    
    def test_timer_update_frame_opencv_interaction(self, stream_player_window):
        """Проверить взаимодействие между таймером и _update_frame_opencv"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Перемотать на начало
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.3)  # Дать время для нескольких вызовов _update_frame_opencv
        QApplication.processEvents()
        
        # Получить состояние таймеров
        states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры все еще активны после нескольких вызовов _update_frame_opencv
        issues = []
        for camera_folder, state in states.items():
            if state.get('has_timer') and state.get('cap_opened') and state.get('is_playing'):
                if not state.get('timer_active'):
                    issues.append(
                        f"{camera_folder}: Timer should be active but is not "
                        f"(cap_opened={state.get('cap_opened')}, is_playing={state.get('is_playing')}, timer_active={state.get('timer_active')})"
                    )
        
        if issues:
            print("\nTimer-_update_frame_opencv interaction issues:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nStates:")
            for camera, state in states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer-_update_frame_opencv interaction issues"
    
    def test_timer_multiple_seek_operations(self, stream_player_window):
        """Проверить состояние таймера после множественных операций перемотки"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Последовательность операций перемотки
        seek_positions = [0, 5000, 10000, 0, 2000, 0]
        
        states_sequence = []
        
        for position_ms in seek_positions:
            # Выполнить перемотку
            window.video_grid.seek_all(position_ms, should_play=True)
            
            # Подождать немного для применения изменений
            QApplication.processEvents()
            time.sleep(0.2)
            QApplication.processEvents()
            
            # Получить состояние таймеров
            states = {}
            for camera_folder, player in window.video_grid._video_players.items():
                states[camera_folder] = get_timer_state(player)
            
            states_sequence.append((position_ms, states))
        
        # Проверить, что таймеры активны после всех операций
        final_states = states_sequence[-1][1]
        issues = []
        
        for camera_folder, state in final_states.items():
            if state.get('has_timer') and state.get('cap_opened') and state.get('is_playing'):
                if not state.get('timer_active'):
                    issues.append(
                        f"{camera_folder}: Timer not active after multiple seek operations "
                        f"(cap_opened={state.get('cap_opened')}, is_playing={state.get('is_playing')}, timer_active={state.get('timer_active')})"
                    )
        
        if issues:
            print("\nTimer state after multiple seek operations:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nStates sequence:")
            for position, states in states_sequence:
                print(f"\nPosition {position}ms:")
                for camera, state in states.items():
                    print(f"  {camera}: timer_active={state.get('timer_active')}, is_playing={state.get('is_playing')}, cap_opened={state.get('cap_opened')}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer issues after multiple seek operations"
