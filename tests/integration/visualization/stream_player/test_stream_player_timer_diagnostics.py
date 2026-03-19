#!/usr/bin/env python3
"""
Диагностические тесты для проверки состояния таймера после перемотки
Эти тесты помогают выявить проблемы с запуском/остановкой таймера
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
        'is_playing': False,
        'has_cap': False,
        'cap_opened': False,
        'has_player': False
    }
    
    if isinstance(player_widget, SplitVideoPlayerWidget):
        if player_widget._video_player:
            state['has_timer'] = player_widget._video_player.timer is not None
            state['timer_active'] = player_widget._video_player.timer.isActive() if player_widget._video_player.timer else False
            state['is_playing'] = player_widget._video_player._is_playing
            state['has_cap'] = player_widget._video_player.cap is not None
            state['cap_opened'] = player_widget._video_player.cap.isOpened() if player_widget._video_player.cap else False
            state['has_player'] = player_widget._video_player.player is not None
    elif isinstance(player_widget, VideoPlayerWidget):
        state['has_timer'] = player_widget.timer is not None
        state['timer_active'] = player_widget.timer.isActive() if player_widget.timer else False
        state['is_playing'] = player_widget._is_playing
        state['has_cap'] = player_widget.cap is not None
        state['cap_opened'] = player_widget.cap.isOpened() if player_widget.cap else False
        state['has_player'] = player_widget.player is not None
    
    return state


class TestTimerDiagnostics:
    """Диагностические тесты для проверки состояния таймера"""
    
    def test_timer_state_after_seek_to_beginning(self, stream_player_window):
        """Проверить состояние таймера после перемотки на начало"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Получить начальное состояние таймеров
        initial_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            initial_states[camera_folder] = get_timer_state(player)
        
        # Перемотать на начало (0ms)
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние таймеров после перемотки
        after_seek_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            after_seek_states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры активны для всех камер
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            initial = initial_states.get(camera_folder, {})
            after = after_seek_states.get(camera_folder, {})
            
            if after.get('has_timer') and not after.get('timer_active'):
                issues.append(
                    f"{camera_folder}: Timer not active after seek to beginning "
                    f"(is_playing={after.get('is_playing')}, cap_opened={after.get('cap_opened')}, "
                    f"has_cap={after.get('has_cap')})"
                )
        
        if issues:
            print("\nTimer state issues after seek to beginning:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nInitial states:")
            for camera, state in initial_states.items():
                print(f"  {camera}: {state}")
            print("\nAfter seek states:")
            for camera, state in after_seek_states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer issues after seek to beginning"
    
    def test_timer_restart_after_seek(self, stream_player_window):
        """Проверить, что таймер перезапускается после перемотки"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.1)
        QApplication.processEvents()
        
        # Получить состояние таймеров до перемотки
        before_seek_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            before_seek_states[camera_folder] = get_timer_state(player)
        
        # Перемотать на середину (например, 5000ms)
        window.video_grid.seek_all(5000, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние таймеров после перемотки
        after_seek_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            after_seek_states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры активны после перемотки
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            before = before_seek_states.get(camera_folder, {})
            after = after_seek_states.get(camera_folder, {})
            
            if after.get('has_timer') and not after.get('timer_active'):
                issues.append(
                    f"{camera_folder}: Timer not active after seek "
                    f"(was_active={before.get('timer_active')}, is_active={after.get('timer_active')}, "
                    f"is_playing={after.get('is_playing')}, cap_opened={after.get('cap_opened')})"
                )
        
        if issues:
            print("\nTimer restart issues after seek:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nBefore seek states:")
            for camera, state in before_seek_states.items():
                print(f"  {camera}: {state}")
            print("\nAfter seek states:")
            for camera, state in after_seek_states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer restart issues after seek"
    
    def test_timer_state_after_seek_with_playback(self, stream_player_window):
        """Проверить состояние таймера после перемотки с включенным воспроизведением"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Перемотать на начало с should_play=True
        window.video_grid.seek_all(0, should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()
        
        # Получить состояние таймеров
        states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры активны для всех камер с видео
        issues = []
        for camera_folder, state in states.items():
            if state.get('has_timer') and state.get('cap_opened'):
                if not state.get('timer_active'):
                    issues.append(
                        f"{camera_folder}: Timer not active with should_play=True "
                        f"(is_playing={state.get('is_playing')}, cap_opened={state.get('cap_opened')})"
                    )
                elif not state.get('is_playing'):
                    issues.append(
                        f"{camera_folder}: _is_playing=False but timer is active "
                        f"(timer_active={state.get('timer_active')})"
                    )
        
        if issues:
            print("\nTimer state issues with should_play=True:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nTimer states:")
            for camera, state in states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer state issues with should_play=True"
    
    def test_timer_state_after_video_reload(self, stream_player_window):
        """Проверить состояние таймера после перезагрузки видео"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Найти максимальное время окончания всех сегментов
        max_end_time = None
        for segments in window._camera_segment_times.values():
            if segments and segments[-1][1]:
                if max_end_time is None or segments[-1][1] > max_end_time:
                    max_end_time = segments[-1][1]
        
        if not max_end_time:
            pytest.skip("Cannot determine end time")
        
        # Перемотать в область после окончания всех записей (вызовет перезагрузку)
        time_after_end = (max_end_time - window.video_grid._start_time).total_seconds() * 1000 + 1000
        window.video_grid.seek_all(int(time_after_end), should_play=False)
        
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Перемотать обратно в область с видео (вызовет перезагрузку видео)
        time_with_video = (max_end_time - window.video_grid._start_time).total_seconds() * 1000 - 5000
        window.video_grid.seek_all(int(time_with_video), should_play=True)
        
        # Подождать немного для применения изменений
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()
        
        # Получить состояние таймеров после перезагрузки
        states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры активны для всех камер с видео
        issues = []
        for camera_folder, state in states.items():
            if camera_folder not in window.video_grid._no_video_cameras:
                if state.get('has_timer') and state.get('cap_opened'):
                    if not state.get('timer_active'):
                        issues.append(
                            f"{camera_folder}: Timer not active after video reload "
                            f"(is_playing={state.get('is_playing')}, cap_opened={state.get('cap_opened')})"
                        )
        
        if issues:
            print("\nTimer state issues after video reload:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nTimer states:")
            for camera, state in states.items():
                print(f"  {camera}: {state}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer state issues after video reload"
    
    def test_timer_stops_on_cap_error(self, stream_player_window):
        """Проверить, что таймер останавливается при ошибке чтения кадра"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Запустить воспроизведение
        window.video_grid.play_all()
        QApplication.processEvents()
        time.sleep(0.1)
        QApplication.processEvents()
        
        # Получить состояние таймеров до симуляции ошибки
        before_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            before_states[camera_folder] = get_timer_state(player)
        
        # Симулировать ошибку чтения кадра (закрыть cap)
        for camera_folder, player in window.video_grid._video_players.items():
            if isinstance(player, VideoPlayerWidget) and player.cap:
                player.cap.release()
            elif isinstance(player, SplitVideoPlayerWidget) and player._video_player and player._video_player.cap:
                player._video_player.cap.release()
        
        # Подождать немного для обработки ошибки в _update_frame_opencv
        QApplication.processEvents()
        time.sleep(0.2)
        QApplication.processEvents()
        
        # Получить состояние таймеров после ошибки
        after_states = {}
        for camera_folder, player in window.video_grid._video_players.items():
            after_states[camera_folder] = get_timer_state(player)
        
        # Проверить, что таймеры остановились
        issues = []
        for camera_folder in window.video_grid._video_players.keys():
            before = before_states.get(camera_folder, {})
            after = after_states.get(camera_folder, {})
            
            if before.get('timer_active') and after.get('timer_active'):
                issues.append(
                    f"{camera_folder}: Timer still active after cap error "
                    f"(cap_opened={after.get('cap_opened')})"
                )
        
        if issues:
            print("\nTimer stop issues on cap error:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nBefore error states:")
            for camera, state in before_states.items():
                print(f"  {camera}: {state}")
            print("\nAfter error states:")
            for camera, state in after_states.items():
                print(f"  {camera}: {state}")
        
        # Это нормально, если таймеры остановились - это ожидаемое поведение
        # Но если они не остановились, это проблема
        # Проверяем только если cap действительно закрыт
        for camera_folder, player in window.video_grid._video_players.items():
            state = after_states.get(camera_folder, {})
            if not state.get('cap_opened') and state.get('timer_active'):
                assert False, f"{camera_folder}: Timer should be stopped when cap is closed"
    
    def test_timer_state_detailed_logging(self, stream_player_window):
        """Детальное логирование состояния таймера для диагностики"""
        window = stream_player_window
        
        if not window.video_grid._start_time:
            pytest.skip("Start time not set")
        
        # Последовательность операций для детального логирования
        operations = [
            ("Initial state", lambda: None),
            ("After play_all()", lambda: window.video_grid.play_all()),
            ("After seek to 0ms", lambda: window.video_grid.seek_all(0, should_play=True)),
            ("After seek to 5000ms", lambda: window.video_grid.seek_all(5000, should_play=True)),
            ("After seek back to 0ms", lambda: window.video_grid.seek_all(0, should_play=True)),
        ]
        
        all_states = {}
        
        for op_name, op_func in operations:
            if op_func:
                op_func()
                QApplication.processEvents()
                time.sleep(0.2)
                QApplication.processEvents()
            
            states = {}
            for camera_folder, player in window.video_grid._video_players.items():
                states[camera_folder] = get_timer_state(player)
            
            all_states[op_name] = states
            
            print(f"\n{op_name}:")
            for camera, state in states.items():
                print(f"  {camera}: timer_active={state.get('timer_active')}, "
                      f"is_playing={state.get('is_playing')}, "
                      f"cap_opened={state.get('cap_opened')}, "
                      f"has_timer={state.get('has_timer')}")
        
        # Проверить, что после последней операции таймеры активны
        final_states = all_states.get("After seek back to 0ms", {})
        issues = []
        for camera_folder, state in final_states.items():
            if state.get('has_timer') and state.get('cap_opened'):
                if not state.get('timer_active'):
                    issues.append(
                        f"{camera_folder}: Timer not active after seek back to 0ms "
                        f"(is_playing={state.get('is_playing')}, cap_opened={state.get('cap_opened')})"
                    )
        
        if issues:
            print("\nFinal state issues:")
            for issue in issues:
                print(f"  - {issue}")
        
        assert len(issues) == 0, f"Found {len(issues)} timer issues in final state"
