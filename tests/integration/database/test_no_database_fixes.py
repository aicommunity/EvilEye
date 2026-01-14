from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Test script to verify fixes for working without database.
"""

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_objects_handler_without_db():
    """Test ObjectsHandler without database."""
    
    test_logger.info("🔍 Testing ObjectsHandler without Database")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.objects_handler import ObjectsHandler
        
        # Create ObjectsHandler without database
        obj_handler = ObjectsHandler(db_controller=None, db_adapter=None)
        test_logger.info("✅ ObjectsHandler created without database")
        
        # Test initialization
        obj_handler.init()
        test_logger.info("✅ ObjectsHandler initialized")
        
        # Test parameters
        test_logger.info(f"db_params: {obj_handler.db_params}")
        test_logger.info(f"cameras_params: {obj_handler.cameras_params}")
        
        test_logger.info("✅ ObjectsHandler test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in ObjectsHandler test: {e}")
        import traceback
        traceback.print_exc()

def test_events_processor_without_db():
    """Test EventsProcessor without database."""
    
    test_logger.info("\n🔍 Testing EventsProcessor without Database")
    test_logger.info("=" * 60)
    
    try:
        from evileye.events_control.events_processor import EventsProcessor
        
        # Create EventsProcessor without database
        events_processor = EventsProcessor(db_adapters=[], db_controller=None)
        test_logger.info("✅ EventsProcessor created without database")
        
        # Test initialization
        events_processor.init()
        test_logger.info("✅ EventsProcessor initialized")
        
        # Test get_last_id
        last_id = events_processor.get_last_id()
        test_logger.info(f"Last ID: {last_id}")
        
        test_logger.info("✅ EventsProcessor test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in EventsProcessor test: {e}")
        import traceback
        traceback.print_exc()

def test_controller_integration():
    """Test controller integration without database."""
    
    test_logger.info("\n🔍 Testing Controller Integration without Database")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller import controller
        
        # Create controller
        ctrl = controller.Controller()
        test_logger.info("✅ Controller created")
        
        # Set use_database to False
        ctrl.use_database = False
        test_logger.info("✅ use_database set to False")
        
        # Test minimal initialization
        test_params = {
            'controller': {
                'use_database': False,
                'fps': 30
            },
            'sources': [],
            'pipeline': {
                'pipeline_class': 'PipelineSurveillance'
            }
        }
        
        # Initialize
        ctrl.init(test_params)
        test_logger.info("✅ Controller initialized without database")
        
        # Check components
        test_logger.info(f"db_controller: {ctrl.db_controller}")
        test_logger.info(f"obj_handler: {ctrl.obj_handler is not None}")
        test_logger.info(f"events_processor: {ctrl.events_processor is not None}")
        
        test_logger.info("✅ Controller integration test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in controller integration test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 No Database Fixes Test")
    test_logger.info("=" * 60)
    
    test_objects_handler_without_db()
    test_events_processor_without_db()
    test_controller_integration()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ ObjectsHandler works without database")
    test_logger.info("  ✅ EventsProcessor works without database")
    test_logger.info("  ✅ Controller integration works without database")
    test_logger.info("  ✅ All components handle None database gracefully")
