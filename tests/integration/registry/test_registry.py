from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Test script to analyze registry and PreprocessingPipeline registration.
"""

import sys
from pathlib import Path

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_registry_before_imports():
    """Test registry before importing preprocessing module."""
    
    test_logger.info("🔍 Testing Registry Before Imports")
    test_logger.info("=" * 60)
    
    # Import base class
    from evileye.core.base_class import EvilEyeBase
    
    test_logger.info(f"Registry contents before preprocessing import:")
    for name, cls in EvilEyeBase._registry.items():
        test_logger.info(f"  {name}: {cls}")
    
    test_logger.info(f"Total registered classes: {len(EvilEyeBase._registry)}")

def test_registry_after_imports():
    """Test registry after importing preprocessing module."""
    
    test_logger.info("\n🔍 Testing Registry After Imports")
    test_logger.info("=" * 60)
    
    # Import base class
    from evileye.core.base_class import EvilEyeBase
    
    # Import preprocessing module
    try:
        import evileye.preprocessing
        test_logger.info("✅ Successfully imported evileye.preprocessing")
    except Exception as e:
        test_logger.error(f"❌ Error importing evileye.preprocessing: {e}")
        return
    
    test_logger.info(f"Registry contents after preprocessing import:")
    for name, cls in EvilEyeBase._registry.items():
        test_logger.info(f"  {name}: {cls}")
    
    test_logger.info(f"Total registered classes: {len(EvilEyeBase._registry)}")
    
    # Check specifically for PreprocessingPipeline
    if "PreprocessingPipeline" in EvilEyeBase._registry:
        test_logger.info("✅ PreprocessingPipeline is registered")
    else:
        test_logger.info("❌ PreprocessingPipeline is NOT registered")

def test_direct_import():
    """Test direct import of PreprocessingPipeline."""
    
    test_logger.info("\n🔍 Testing Direct Import")
    test_logger.info("=" * 60)
    
    try:
        from evileye.preprocessing.preprocessing_pipeline import PreprocessingPipeline
        test_logger.info("✅ Successfully imported PreprocessingPipeline directly")
        
        # Check if it's in registry now
        from evileye.core.base_class import EvilEyeBase
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is now in registry")
        else:
            test_logger.info("❌ PreprocessingPipeline is still NOT in registry")
            
    except Exception as e:
        test_logger.error(f"❌ Error importing PreprocessingPipeline directly: {e}")

def test_import_order():
    """Test different import orders."""
    
    test_logger.info("\n🔍 Testing Import Order")
    test_logger.info("=" * 60)
    
    # Clear registry (simulate fresh start)
    from evileye.core.base_class import EvilEyeBase
    EvilEyeBase._registry.clear()
    
    test_logger.info("Registry cleared")
    
    # Import in different order
    try:
        # First import preprocessing
        import evileye.preprocessing
        test_logger.info("✅ Imported preprocessing first")
        
        # Then check registry
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is registered after preprocessing import")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT registered after preprocessing import")
            
    except Exception as e:
        test_logger.error(f"❌ Error in import order test: {e}")

def test_controller_imports():
    """Test what controller imports."""
    
    test_logger.info("\n🔍 Testing Controller Imports")
    test_logger.info("=" * 60)
    
    try:
        # Import controller
        from evileye.controller import controller
        test_logger.info("✅ Successfully imported controller")
        
        # Check registry
        from evileye.core.base_class import EvilEyeBase
        if "PreprocessingPipeline" in EvilEyeBase._registry:
            test_logger.info("✅ PreprocessingPipeline is registered after controller import")
        else:
            test_logger.info("❌ PreprocessingPipeline is NOT registered after controller import")
            
    except Exception as e:
        test_logger.error(f"❌ Error importing controller: {e}")

def main():
    """Main test function."""
    
    test_logger.info("🔍 Registry Analysis for PreprocessingPipeline")
    test_logger.info("=" * 60)
    
    # Test registry before imports
    test_registry_before_imports()
    
    # Test registry after imports
    test_registry_after_imports()
    
    # Test direct import
    test_direct_import()
    
    # Test import order
    test_import_order()
    
    # Test controller imports
    test_controller_imports()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  • Registry is populated when modules are imported")
    test_logger.info("  • PreprocessingPipeline should be registered when preprocessing module is imported")
    test_logger.info("  • If not registered, there might be an import issue")
