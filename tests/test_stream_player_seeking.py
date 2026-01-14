"""
Unit tests for video seeking functionality in stream player
"""
import unittest
from unittest.mock import Mock, MagicMock, patch, call
import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    pyqt_version = 5

from evileye.visualization_modules.stream_player_components import VideoGridWidget, SplitVideoPlayerWidget
from evileye.visualization_modules.video_player_window import VideoPlayerWidget


class TestStreamPlayerSeeking(unittest.TestCase):
    """Tests for video seeking functionality"""
    
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
        
        # Mock start time
        self.start_time = datetime.datetime(2026, 1, 8, 14, 20, 16)
        self.video_grid._start_time = self.start_time
        
        # Create mock players
        self.mock_player1 = Mock(spec=VideoPlayerWidget)
        self.mock_player1.video_path = "/path/to/cam1/video.mp4"
        self.mock_player1._is_playing = True
        self.mock_player1.player = None
        self.mock_player1.cap = Mock()
        self.mock_player1.cap.get.return_value = 30.0  # FPS
        self.mock_player1.timer = Mock()
        self.mock_player1.timer.isActive.return_value = True
        
        self.mock_split_player = Mock(spec=SplitVideoPlayerWidget)
        self.mock_split_player._video_player = Mock()
        self.mock_split_player._video_player.video_path = "/path/to/cam2-cam3/video.mp4"
        self.mock_split_player._video_player._is_playing = True
        self.mock_split_player._video_player.player = None
        self.mock_split_player._video_player.cap = Mock()
        self.mock_split_player._video_player.cap.get.return_value = 30.0
        self.mock_split_player._video_player.timer = Mock()
        self.mock_split_player._video_player.timer.isActive.return_value = True
        self.mock_split_player._region_widgets = []
        
        # Set up video players dictionary
        self.video_grid._video_players = {
            "Cam1": self.mock_player1,
            "Cam2-Cam3": self.mock_split_player
        }
        
        # Set up camera segments with different start times
        self.video_grid._camera_segments = {
            "Cam1": [
                (datetime.datetime(2026, 1, 8, 14, 20, 16), 
                 datetime.datetime(2026, 1, 8, 14, 25, 16), 
                 "/path/to/cam1/video.mp4")
            ],
            "Cam2-Cam3": [
                (datetime.datetime(2026, 1, 8, 14, 20, 16), 
                 datetime.datetime(2026, 1, 8, 14, 25, 16), 
                 "/path/to/cam2-cam3/video.mp4")
            ],
            "Cam4-Cam5": [
                (datetime.datetime(2026, 1, 8, 14, 20, 19),  # Started 3 seconds later
                 datetime.datetime(2026, 1, 8, 14, 25, 19), 
                 "/path/to/cam4-cam5/video.mp4")
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
            "Cam1": "/path/to/cam1/video.mp4",
            "Cam2-Cam3": "/path/to/cam2-cam3/video.mp4"
        }
        self.video_grid._current_segment_indices = {
            "Cam1": 0,
            "Cam2-Cam3": 0
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
    
    def test_seek_all_calls_seek_for_all_cameras(self):
        """Test that _seek_player is called for all cameras"""
        # Add Cam4-Cam5 player
        mock_player4 = Mock(spec=SplitVideoPlayerWidget)
        mock_player4._video_player = Mock()
        mock_player4._video_player.video_path = "/path/to/cam4-cam5/video.mp4"
        mock_player4._video_player._is_playing = True
        mock_player4._video_player.player = None
        mock_player4._video_player.cap = Mock()
        mock_player4._video_player.cap.get.return_value = 30.0
        mock_player4._video_player.timer = Mock()
        mock_player4._video_player.timer.isActive.return_value = True
        mock_player4._region_widgets = []
        self.video_grid._video_players["Cam4-Cam5"] = mock_player4
        self.video_grid._current_segments["Cam4-Cam5"] = "/path/to/cam4-cam5/video.mp4"
        self.video_grid._current_segment_indices["Cam4-Cam5"] = 0
        
        # Mock _seek_player to track calls
        seek_calls = []
        original_seek = self.video_grid._seek_player
        
        def track_seek(player, position_ms):
            seek_calls.append((type(player).__name__, position_ms))
            return original_seek(player, position_ms)
        
        self.video_grid._seek_player = track_seek
        
        # Call seek_all
        self.video_grid.seek_all(1000, should_play=True)
        
        # Check that _seek_player was called for all cameras
        self.assertEqual(len(seek_calls), 3, f"Expected 3 seek calls, got {len(seek_calls)}: {seek_calls}")
        
        # Verify calls for each camera
        camera_names = [call[0] for call in seek_calls]
        self.assertIn("VideoPlayerWidget", camera_names, "Cam1 should be seeked")
        self.assertIn("SplitVideoPlayerWidget", camera_names, "Split players should be seeked")
    
    def test_seek_all_calculates_correct_offset(self):
        """Test that segment_offset_ms is calculated correctly for each camera"""
        # Add Cam4-Cam5 player
        mock_player4 = Mock(spec=SplitVideoPlayerWidget)
        mock_player4._video_player = Mock()
        mock_player4._video_player.video_path = "/path/to/cam4-cam5/video.mp4"
        mock_player4._video_player._is_playing = True
        mock_player4._video_player.player = None
        mock_player4._video_player.cap = Mock()
        mock_player4._video_player.cap.get.return_value = 30.0
        mock_player4._video_player.timer = Mock()
        mock_player4._video_player.timer.isActive.return_value = True
        mock_player4._region_widgets = []
        self.video_grid._video_players["Cam4-Cam5"] = mock_player4
        self.video_grid._current_segments["Cam4-Cam5"] = "/path/to/cam4-cam5/video.mp4"
        self.video_grid._current_segment_indices["Cam4-Cam5"] = 0
        
        # Track positions passed to _seek_player
        seek_positions = {}
        
        def track_seek(player, position_ms):
            camera_name = None
            for name, p in self.video_grid._video_players.items():
                if p == player:
                    camera_name = name
                    break
            if camera_name:
                seek_positions[camera_name] = position_ms
        
        self.video_grid._seek_player = track_seek
        
        # Seek to 2000ms (2 seconds after start)
        self.video_grid.seek_all(2000, should_play=True)
        
        # Cam1 started at 14:20:16, so at 2000ms offset should be 2000ms
        self.assertEqual(seek_positions.get("Cam1"), 2000, 
                        f"Cam1 should seek to 2000ms, got {seek_positions.get('Cam1')}")
        
        # Cam4-Cam5 started at 14:20:19 (3 seconds later), so at 2000ms global time
        # target_time = 14:20:18, segment_start = 14:20:19
        # segment_offset = -1000ms, but should be clamped to 0ms
        self.assertEqual(seek_positions.get("Cam4-Cam5"), 0,
                        f"Cam4-Cam5 should seek to 0ms (started later), got {seek_positions.get('Cam4-Cam5')}")
    
    def test_seek_all_handles_late_starting_cameras(self):
        """Test handling of cameras that started recording later"""
        # Add Cam4-Cam5 player
        mock_player4 = Mock(spec=SplitVideoPlayerWidget)
        mock_player4._video_player = Mock()
        mock_player4._video_player.video_path = "/path/to/cam4-cam5/video.mp4"
        mock_player4._video_player._is_playing = True
        mock_player4._video_player.player = None
        mock_player4._video_player.cap = Mock()
        mock_player4._video_player.cap.get.return_value = 30.0
        mock_player4._video_player.timer = Mock()
        mock_player4._video_player.timer.isActive.return_value = True
        mock_player4._region_widgets = []
        self.video_grid._video_players["Cam4-Cam5"] = mock_player4
        self.video_grid._current_segments["Cam4-Cam5"] = "/path/to/cam4-cam5/video.mp4"
        self.video_grid._current_segment_indices["Cam4-Cam5"] = 0
        
        # Seek to 5000ms (5 seconds after start)
        # Cam4-Cam5 started at 14:20:19, so target_time (14:20:21) is after segment_start (14:20:19)
        # segment_offset should be 2000ms (5s - 3s delay)
        
        seek_positions = {}
        
        def track_seek(player, position_ms):
            camera_name = None
            for name, p in self.video_grid._video_players.items():
                if p == player:
                    camera_name = name
                    break
            if camera_name:
                seek_positions[camera_name] = position_ms
        
        self.video_grid._seek_player = track_seek
        
        self.video_grid.seek_all(5000, should_play=True)
        
        # Cam4-Cam5 should seek to 2000ms (5000ms - 3000ms delay)
        self.assertEqual(seek_positions.get("Cam4-Cam5"), 2000,
                        f"Cam4-Cam5 should seek to 2000ms (5s - 3s delay), got {seek_positions.get('Cam4-Cam5')}")
    
    def test_seek_player_for_regular_player(self):
        """Test _seek_player for regular VideoPlayerWidget"""
        # Test with OpenCV backend
        position_ms = 1500
        self.video_grid._seek_player(self.mock_player1, position_ms)
        
        # Verify cap.set was called with correct frame number
        expected_frame = int((position_ms / 1000.0) * 30)
        self.mock_player1.cap.set.assert_called_once()
        call_args = self.mock_player1.cap.set.call_args
        self.assertEqual(call_args[0][0], 0)  # CAP_PROP_POS_FRAMES
        self.assertEqual(call_args[0][1], expected_frame)
    
    def test_seek_player_for_split_player(self):
        """Test _seek_player for SplitVideoPlayerWidget"""
        position_ms = 2000
        self.mock_split_player.seek = Mock()
        
        self.video_grid._seek_player(self.mock_split_player, position_ms)
        
        # Verify seek was called on split player
        self.mock_split_player.seek.assert_called_once_with(position_ms)
    
    def test_seek_all_synchronizes_all_cameras(self):
        """Test that seek_all synchronizes all cameras"""
        # Add Cam4-Cam5 player
        mock_player4 = Mock(spec=SplitVideoPlayerWidget)
        mock_player4._video_player = Mock()
        mock_player4._video_player.video_path = "/path/to/cam4-cam5/video.mp4"
        mock_player4._video_player._is_playing = True
        mock_player4._video_player.player = None
        mock_player4._video_player.cap = Mock()
        mock_player4._video_player.cap.get.return_value = 30.0
        mock_player4._video_player.timer = Mock()
        mock_player4._video_player.timer.isActive.return_value = True
        mock_player4._region_widgets = []
        self.video_grid._video_players["Cam4-Cam5"] = mock_player4
        self.video_grid._current_segments["Cam4-Cam5"] = "/path/to/cam4-cam5/video.mp4"
        self.video_grid._current_segment_indices["Cam4-Cam5"] = 0
        
        # Track all seek calls
        seek_calls = []
        
        def track_seek(player, position_ms):
            camera_name = None
            for name, p in self.video_grid._video_players.items():
                if p == player:
                    camera_name = name
                    break
            seek_calls.append((camera_name, position_ms))
        
        self.video_grid._seek_player = track_seek
        
        # Seek to 3000ms
        self.video_grid.seek_all(3000, should_play=True)
        
        # All cameras should have been seeked
        self.assertEqual(len(seek_calls), 3, 
                        f"Expected 3 cameras to be seeked, got {len(seek_calls)}")
        
        # Verify all cameras are in the calls
        camera_names = [call[0] for call in seek_calls]
        self.assertIn("Cam1", camera_names)
        self.assertIn("Cam2-Cam3", camera_names)
        self.assertIn("Cam4-Cam5", camera_names)


if __name__ == '__main__':
    unittest.main()
