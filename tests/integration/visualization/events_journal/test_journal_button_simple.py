#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_button_logic():
    """Test the journal button configuration logic without creating full windows"""
    
    # Test 1: use_database = True
    test_logger.info("=== Test 1: use_database = True ===")
    use_database = True
    db_journal_win = "DatabaseJournalWindow"  # Mock
    
    if use_database:
        button_enabled = True
        button_text = "&DB journal"
        button_tooltip = "Open database events journal"
    else:
        if db_journal_win is not None:
            button_enabled = True
            button_text = "&Journal"
            button_tooltip = "Open events journal (JSON mode)"
        else:
            button_enabled = False
            button_text = "&Journal"
            button_tooltip = "Journal is not available (database disabled)"
    
    test_logger.info(f"DB mode - Button enabled: {button_enabled}")
    test_logger.info(f"DB mode - Button text: {button_text}")
    test_logger.info(f"DB mode - Button tooltip: {button_tooltip}")
    
    # Test 2: use_database = False, journal created successfully
    test_logger.info("\n=== Test 2: use_database = False, journal created ===")
    use_database = False
    db_journal_win = "EventsJournalJson"  # Mock
    
    if use_database:
        button_enabled = True
        button_text = "&DB journal"
        button_tooltip = "Open database events journal"
    else:
        if db_journal_win is not None:
            button_enabled = True
            button_text = "&Journal"
            button_tooltip = "Open events journal (JSON mode)"
        else:
            button_enabled = False
            button_text = "&Journal"
            button_tooltip = "Journal is not available (database disabled)"
    
    test_logger.info(f"JSON mode - Button enabled: {button_enabled}")
    test_logger.info(f"JSON mode - Button text: {button_text}")
    test_logger.info(f"JSON mode - Button tooltip: {button_tooltip}")
    
    # Test 3: use_database = False, journal creation failed
    test_logger.info("\n=== Test 3: use_database = False, journal creation failed ===")
    use_database = False
    db_journal_win = None  # Mock
    
    if use_database:
        button_enabled = True
        button_text = "&DB journal"
        button_tooltip = "Open database events journal"
    else:
        if db_journal_win is not None:
            button_enabled = True
            button_text = "&Journal"
            button_tooltip = "Open events journal (JSON mode)"
        else:
            button_enabled = False
            button_text = "&Journal"
            button_tooltip = "Journal is not available (database disabled)"
    
    test_logger.info(f"Failed mode - Button enabled: {button_enabled}")
    test_logger.info(f"Failed mode - Button text: {button_text}")
    test_logger.info(f"Failed mode - Button tooltip: {button_tooltip}")
    
    test_logger.info("\n=== Expected behavior ===")
    test_logger.info("1. use_database=True: Button enabled, text='&DB journal'")
    test_logger.info("2. use_database=False + journal exists: Button enabled, text='&Journal'")
    test_logger.info("3. use_database=False + no journal: Button disabled, text='&Journal'")
    
    test_logger.info("\n=== Test completed ===")
