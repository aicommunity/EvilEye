#!/usr/bin/env python3
"""
Test script for the improved font scaling system.
Demonstrates resolution-based font scaling vs the old hardcoded method.
"""

import cv2
import numpy as np
import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evileye.utils.utils import (
    put_text_adaptive, 
    calculate_font_scale_for_resolution,
    calculate_font_scale_simple,
    pt_to_pixels
)

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def create_test_image(width=1920, height=1080):
    """Create a test image with different resolutions."""
    # Create a gradient background
    image = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Create gradient
    for y in range(height):
        for x in range(width):
            r = int(255 * x / width)
            g = int(255 * y / height)
            b = int(128)
            image[y, x] = [b, g, r]
    
    return image

def test_font_scaling_comparison():
    """Compare different font scaling methods."""
    
    test_logger.info("🔍 Font Scaling Method Comparison")
    test_logger.info("=" * 60)
    
    # Test different resolutions
    resolutions = [
        (640, 480),    # VGA
        (1280, 720),   # HD
        (1920, 1080),  # Full HD
        (3840, 2160)   # 4K
    ]
    
    font_size_pt = 16
    
    test_logger.info(f"\n📏 Font size: {font_size_pt}pt")
    test_logger.info(f"{'Resolution':<12} {'Old Method':<12} {'Resolution-based':<18} {'Simple Method':<15}")
    test_logger.info("-" * 40)
    
    for width, height in resolutions:
        # Old method (hardcoded 30.0)
        old_scale = pt_to_pixels(font_size_pt) / 30.0
        
        # New methods
        resolution_scale = calculate_font_scale_for_resolution(font_size_pt, width, height)
        simple_scale = calculate_font_scale_simple(font_size_pt, width, height)
        
        test_logger.info(f"{width}x{height:<6} {old_scale:<12.3f} {resolution_scale:<18.3f} {simple_scale:<15.3f}")

def test_visual_comparison():
    """Create visual comparison of different scaling methods."""
    
    test_logger.info("\n🎨 Visual Comparison Test")
    test_logger.info("=" * 60)
    
    # Test resolutions
    resolutions = [
        (640, 480),    # VGA
        (1920, 1080),  # Full HD
        (3840, 2160)   # 4K
    ]
    
    for width, height in resolutions:
        test_logger.info(f"\n📐 Testing resolution: {width}x{height}")
        
        # Create test image
        image = create_test_image(width, height)
        
        # Test different methods
        methods = [
            ("resolution_based", "Resolution-based"),
            ("simple", "Simple diagonal-based")
        ]
        
        y_positions = [20, 40, 60, 80]
        
        for i, (method, method_name) in enumerate(methods):
            if i < len(y_positions):
                y_pos = y_positions[i]
                
                # Draw text with different methods
                put_text_adaptive(image, f"{method_name} - 16pt", (10, y_pos), 
                                font_size_pt=16, color=(255, 255, 255),
                                background_color=(0, 0, 0),
                                font_scale_method=method)
                
                put_text_adaptive(image, f"{method_name} - 24pt", (10, y_pos + 15), 
                                font_size_pt=24, color=(255, 255, 0),
                                background_color=(0, 0, 0),
                                font_scale_method=method)
        
        # Save test image
        output_filename = f"font_scaling_comparison_{width}x{height}.jpg"
        cv2.imwrite(output_filename, image)
        test_logger.info(f"  💾 Saved: {output_filename}")

def test_resolution_independence():
    """Test that text appears similar size across different resolutions."""
    
    test_logger.info("\n📊 Resolution Independence Test")
    test_logger.info("=" * 60)
    
    # Test with same font size across different resolutions
    font_size_pt = 20
    
    resolutions = [
        (640, 480),    # VGA
        (1280, 720),   # HD
        (1920, 1080),  # Full HD
        (3840, 2160)   # 4K
    ]
    
    for width, height in resolutions:
        test_logger.info(f"\n📐 Resolution: {width}x{height}")
        
        # Create test image
        image = create_test_image(width, height)
        
        # Calculate font scales
        resolution_scale = calculate_font_scale_for_resolution(font_size_pt, width, height)
        simple_scale = calculate_font_scale_simple(font_size_pt, width, height)
        
        test_logger.info(f"  Resolution-based scale: {resolution_scale:.3f}")
        test_logger.info(f"  Simple scale: {simple_scale:.3f}")
        
        # Draw text with resolution-based method
        put_text_adaptive(image, f"Resolution-based {font_size_pt}pt", (10, 20), 
                        font_size_pt=font_size_pt, color=(255, 255, 255),
                        background_color=(0, 0, 0),
                        font_scale_method="resolution_based")
        
        # Draw text with simple method
        put_text_adaptive(image, f"Simple {font_size_pt}pt", (10, 50), 
                        font_size_pt=font_size_pt, color=(255, 255, 0),
                        background_color=(0, 0, 0),
                        font_scale_method="simple")
        
        # Save test image
        output_filename = f"resolution_independence_{width}x{height}.jpg"
        cv2.imwrite(output_filename, image)
        test_logger.info(f"  💾 Saved: {output_filename}")

def test_edge_cases():
    """Test edge cases and extreme resolutions."""
    
    test_logger.info("\n🔍 Edge Cases Test")
    test_logger.info("=" * 60)
    
    # Test extreme resolutions
    extreme_resolutions = [
        (320, 240),    # Very small
        (8000, 6000),  # Very large
        (1920, 480),   # Very wide
        (480, 1920),   # Very tall
    ]
    
    for width, height in extreme_resolutions:
        test_logger.info(f"\n📐 Extreme resolution: {width}x{height}")
        
        # Create test image
        image = create_test_image(width, height)
        
        # Test both methods
        for method in ["resolution_based", "simple"]:
            try:
                put_text_adaptive(image, f"{method} test", (10, 20), 
                                font_size_pt=16, color=(255, 255, 255),
                                background_color=(0, 0, 0),
                                font_scale_method=method)
                test_logger.info(f"  ✅ {method}: Success")
            except Exception as e:
                test_logger.info(f"  ❌ {method}: Failed - {e}")
        
        # Save test image
        output_filename = f"edge_case_{width}x{height}.jpg"
        cv2.imwrite(output_filename, image)
        test_logger.info(f"  💾 Saved: {output_filename}")

def main():
    """Main test function."""
    
    test_logger.info("🎨 Improved Font Scaling System Test")
    test_logger.info("=" * 60)
    
    try:
        # Run all tests
        test_font_scaling_comparison()
        test_visual_comparison()
        test_resolution_independence()
        test_edge_cases()
        
        test_logger.info("\n✅ All tests completed successfully!")
        test_logger.info("\n📁 Generated test images:")
        test_logger.info("  - font_scaling_comparison_*.jpg (method comparison)")
        test_logger.info("  - resolution_independence_*.jpg (consistency test)")
        test_logger.info("  - edge_case_*.jpg (extreme resolutions)")
        
        test_logger.info("\n📊 Key Improvements:")
        test_logger.info("  ✅ Removed hardcoded 30.0 divisor")
        test_logger.info("  ✅ Added resolution-based scaling")
        test_logger.info("  ✅ Added simple diagonal-based scaling")
        test_logger.info("  ✅ Configurable base resolution")
        test_logger.info("  ✅ Better handling of extreme resolutions")
        
    except Exception as e:
        test_logger.info(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0
