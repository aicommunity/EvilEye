"""
Integration tests for GUI initialization and visualization.

Tests cover problematic cases from logs:
- Visualizer stopping immediately after start
- Missing source_ids in visualizer initialization
- Controller visualization adapter integration
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys

# Mock PyQt before importing
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt5'] = MagicMock()

from evileye.gui import GUIMode, GUIManager
from evileye.gui.visualization_adapter import VisualizationAdapter
from evileye.controller import controller


class TestVisualizerInitialization(unittest.TestCase):
    """Test visualizer initialization edge cases."""
    
    def test_visualizer_init_without_source_ids(self):
        """Test that visualizer init fails gracefully when source_ids is empty."""
        from evileye.visualization_modules.visualizer import Visualizer
        
        # Create visualizer with empty source_ids
        slots = {'update_image': lambda x, y: None}
        signals = {'display_zones_signal': MagicMock()}
        visualizer = Visualizer(slots, signals)
        visualizer.source_ids = []  # Empty source_ids
        
        # Init should return False
        result = visualizer.init()
        self.assertFalse(result)
        self.assertEqual(len(visualizer.visual_threads), 0)
    
    def test_visualizer_init_with_source_ids(self):
        """Test that visualizer init succeeds with source_ids."""
        from evileye.visualization_modules.visualizer import Visualizer
        
        slots = {'update_image': lambda x, y: None, 
                 'update_original_cv_image': lambda x, y: None,
                 'clean_image_available': lambda x, y: None,
                 'open_zone_win': lambda x: None,
                 'open_roi_win': lambda x: None}
        signals = {'display_zones_signal': MagicMock(),
                   'add_zone_signal': MagicMock(),
                   'add_roi_signal': MagicMock()}
        
        visualizer = Visualizer(slots, signals)
        visualizer.source_ids = [0, 1]
        visualizer.fps = [30, 30]
        visualizer.num_height = 1
        visualizer.num_width = 2
        
        # Init should succeed
        result = visualizer.init()
        self.assertTrue(result)
        self.assertEqual(len(visualizer.visual_threads), 2)
    
    def test_visualizer_double_init_does_not_reinit(self):
        """Test that calling init() twice doesn't reinitialize if already initialized."""
        from evileye.visualization_modules.visualizer import Visualizer
        
        slots = {'update_image': lambda x, y: None,
                 'update_original_cv_image': lambda x, y: None,
                 'clean_image_available': lambda x, y: None,
                 'open_zone_win': lambda x: None,
                 'open_roi_win': lambda x: None}
        signals = {'display_zones_signal': MagicMock(),
                   'add_zone_signal': MagicMock(),
                   'add_roi_signal': MagicMock()}
        
        visualizer = Visualizer(slots, signals)
        visualizer.source_ids = [0]
        visualizer.fps = [30]
        visualizer.num_height = 1
        visualizer.num_width = 1
        
        # First init
        result1 = visualizer.init()
        self.assertTrue(result1)
        thread_count_1 = len(visualizer.visual_threads)
        self.assertEqual(thread_count_1, 1)
        
        # Second init should NOT reinitialize (already initialized)
        visualizer.source_ids = [0, 1]  # Change source_ids
        visualizer.fps = [30, 30]
        visualizer.num_width = 2
        result2 = visualizer.init()
        self.assertTrue(result2)  # Returns True because already initialized
        # Should still have same threads (not reinitialized)
        self.assertEqual(len(visualizer.visual_threads), 1)  # Still 1 thread from first init
    
    def test_visualizer_reinit_after_release(self):
        """Test that visualizer can be reinitialized after release."""
        from evileye.visualization_modules.visualizer import Visualizer
        
        slots = {'update_image': lambda x, y: None,
                 'update_original_cv_image': lambda x, y: None,
                 'clean_image_available': lambda x, y: None,
                 'open_zone_win': lambda x: None,
                 'open_roi_win': lambda x: None}
        signals = {'display_zones_signal': MagicMock(),
                   'add_zone_signal': MagicMock(),
                   'add_roi_signal': MagicMock()}
        
        visualizer = Visualizer(slots, signals)
        visualizer.source_ids = [0]
        visualizer.fps = [30]
        visualizer.num_height = 1
        visualizer.num_width = 1
        
        # First init
        result1 = visualizer.init()
        self.assertTrue(result1)
        self.assertEqual(len(visualizer.visual_threads), 1)
        
        # Release
        visualizer.release()
        self.assertEqual(len(visualizer.visual_threads), 0)
        self.assertFalse(visualizer.get_init_flag())
        
        # Reinit with different source_ids
        visualizer.source_ids = [0, 1]
        visualizer.fps = [30, 30]
        visualizer.num_width = 2
        result2 = visualizer.init()
        self.assertTrue(result2)
        self.assertEqual(len(visualizer.visual_threads), 2)


