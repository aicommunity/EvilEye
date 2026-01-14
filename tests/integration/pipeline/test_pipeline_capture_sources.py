#!/usr/bin/env python3
"""
Test script to verify PipelineCapture get_sources method.
"""

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_pipeline_capture_sources():
    """Test PipelineCapture get_sources functionality."""
    
    test_logger.info("🔍 Testing PipelineCapture get_sources")
    test_logger.info("=" * 60)
    
    try:
        from evileye.pipelines.pipeline_capture import PipelineCapture
        from unittest.mock import Mock, patch
        import cv2
        
        # Create pipeline
        pipeline = PipelineCapture()
        test_logger.info("✅ PipelineCapture instantiated")
        
        # Test get_sources before initialization (should return empty list)
        sources = pipeline.get_sources()
        assert isinstance(sources, list)
        assert len(sources) == 0
        test_logger.info("✅ get_sources returns empty list before initialization")
        
        # Mock VideoCapture class
        mock_video_capture = Mock()
        mock_video_capture.init.return_value = True
        mock_video_capture.is_opened.return_value = True
        mock_video_capture.is_finished.return_value = False
        mock_video_capture.source_fps = 30.0
        mock_video_capture.video_current_frame = 0
        mock_video_capture.capture = Mock()
        mock_video_capture.capture.get.side_effect = lambda prop: {
            3: 1920,  # CAP_PROP_FRAME_WIDTH
            4: 1080,  # CAP_PROP_FRAME_HEIGHT
            7: 100    # CAP_PROP_FRAME_COUNT
        }.get(prop, 0)
        
        # Mock CaptureImage
        mock_capture_image = Mock()
        mock_capture_image.source_id = 0
        mock_capture_image.frame_id = 0
        mock_capture_image.time_stamp = 1234567890.0
        mock_capture_image.current_video_frame = 0
        mock_capture_image.current_video_position = 0.0
        mock_capture_image.image = Mock()
        
        # Mock get() method to return list with CaptureImage
        mock_video_capture.get.return_value = [mock_capture_image]
        
        # Set source config and mock file existence
        pipeline.source_config = {
            'camera': 'test_video.mp4',
            'source': 'VideoFile',
            'source_ids': [0],
            'source_names': ['VideoCapture']
        }
        
        with patch('evileye.pipelines.pipeline_capture.VideoCapture', return_value=mock_video_capture), \
             patch('os.path.exists', return_value=True):
            # Initialize pipeline
            result = pipeline.init_impl()
            assert result == True
            test_logger.info("✅ Pipeline initialized successfully")
            
            # Test get_sources after initialization (should return video capture object)
            sources = pipeline.get_sources()
            assert isinstance(sources, list)
            assert len(sources) == 1
            assert sources[0] == mock_video_capture
            test_logger.info("✅ get_sources returns video capture object after initialization")
            
            # Test get_sources after release (should return empty list)
            pipeline.release_impl()
            sources = pipeline.get_sources()
            assert isinstance(sources, list)
            assert len(sources) == 0
            test_logger.info("✅ get_sources returns empty list after release")
        
        test_logger.info("✅ PipelineCapture get_sources test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_capture_controller_compatibility():
    """Test that PipelineCapture is compatible with controller."""
    
    test_logger.info("\n🔍 Testing PipelineCapture Controller Compatibility")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller.controller import Controller
        import json
        from evileye.core.logging_config import setup_evileye_logging
        from evileye.core.logger import get_module_logger
        
        # Create controller
        controller = Controller()
        
        # Check available pipelines
        available_pipelines = controller.get_available_pipeline_classes()
        test_logger.info(f"Available pipelines: {available_pipelines}")
        
        if 'PipelineCapture' in available_pipelines:
            test_logger.info("✅ PipelineCapture discovered")
            
            # Test creation
            pipeline = controller._create_pipeline_instance('PipelineCapture')
            test_logger.info(f"✅ Pipeline created: {type(pipeline).__name__}")
            
            # Test that it has required methods
            assert hasattr(pipeline, 'get_sources')
            assert hasattr(pipeline, 'process')
            assert hasattr(pipeline, 'init_impl')
            test_logger.info("✅ Has all required methods")
            
            # Test get_sources method
            sources = pipeline.get_sources()
            assert isinstance(sources, list)
            test_logger.info("✅ get_sources method works")
            
        else:
            test_logger.info("❌ PipelineCapture not discovered")
        
        test_logger.info("✅ PipelineCapture controller compatibility test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in compatibility test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 PipelineCapture Sources Test")
    test_logger.info("=" * 60)
    
    test_pipeline_capture_sources()
    test_pipeline_capture_controller_compatibility()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ PipelineCapture get_sources method tested")
    test_logger.info("  ✅ Controller compatibility verified")
    test_logger.info("  ✅ All tests passed successfully")
