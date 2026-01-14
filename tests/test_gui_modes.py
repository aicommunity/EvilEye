"""
Tests for GUI modes (headless, hidden, visible).
"""

import unittest
import json
import tempfile
import os
from pathlib import Path

from evileye.gui import GUIMode, determine_gui_mode


class TestGUIModes(unittest.TestCase):
    """Test GUI mode determination."""
    
    def test_headless_mode_from_cli(self):
        """Test headless mode when CLI gui=False."""
        config = {"controller": {}}
        mode = determine_gui_mode(config, cli_gui=False)
        self.assertEqual(mode, GUIMode.HEADLESS)
    
    def test_visible_mode_from_cli(self):
        """Test visible mode when CLI gui=True."""
        config = {"controller": {}}
        mode = determine_gui_mode(config, cli_gui=True)
        self.assertEqual(mode, GUIMode.VISIBLE)
    
    def test_hidden_mode_from_config(self):
        """Test hidden mode from config."""
        config = {"controller": {"gui_mode": "hidden"}}
        mode = determine_gui_mode(config, cli_gui=True)
        self.assertEqual(mode, GUIMode.HIDDEN)
    
    def test_headless_mode_from_config(self):
        """Test headless mode from config."""
        config = {"controller": {"gui_mode": "headless"}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.HEADLESS)
    
    def test_visible_mode_from_config(self):
        """Test visible mode from config."""
        config = {"controller": {"gui_mode": "visible"}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.VISIBLE)
    
    def test_legacy_gui_enabled_false(self):
        """Test legacy config: gui_enabled=False."""
        config = {"controller": {"gui_enabled": False}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.HEADLESS)
    
    def test_legacy_show_main_gui_false(self):
        """Test legacy config: show_main_gui=False."""
        config = {"controller": {"gui_enabled": True, "show_main_gui": False}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.HIDDEN)
    
    def test_legacy_show_main_gui_true(self):
        """Test legacy config: show_main_gui=True."""
        config = {"controller": {"gui_enabled": True, "show_main_gui": True}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.VISIBLE)
    
    def test_default_visible(self):
        """Test default mode is visible."""
        config = {"controller": {}}
        mode = determine_gui_mode(config, cli_gui=None)
        self.assertEqual(mode, GUIMode.VISIBLE)
    
    def test_cli_overrides_config(self):
        """Test CLI argument overrides config."""
        config = {"controller": {"gui_mode": "hidden"}}
        mode = determine_gui_mode(config, cli_gui=False)
        self.assertEqual(mode, GUIMode.HEADLESS)  # CLI should override


class TestGUIManager(unittest.TestCase):
    """Test GUIManager initialization."""
    
    def test_headless_mode_no_qt_app(self):
        """Test that headless mode doesn't create QApplication."""
        from evileye.gui import GUIManager
        
        config = {"controller": {}}
        manager = GUIManager(GUIMode.HEADLESS, config)
        
        # Headless mode should not create QApplication
        self.assertIsNone(manager.qt_app)
        self.assertIsNone(manager.main_window)
    
    def test_flag_file_path_initialization(self):
        """Test that flag file path is initialized in constructor."""
        from evileye.gui import GUIManager
        
        config = {"controller": {"gui_flag_file": "test/.show_gui"}}
        manager = GUIManager(GUIMode.HIDDEN, config)
        
        # Flag file path should be initialized in constructor
        self.assertIsNotNone(manager.flag_file_path)
        self.assertEqual(str(manager.flag_file_path), "test/.show_gui")
    
    def test_default_flag_file_path(self):
        """Test default flag file path."""
        from evileye.gui import GUIManager
        
        config = {"controller": {}}
        manager = GUIManager(GUIMode.HIDDEN, config)
        
        # Default flag file path
        self.assertIsNotNone(manager.flag_file_path)
        self.assertEqual(str(manager.flag_file_path), "EvilEyeData/.show_gui")


class TestVisualizationAdapter(unittest.TestCase):
    """Test VisualizationAdapter."""
    
    def test_adapter_without_visualizer(self):
        """Test adapter without visualizer."""
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        adapter = VisualizationAdapter()
        self.assertFalse(adapter.is_available())
        self.assertEqual(adapter.get_params(), {})
    
    def test_adapter_set_visualizer(self):
        """Test setting visualizer in adapter."""
        from evileye.gui.visualization_adapter import VisualizationAdapter
        
        adapter = VisualizationAdapter()
        
        # Create mock visualizer
        class MockVisualizer:
            def start(self):
                pass
            def stop(self):
                pass
            def get_params(self):
                return {"test": "value"}
        
        mock_visualizer = MockVisualizer()
        adapter.set_visualizer(mock_visualizer)
        
        self.assertTrue(adapter.is_available())
        self.assertEqual(adapter.get_params(), {"test": "value"})


if __name__ == '__main__':
    unittest.main()
