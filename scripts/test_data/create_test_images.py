#!/usr/bin/env python3
"""
Create test image sequences for GStreamer testing
"""

import cv2
import numpy as np
import os

def create_test_image_sequence():
    """Create a test sequence of images"""
    
    # Create images directory if it doesn't exist
    os.makedirs('images', exist_ok=True)
    
    # Create 10 test images
    for i in range(1, 11):
        # Create a simple test image with frame number
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Add some color variation
        img[:, :, 0] = (i * 25) % 255  # Red channel
        img[:, :, 1] = (i * 50) % 255  # Green channel  
        img[:, :, 2] = (i * 75) % 255  # Blue channel
        
        # Add frame number text
        cv2.putText(img, f'Frame {i:03d}', (50, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        
        # Add timestamp
        cv2.putText(img, f'Time: {i*0.1:.1f}s', (50, 300),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Save as JPEG
        filename = f'images/sequence_{i:03d}.jpg'
        cv2.imwrite(filename, img)
        print(f'Created {filename}')
    
    print(f'\nCreated {10} test images in images/ directory')
    print('You can now test with: evileye run configs/image_sequence_gstreamer.json')

if __name__ == '__main__':
    create_test_image_sequence()