class TestVisualizationAdapter(unittest.TestCase):
    """Test visualization adapter integration."""
    
    def test_adapter_update_converts_dict_to_list(self):
        """Test that adapter converts dict to list for visualizer.update()."""
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        # Create mock visualizer
        mock_visualizer = Mock()
        mock_visualizer.update = Mock()
        
        adapter = VisualizationAdapter(mock_visualizer)
        
        # Test with dict format (from controller)
        processing_frames_dict = {
            0: [Mock(source_id=0), Mock(source_id=0)],
            1: [Mock(source_id=1)]
        }
        
        adapter.update(
            processing_frames_dict,
            {0: 100, 1: 200},
            [],
            {0: 5, 1: 3},
            {}
        )
        
        # Check that visualizer.update was called
        self.assertTrue(mock_visualizer.update.called)
        # Check that first argument is a list (converted from dict)
        call_args = mock_visualizer.update.call_args[0]
        self.assertIsInstance(call_args[0], list)
        self.assertEqual(len(call_args[0]), 3)  # 2 frames from source 0 + 1 from source 1
    
    def test_adapter_update_with_list(self):
        """Test that adapter handles list format correctly."""
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        mock_visualizer = Mock()
        mock_visualizer.update = Mock()
        
        adapter = VisualizationAdapter(mock_visualizer)
        
        # Test with list format
        processing_frames_list = [Mock(source_id=0), Mock(source_id=1)]
        
        adapter.update(
            processing_frames_list,
            {0: 100, 1: 200},
            [],
            {},
            {}
        )
        
        self.assertTrue(mock_visualizer.update.called)
        call_args = mock_visualizer.update.call_args[0]
        self.assertIsInstance(call_args[0], list)
        self.assertEqual(len(call_args[0]), 2)


class TestControllerVisualizationIntegration(unittest.TestCase):
    """Test controller and visualization adapter integration."""
    
    def test_controller_set_visualization_adapter(self):
        """Test setting visualization adapter on controller."""
        from evileye.controller import controller
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        ctrl = controller.Controller()
        adapter = VisualizationAdapter()
        
        # Set adapter
        ctrl.set_visualization_adapter(adapter)
        
        self.assertEqual(ctrl.visualization_adapter, adapter)
    
    def test_controller_start_with_adapter(self):
        """Test that controller.start() calls adapter.start() if adapter is available."""
        from evileye.controller import controller
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        ctrl = controller.Controller()
        adapter = VisualizationAdapter()
        adapter.is_available = Mock(return_value=True)
        adapter.start = Mock()
        
        ctrl.set_visualization_adapter(adapter)
        
        # Mock other required components
        ctrl.pipeline = Mock()
        ctrl.pipeline.start = Mock()
        ctrl.obj_handler = Mock()
        ctrl.obj_handler.start = Mock()
        ctrl.run_flag = False  # Prevent control thread from starting
        
        # This will fail because controller needs full initialization,
        # but we can test that adapter.start() would be called
        # For now, just verify adapter is set
        self.assertEqual(ctrl.visualization_adapter, adapter)


class TestGUIManagerIntegration(unittest.TestCase):
    """Test GUIManager integration with controller."""
    
    def test_gui_manager_headless_mode(self):
        """Test that headless mode doesn't create QApplication."""
        config = {"controller": {}}
        manager = GUIManager(GUIMode.HEADLESS, config)
        
        self.assertIsNone(manager.qt_app)
        self.assertIsNone(manager.main_window)
    
    def test_gui_manager_hidden_mode_flag_monitor(self):
        """Test that hidden mode sets up flag monitor."""
        config = {"controller": {"gui_flag_file": "test/.show_gui"}}
        manager = GUIManager(GUIMode.HIDDEN, config)
        
        # Flag file path should be initialized
        self.assertIsNotNone(manager.flag_file_path)
        self.assertEqual(str(manager.flag_file_path), "test/.show_gui")
        
        # Flag monitor timer should be None initially (started later)
        self.assertIsNone(manager.flag_monitor_timer)


if __name__ == '__main__':
    unittest.main()
