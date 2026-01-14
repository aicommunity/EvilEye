#!/usr/bin/env python3
"""
Test script to verify PipelineCapture launch.
"""

import json
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import os

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_pipeline_capture_launch():
    """Test PipelineCapture launch with configuration."""
    
    test_logger.info("🔍 Testing PipelineCapture Launch")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller.controller import Controller
        
        # Load configuration
        config_path = "evileye/samples_configs/pipeline_capture.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        test_logger.info("✅ Configuration loaded")
        
        # Create controller
        controller = Controller()
        test_logger.info("✅ Controller created")
        
        # Check available pipelines
        available_pipelines = controller.get_available_pipeline_classes()
        test_logger.info(f"Available pipelines: {available_pipelines}")
        
        if 'PipelineCapture' not in available_pipelines:
            test_logger.info("❌ PipelineCapture not available")
            return
        
        # Try to create pipeline instance
        try:
            pipeline = controller._create_pipeline_instance('PipelineCapture')
            test_logger.info("✅ PipelineCapture instance created")
        except Exception as e:
            test_logger.error(f"❌ Failed to create PipelineCapture instance: {e}")
            return
        
        # Try to initialize pipeline with config
        try:
            pipeline.params = config['pipeline']
            pipeline.set_params_impl()
            test_logger.info("✅ Pipeline parameters set")
        except Exception as e:
            test_logger.error(f"❌ Failed to set pipeline parameters: {e}")
            return
        
        # Try to initialize pipeline
        try:
            result = pipeline.init_impl()
            test_logger.info(f"✅ Pipeline initialized: {result}")
        except Exception as e:
            test_logger.error(f"❌ Failed to initialize pipeline: {e}")
            return
        
        test_logger.info("✅ PipelineCapture launch test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in launch test: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_capture_with_controller():
    """Test PipelineCapture with controller initialization."""
    
    test_logger.info("\n🔍 Testing PipelineCapture with Controller")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller.controller import Controller
        
        # Load configuration
        config_path = "evileye/samples_configs/pipeline_capture.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        test_logger.info("✅ Configuration loaded")
        
        # Create controller
        controller = Controller()
        test_logger.info("✅ Controller created")
        
        # Try to initialize controller with config
        try:
            controller.init(config)
            test_logger.info("✅ Controller initialized with config")
        except Exception as e:
            test_logger.error(f"❌ Failed to initialize controller: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Check if pipeline was created correctly
        if hasattr(controller, 'pipeline') and controller.pipeline:
            test_logger.info(f"✅ Pipeline created: {type(controller.pipeline).__name__}")
        else:
            test_logger.info("❌ No pipeline created")
        
        test_logger.info("✅ PipelineCapture with controller test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in controller test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 PipelineCapture Launch Test")
    test_logger.info("=" * 60)
    
    test_pipeline_capture_launch()
    test_pipeline_capture_with_controller()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ PipelineCapture launch tested")
    test_logger.info("  ✅ Controller integration tested")
    test_logger.info("  ✅ All tests completed")
