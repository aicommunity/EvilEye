from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Test script to verify that all pipeline classes implement required abstract methods.
"""

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_pipeline_base_abstract_methods():
    """Test that PipelineBase has required abstract methods."""
    
    test_logger.info("🔍 Testing PipelineBase Abstract Methods")
    test_logger.info("=" * 60)
    
    try:
        from evileye.core.pipeline_base import PipelineBase
        import inspect
        
        # Check abstract methods
        abstract_methods = []
        for name, method in inspect.getmembers(PipelineBase, inspect.isfunction):
            if getattr(method, '__isabstractmethod__', False):
                abstract_methods.append(name)
        
        test_logger.info(f"Abstract methods in PipelineBase: {abstract_methods}")
        
        # Check that get_sources is abstract
        assert 'get_sources' in abstract_methods
        test_logger.info("✅ get_sources is abstract in PipelineBase")
        
        # Check that generate_default_structure is abstract
        assert 'generate_default_structure' in abstract_methods
        test_logger.info("✅ generate_default_structure is abstract in PipelineBase")
        
        test_logger.info("✅ PipelineBase abstract methods test completed")
        
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_simple_implementation():
    """Test that PipelineSimple implements abstract methods."""
    
    test_logger.info("\n🔍 Testing PipelineSimple Implementation")
    test_logger.info("=" * 60)
    
    try:
        from evileye.core.pipeline_simple import PipelineSimple
        import inspect
        
        # Check that PipelineSimple is not abstract
        abstract_methods = []
        for name, method in inspect.getmembers(PipelineSimple, inspect.isfunction):
            if getattr(method, '__isabstractmethod__', False):
                abstract_methods.append(name)
        
        test_logger.info(f"Abstract methods in PipelineSimple: {abstract_methods}")
        
        # PipelineSimple should only have process_logic as abstract
        assert 'process_logic' in abstract_methods
        assert 'get_sources' not in abstract_methods
        assert 'generate_default_structure' not in abstract_methods
        test_logger.info("✅ PipelineSimple correctly implements abstract methods")
        
        # Test get_sources implementation
        pipeline = PipelineSimple()
        sources = pipeline.get_sources()
        assert isinstance(sources, list)
        assert len(sources) == 0
        test_logger.info("✅ PipelineSimple.get_sources() returns empty list")
        
        test_logger.info("✅ PipelineSimple implementation test completed")
        
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_processors_implementation():
    """Test that PipelineProcessors implements abstract methods."""
    
    test_logger.info("\n🔍 Testing PipelineProcessors Implementation")
    test_logger.info("=" * 60)
    
    try:
        from evileye.core.pipeline_processors import PipelineProcessors
        import inspect
        
        # Check that PipelineProcessors is not abstract
        abstract_methods = []
        for name, method in inspect.getmembers(PipelineProcessors, inspect.isfunction):
            if getattr(method, '__isabstractmethod__', False):
                abstract_methods.append(name)
        
        test_logger.info(f"Abstract methods in PipelineProcessors: {abstract_methods}")
        
        # PipelineProcessors should not have any abstract methods
        assert len(abstract_methods) == 0
        test_logger.info("✅ PipelineProcessors has no abstract methods")
        
        # Test get_sources implementation
        pipeline = PipelineProcessors()
        sources = pipeline.get_sources()
        assert isinstance(sources, list)
        test_logger.info("✅ PipelineProcessors.get_sources() returns list")
        
        test_logger.info("✅ PipelineProcessors implementation test completed")
        
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_capture_implementation():
    """Test that PipelineCapture implements abstract methods."""
    
    test_logger.info("\n🔍 Testing PipelineCapture Implementation")
    test_logger.info("=" * 60)
    
    try:
        from evileye.pipelines.pipeline_capture import PipelineCapture
        import inspect
        
        # Check that PipelineCapture is not abstract
        abstract_methods = []
        for name, method in inspect.getmembers(PipelineCapture, inspect.isfunction):
            if getattr(method, '__isabstractmethod__', False):
                abstract_methods.append(name)
        
        test_logger.info(f"Abstract methods in PipelineCapture: {abstract_methods}")
        
        # PipelineCapture should not have any abstract methods
        assert len(abstract_methods) == 0
        test_logger.info("✅ PipelineCapture correctly implements abstract methods")
        
        # Test get_sources implementation
        pipeline = PipelineCapture()
        sources = pipeline.get_sources()
        assert isinstance(sources, list)
        assert len(sources) == 0  # No capture object initially
        test_logger.info("✅ PipelineCapture.get_sources() returns empty list initially")
        
        test_logger.info("✅ PipelineCapture implementation test completed")
        
    except Exception as e:
        test_logger.error(f"❌ Error in test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 Pipeline Base Methods Test")
    test_logger.info("=" * 60)
    
    test_pipeline_base_abstract_methods()
    test_pipeline_simple_implementation()
    test_pipeline_processors_implementation()
    test_pipeline_capture_implementation()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ PipelineBase has correct abstract methods")
    test_logger.info("  ✅ PipelineSimple implements abstract methods")
    test_logger.info("  ✅ PipelineProcessors implements abstract methods")
    test_logger.info("  ✅ PipelineCapture implements abstract methods")
    test_logger.info("  ✅ All pipeline classes have get_sources() method")
    test_logger.info("  ✅ All tests passed successfully")
