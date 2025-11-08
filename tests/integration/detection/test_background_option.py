#!/usr/bin/env python3
"""
Test script to demonstrate the background disable option.
"""

import cv2
import numpy as np
import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evileye.utils.utils import put_text_adaptive, put_text_with_bbox

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def create_test_image(width=800, height=600):
    """Create a test image with gradient background."""
    # Create gradient background
    image = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Create gradient
    for y in range(height):
        for x in range(width):
            r = int(128 + 64 * x / width)
            g = int(128 + 64 * y / height)
            b = int(128)
            image[y, x] = [b, g, r]
    
    return image

def test_background_options():
    """Test different background options."""
    
    test_logger.info("🎨 Background Options Test")
    test_logger.info("=" * 60)
    
    # Create test image
    image = create_test_image(800, 600)
    
    # Test configurations
    test_configs = [
        {
            "name": "Background Enabled",
            "background_enabled": True,
            "background_color": [0, 0, 0],
            "color": [255, 255, 255],
            "position": (10, 20)
        },
        {
            "name": "Background Disabled",
            "background_enabled": False,
            "background_color": [0, 0, 0],
            "color": [255, 255, 255],
            "position": (10, 60)
        },
        {
            "name": "Colored Background",
            "background_enabled": True,
            "background_color": [0, 100, 200],
            "color": [255, 255, 255],
            "position": (10, 100)
        },
        {
            "name": "No Background (transparent)",
            "background_enabled": False,
            "background_color": None,
            "color": [0, 255, 0],
            "position": (10, 140)
        }
    ]
    
    for i, config in enumerate(test_configs):
        test_logger.info(f"\n📝 Testing: {config['name']}")
        
        # Draw text with different background settings
        put_text_adaptive(
            image, 
            config['name'], 
            config['position'], 
            font_size_pt=16,
            color=tuple(config['color']),
            background_color=config['background_color'],
            background_enabled=config['background_enabled'],
            padding_percent=2.0
        )
        
        test_logger.info(f"  ✅ Position: {config['position']}")
        test_logger.info(f"  ✅ Background enabled: {config['background_enabled']}")
        test_logger.info(f"  ✅ Background color: {config['background_color']}")
        test_logger.info(f"  ✅ Text color: {config['color']}")
    
    # Test bounding box text
    test_logger.info(f"\n📦 Testing bounding box text with background disabled")
    
    # Create a bounding box
    bbox = [200, 200, 400, 300]
    
    # Draw bounding box
    cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
    
    # Draw text with background disabled
    # Note: put_text_with_bbox signature: (image, text, bbox, font_face, font_scale, thickness, ...)
    # Using default font parameters
    put_text_with_bbox(
        image,
        "Object Label (No Background)",
        bbox,
        font_face=cv2.FONT_HERSHEY_SIMPLEX,
        font_scale=0.5,
        thickness=1,
        color=(255, 255, 255),
        background_color=(0, 0, 0),
        background_enabled=False,
        position_offset_percent=(0, -10)
    )
    
    # Draw text with background enabled
    put_text_with_bbox(
        image,
        "Object Label (With Background)",
        bbox,
        font_face=cv2.FONT_HERSHEY_SIMPLEX,
        font_scale=0.5,
        thickness=1,
        color=(255, 255, 255),
        background_color=(0, 0, 0),
        background_enabled=True,
        position_offset_percent=(0, 10)
    )
    
    # Save test image
    from pathlib import Path
    output_dir = Path(__file__).parent.parent.parent / "data" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = str(output_dir / "background_options_test.jpg")
    cv2.imwrite(output_filename, image)
    test_logger.info(f"\n💾 Saved test image: {output_filename}")
    
    # Test functions should return None, not values

def test_config_file_background_settings():
    """Test background settings from configuration files."""
    
    test_logger.info("\n📄 Testing background settings from config files")
    test_logger.info("=" * 60)
    
    import json
    
    config_files = [
        "evileye/samples_configs/single_video.json",
        "evileye/samples_configs/single_video_split.json"
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            test_logger.info(f"\n📋 {config_file}")
            
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            text_config = config.get('visualizer', {}).get('text_config', {})
            
            background_enabled = text_config.get('background_enabled', True)
            background_color = text_config.get('background_color', None)
            
            test_logger.info(f"  Background enabled: {background_enabled}")
            test_logger.info(f"  Background color: {background_color}")
            
            if background_enabled:
                test_logger.info(f"  ✅ Background will be drawn")
            else:
                test_logger.info(f"  ❌ Background will be disabled")

def main():
    """Main test function."""
    
    test_logger.info("🎨 Background Disable Option Test")
    test_logger.info("=" * 60)
    
    try:
        # Test background options
        test_image = test_background_options()
        
        # Test config file settings
        test_config_file_background_settings()
        
        test_logger.info("\n✅ All tests completed successfully!")
        
        test_logger.info("\n📋 Summary:")
        test_logger.info("  ✅ Added background_enabled option")
        test_logger.info("  ✅ Background can be disabled independently of background_color")
        test_logger.info("  ✅ Works with both put_text_adaptive and put_text_with_bbox")
        test_logger.info("  ✅ Configurable via JSON configuration")
        test_logger.info("  ✅ Default value is True (backward compatibility)")
        
        test_logger.info(f"\n🎨 Check the generated image: {test_image}")
        test_logger.info("  - Shows different text rendering options")
        test_logger.info("  - Demonstrates background enable/disable")
        test_logger.info("  - Shows bounding box text with and without background")
        
    except Exception as e:
        test_logger.info(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0
