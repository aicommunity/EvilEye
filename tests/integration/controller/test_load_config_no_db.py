#!/usr/bin/env python3
"""
Test loading configuration without database.
"""

import json
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_load_config():
    """Test loading configuration file without database."""
    
    test_logger.info("🔍 Testing Configuration Loading")
    test_logger.info("=" * 60)
    
    try:
        # Load configuration
        with open('test_config_no_database.json', 'r') as f:
            config = json.load(f)
        
        test_logger.info("✅ Configuration loaded successfully")
        test_logger.info(f"use_database: {config['controller']['use_database']}")
        
        # Test controller initialization
        from evileye.controller import controller
        ctrl = controller.Controller()
        test_logger.info("✅ Controller created")
        
        # Initialize with config
        ctrl.init(config)
        test_logger.info("✅ Controller initialized with config")
        
        # Check results
        test_logger.info(f"Controller use_database: {ctrl.use_database}")
        test_logger.info(f"Database controller: {ctrl.db_controller}")
        test_logger.info(f"Object handler: {ctrl.obj_handler is not None}")
        test_logger.info(f"Events processor: {ctrl.events_processor is not None}")
        
        test_logger.info("✅ Test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
