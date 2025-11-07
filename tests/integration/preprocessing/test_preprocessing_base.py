from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Test script to check PreprocessingBase inheritance.
"""

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_preprocessing_base():
    """Test PreprocessingBase inheritance."""
    
    test_logger.info("🔍 Testing PreprocessingBase")
    test_logger.info("=" * 60)
    
    try:
        from evileye.preprocessing.preprocessing_base import PreprocessingBase
        from evileye.core.base_class import EvilEyeBase
        
        test_logger.info(f"PreprocessingBase: {PreprocessingBase}")
        test_logger.info(f"EvilEyeBase: {EvilEyeBase}")
        test_logger.info(f"PreprocessingBase.__bases__: {PreprocessingBase.__bases__}")
        
        # Check if PreprocessingBase inherits from EvilEyeBase
        if EvilEyeBase in PreprocessingBase.__bases__:
            test_logger.info("✅ PreprocessingBase correctly inherits from EvilEyeBase")
        else:
            test_logger.info("❌ PreprocessingBase does NOT inherit from EvilEyeBase")
            
    except Exception as e:
        test_logger.error(f"❌ Error testing PreprocessingBase: {e}")
        import traceback
        traceback.print_exc()

def test_preprocessing_pipeline():
    """Test PreprocessingPipeline registration."""
    
    test_logger.info("\n🔍 Testing PreprocessingPipeline")
    test_logger.info("=" * 60)
    
    try:
        from evileye.preprocessing.preprocessing_pipeline import PreprocessingPipeline
        from evileye.core.base_class import EvilEyeBase
        
        test_logger.info(f"PreprocessingPipeline: {PreprocessingPipeline}")
        test_logger.info(f"PreprocessingPipeline.__bases__: {PreprocessingPipeline.__bases__}")
        
        # Check if PreprocessingPipeline is in registry
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is in registry")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT in registry")
            
        # Try to create instance
        try:
            instance = PreprocessingPipeline()
            test_logger.info("✅ Successfully created PreprocessingPipeline instance")
        except Exception as e:
            test_logger.error(f"❌ Error creating PreprocessingPipeline instance: {e}")
            
    except Exception as e:
        test_logger.error(f"❌ Error testing PreprocessingPipeline: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 PreprocessingBase and PreprocessingPipeline Test")
    test_logger.info("=" * 60)
    
    test_preprocessing_base()
    test_preprocessing_pipeline()
