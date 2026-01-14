"""
Integration tests for video seeking synchronization
"""
import unittest
import datetime
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

from evileye.visualization_modules.stream_player_components import VideoGridWidget


class TestStreamPlayerSeekingIntegration(unittest.TestCase):
    """Integration tests for video seeking"""
    
    @classmethod
    def setUpClass(cls):
        """Create QApplication once for all tests"""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()
    
    def setUp(self):
        """Set up test fixtures"""
        self.video_grid = VideoGridWidget()
        
        # Mock start time (earliest camera start)
        self.start_time = datetime.datetime(2026, 1, 8, 14, 20, 16)
        self.video_grid._start_time = self.start_time
        
        # Create mock players with tracking
        self.seek_calls = {}  # {camera_name: [list of positions]}
        
        def create_mock_player(camera_name, is_split=False):
            if is_split:
                player = Mock()
                player._video_player = Mock()
                player._video_player.video_path = f"/path/to/{camera_name}/video.mp4"
                player._video_player._is_playing = True
                player._video_player.player = None
                player._video_player.cap = Mock()
                player._video_player.cap.get.return_value = 30.0
                player._video_player.cap.set = Mock()
                player._video_player.cap.get.return_value = 0  # For CAP_PROP_POS_FRAMES
                player._video_player.timer = Mock()
                player._video_player.timer.isActive.return_value = True
                player._region_widgets = []
                player.seek = Mock(side_effect=lambda pos: self.seek_calls.setdefault(camera_name, []).append(pos))
            else:
                player = Mock()
                player.video_path = f"/path/to/{camera_name}/video.mp4"
                player._is_playing = True
                player.player = None
                player.cap = Mock()
                player.cap.get = Mock(side_effect=lambda prop: 30.0 if prop == 5 else 0)  # FPS = 30, POS_FRAMES = 0
                player.cap.set = Mock()
                player.timer = Mock()
                player.timer.isActive.return_value = True
            
            return player
        
        # Create players
        self.video_grid._video_players = {
            "Cam1": create_mock_player("Cam1", is_split=False),
            "Cam2-Cam3": create_mock_player("Cam2-Cam3", is_split=True),
            "Cam4-Cam5": create_mock_player("Cam4-Cam5", is_split=True)
        }
        
        # Set up camera segments with different start times
        self.video_grid._camera_segments = {
            "Cam1": [
                (datetime.datetime(2026, 1, 8, 14, 20, 16), 
                 datetime.datetime(2026, 1, 8, 14, 25, 16), 
                 "/path/to/Cam1/video.mp4")
            ],
            "Cam2-Cam3": [
                (datetime.datetime(2026, 1, 8, 14, 20, 16), 
                 datetime.datetime(2026, 1, 8, 14, 25, 16), 
                 "/path/to/Cam2-Cam3/video.mp4")
            ],
            "Cam4-Cam5": [
                (datetime.datetime(2026, 1, 8, 14, 20, 19),  # Started 3 seconds later
                 datetime.datetime(2026, 1, 8, 14, 25, 19), 
                 "/path/to/Cam4-Cam5/video.mp4")
            ]
        }
        
        # Set up folder to sources mapping
        self.video_grid._folder_to_sources = {
            "Cam1": ["Cam1"],
            "Cam2-Cam3": ["Cam2", "Cam3"],
            "Cam4-Cam5": ["Cam4", "Cam5"]
        }
        
        # Set up current segments and indices
        self.video_grid._current_segments = {
            "Cam1": "/path/to/Cam1/video.mp4",
            "Cam2-Cam3": "/path/to/Cam2-Cam3/video.mp4",
            "Cam4-Cam5": "/path/to/Cam4-Cam5/video.mp4"
        }
        self.video_grid._current_segment_indices = {
            "Cam1": 0,
            "Cam2-Cam3": 0,
            "Cam4-Cam5": 0
        }
        
        # Set up source config
        self.video_grid._source_config = {
            "Cam2-Cam3": {
                "split": True,
                "num_split": 2,
                "src_coords": [[0, 0, 960, 540], [960, 0, 960, 540]],
                "source_names": ["Cam2", "Cam3"],
                "parent_folder": "Cam2-Cam3"
            },
            "Cam4-Cam5": {
                "split": True,
                "num_split": 2,
                "src_coords": [[0, 0, 960, 540], [960, 0, 960, 540]],
                "source_names": ["Cam4", "Cam5"],
                "parent_folder": "Cam4-Cam5"
            }
        }
        
        # Track _seek_player calls
        self.original_seek = self.video_grid._seek_player
        
        def track_seek(player, position_ms):
            camera_name = None
            for name, p in self.video_grid._video_players.items():
                if p == player:
                    camera_name = name
                    break
            if camera_name:
                if camera_name not in self.seek_calls:
                    self.seek_calls[camera_name] = []
                self.seek_calls[camera_name].append(position_ms)
            return self.original_seek(player, position_ms)
        
        self.video_grid._seek_player = track_seek
    
    def test_seek_forward_backward(self):
        """Test seeking forward and backward, verify all cameras are synchronized"""
        self.seek_calls.clear()
        
        # Seek forward to 2000ms
        self.video_grid.seek_all(2000, should_play=True)
        
        # All cameras should have been seeked
        self.assertIn("Cam1", self.seek_calls, "Cam1 should be seeked")
        self.assertIn("Cam2-Cam3", self.seek_calls, "Cam2-Cam3 should be seeked")
        self.assertIn("Cam4-Cam5", self.seek_calls, "Cam4-Cam5 should be seeked")
        
        # Cam1 and Cam2-Cam3 started at 14:20:16, so at 2000ms offset should be 2000ms
        self.assertEqual(self.seek_calls["Cam1"][-1], 2000, 
                        f"Cam1 should seek to 2000ms, got {self.seek_calls['Cam1'][-1]}")
        self.assertEqual(self.seek_calls["Cam2-Cam3"][-1], 2000,
                        f"Cam2-Cam3 should seek to 2000ms, got {self.seek_calls['Cam2-Cam3'][-1]}")
        
        # Cam4-Cam5 started at 14:20:19 (3s later), so at 2000ms global time
        # target_time = 14:20:18, segment_start = 14:20:19
        # segment_offset = -1000ms, should be clamped to 0ms
        self.assertEqual(self.seek_calls["Cam4-Cam5"][-1], 0,
                        f"Cam4-Cam5 should seek to 0ms (started later), got {self.seek_calls['Cam4-Cam5'][-1]}")
        
        # Seek forward to 5000ms (5 seconds after start)
        self.seek_calls.clear()
        self.video_grid.seek_all(5000, should_play=True)
        
        # Cam1 and Cam2-Cam3 should seek to 5000ms
        self.assertEqual(self.seek_calls["Cam1"][-1], 5000,
                        f"Cam1 should seek to 5000ms, got {self.seek_calls['Cam1'][-1]}")
        self.assertEqual(self.seek_calls["Cam2-Cam3"][-1], 5000,
                        f"Cam2-Cam3 should seek to 5000ms, got {self.seek_calls['Cam2-Cam3'][-1]}")
        
        # Cam4-Cam5 started at 14:20:19, so at 5000ms global time
        # target_time = 14:20:21, segment_start = 14:20:19
        # segment_offset = 2000ms (5000ms - 3000ms delay)
        self.assertEqual(self.seek_calls["Cam4-Cam5"][-1], 2000,
                        f"Cam4-Cam5 should seek to 2000ms (5s - 3s delay), got {self.seek_calls['Cam4-Cam5'][-1]}")
        
        # Seek back to 1000ms
        self.seek_calls.clear()
        self.video_grid.seek_all(1000, should_play=True)
        
        # All cameras should seek back
        self.assertEqual(self.seek_calls["Cam1"][-1], 1000,
                        f"Cam1 should seek back to 1000ms, got {self.seek_calls['Cam1'][-1]}")
        self.assertEqual(self.seek_calls["Cam2-Cam3"][-1], 1000,
                        f"Cam2-Cam3 should seek back to 1000ms, got {self.seek_calls['Cam2-Cam3'][-1]}")
        # Cam4-Cam5: target_time = 14:20:17, segment_start = 14:20:19, offset = -2000ms -> 0ms
        self.assertEqual(self.seek_calls["Cam4-Cam5"][-1], 0,
                        f"Cam4-Cam5 should seek to 0ms (before start), got {self.seek_calls['Cam4-Cam5'][-1]}")
    
    def test_seek_with_different_start_times(self):
        """Test seeking with cameras that started recording at different times"""
        self.seek_calls.clear()
        
        # Seek to various positions and verify calculations
        test_cases = [
            (0, {"Cam1": 0, "Cam2-Cam3": 0, "Cam4-Cam5": 0}),  # All at start
            (1000, {"Cam1": 1000, "Cam2-Cam3": 1000, "Cam4-Cam5": 0}),  # Cam4-Cam5 not started yet
            (3000, {"Cam1": 3000, "Cam2-Cam3": 3000, "Cam4-Cam5": 0}),  # Cam4-Cam5 just started
            (5000, {"Cam1": 5000, "Cam2-Cam3": 5000, "Cam4-Cam5": 2000}),  # Cam4-Cam5 2s in
            (10000, {"Cam1": 10000, "Cam2-Cam3": 10000, "Cam4-Cam5": 7000}),  # All well into recording
        ]
        
        for position_ms, expected_positions in test_cases:
            self.seek_calls.clear()
            self.video_grid.seek_all(position_ms, should_play=True)
            
            for camera_name, expected_pos in expected_positions.items():
                actual_pos = self.seek_calls.get(camera_name, [None])[-1]
                self.assertEqual(actual_pos, expected_pos,
                               f"At position_ms={position_ms}, {camera_name} should seek to {expected_pos}ms, got {actual_pos}ms")


if __name__ == '__main__':
    unittest.main()
