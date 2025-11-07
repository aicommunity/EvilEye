from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Debug script to analyze PreprocessingPipeline registration issue.
"""

import sys
from pathlib import Path

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_registry_debug():
    """Debug registry registration."""
    
    test_logger.info("🔍 Debug Registry Registration")
    test_logger.info("=" * 60)
    
    # Clear registry
    from evileye.core.base_class import EvilEyeBase
    EvilEyeBase._registry.clear()
    test_logger.info("Registry cleared")
    
    # Check registry before any imports
    test_logger.info(f"Registry before imports: {len(EvilEyeBase._registry)} items")
    
    # Import preprocessing step by step
    try:
        test_logger.info("1. Importing preprocessing_base...")
        import evileye.preprocessing.preprocessing_base
        test_logger.info(f"   Registry after preprocessing_base: {len(EvilEyeBase._registry)} items")
        
        test_logger.info("2. Importing preprocessing_factory...")
        import evileye.preprocessing.preprocessing_factory
        test_logger.info(f"   Registry after preprocessing_factory: {len(EvilEyeBase._registry)} items")
        
        test_logger.info("3. Importing preprocessing_vehicle...")
        import evileye.preprocessing.preprocessing_vehicle
        test_logger.info(f"   Registry after preprocessing_vehicle: {len(EvilEyeBase._registry)} items")
        
        # Check if PreprocessingPipeline is registered
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is registered!")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT registered!")
            
        # Show all registered classes
        test_logger.info("\nRegistered classes:")
        for name, cls in EvilEyeBase._registry.items():
            test_logger.info(f"  {name}: {cls}")
            
    except Exception as e:
        test_logger.error(f"❌ Error during step-by-step import: {e}")
        import traceback
        traceback.print_exc()

def test_import_evileye_preprocessing():
    """Test importing evileye.preprocessing directly."""
    
    test_logger.info("\n🔍 Test Import evileye.preprocessing")
    test_logger.info("=" * 60)
    
    # Clear registry
    from evileye.core.base_class import EvilEyeBase
    EvilEyeBase._registry.clear()
    test_logger.info("Registry cleared")
    
    try:
        test_logger.info("Importing evileye.preprocessing...")
        import evileye.preprocessing
        test_logger.info(f"Registry after import: {len(EvilEyeBase._registry)} items")
        
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is registered!")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT registered!")
            
    except Exception as e:
        test_logger.error(f"❌ Error importing evileye.preprocessing: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main debug function."""
    
    test_logger.info("🔍 PreprocessingPipeline Registration Debug")
    test_logger.info("=" * 60)
    
    test_registry_debug()
    test_import_evileye_preprocessing()
