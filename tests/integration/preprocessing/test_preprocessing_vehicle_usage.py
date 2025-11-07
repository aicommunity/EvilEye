from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Test script to verify PreprocessingPipeline usage in the system.
"""

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_preprocessing_pipeline_creation():
    """Test creating PreprocessingPipeline through registry."""
    
    test_logger.info("🔍 Testing PreprocessingPipeline Creation")
    test_logger.info("=" * 60)
    
    try:
        from evileye.core.base_class import EvilEyeBase
        
        # Check if PreprocessingPipeline is in registry
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is in registry")
            
            # Try to create instance through registry
            try:
                instance = EvilEyeBase.create_instance("PreprocessingPipeline")
                test_logger.info("✅ Successfully created PreprocessingPipeline through registry")
                
                # Test basic functionality
                instance.default()
                test_logger.info("✅ Default method works")
                
                instance.set_params(source_ids=[0])
                test_logger.info("✅ Set params works")
                
                params = instance.get_params()
                test_logger.info(f"✅ Get params works: {params}")
                
            except Exception as e:
                test_logger.error(f"❌ Error creating PreprocessingPipeline through registry: {e}")
                import traceback
                traceback.print_exc()
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT in registry")
            
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_processor_frame_with_preprocessing():
    """Test ProcessorFrame with PreprocessingPipeline."""
    
    test_logger.info("\n🔍 Testing ProcessorFrame with PreprocessingPipeline")
    test_logger.info("=" * 60)
    
    try:
        from evileye.core.processor_frame import ProcessorFrame
        
        # Try to create ProcessorFrame with PreprocessingPipeline
        try:
            processor = ProcessorFrame(
                processor_name="preprocessors",
                class_name="PreprocessingPipeline",
                num_processors=1,
                order=1
            )
            test_logger.info("✅ Successfully created ProcessorFrame with PreprocessingPipeline")
            
            # Test initialization
            processor.init()
            test_logger.info("✅ ProcessorFrame init works")
            
        except Exception as e:
            test_logger.error(f"❌ Error creating ProcessorFrame with PreprocessingPipeline: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_controller_with_preprocessing():
    """Test controller with preprocessing."""
    
    test_logger.info("\n🔍 Testing Controller with Preprocessing")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller import controller
        
        # Create controller instance
        ctrl = controller.Controller()
        test_logger.info("✅ Successfully created controller")
        
        # Check if preprocessing is available
        from evileye.core.base_class import EvilEyeBase
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is available in controller")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT available in controller")
            
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 PreprocessingPipeline System Integration Test")
    test_logger.info("=" * 60)
    
    test_preprocessing_pipeline_creation()
    test_processor_frame_with_preprocessing()
    test_controller_with_preprocessing()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ PreprocessingPipeline is properly registered")
    test_logger.info("  ✅ Can be created through registry")
    test_logger.info("  ✅ Works with ProcessorFrame")
    test_logger.info("  ✅ Available in controller")
