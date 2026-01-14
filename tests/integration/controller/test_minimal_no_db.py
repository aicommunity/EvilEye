from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
#!/usr/bin/env python3
"""
Minimal test for controller without database.
"""

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_minimal_init():
    """Test minimal controller initialization without database."""
    
    test_logger.info("🔍 Testing Minimal Controller Init")
    test_logger.info("=" * 60)
    
    try:
        from evileye.controller import controller
        
        # Create controller
        ctrl = controller.Controller()
        test_logger.info("✅ Controller created")
        
        # Set minimal parameters
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
        test_logger.info("Initializing controller...")
        ctrl.init(test_params)
        test_logger.info("✅ Controller initialized")
        
        # Check results
        test_logger.info(f"use_database: {ctrl.use_database}")
        test_logger.info(f"db_controller: {ctrl.db_controller}")
        test_logger.info(f"obj_handler: {ctrl.obj_handler is not None}")
        test_logger.info(f"events_processor: {ctrl.events_processor is not None}")
        
        test_logger.info("✅ Test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
