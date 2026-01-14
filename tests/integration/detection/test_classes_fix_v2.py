#!/usr/bin/env python3
"""
Test script to verify that classes parameter fix works correctly.
"""

import time

def test_classes_parameter_fix():
    """Test the classes parameter fix"""
    print("🧪 Testing classes parameter fix...")
    print("=" * 50)
    
    try:
        from evileye.object_detector.object_detection_yolo import ObjectDetectorYolo
        
        # Test 1: Classes with IDs (should work as before)
        print("Test 1: Classes with IDs")
        detector1 = ObjectDetectorYolo()
        detector1.set_params(classes=[0, 1, 2])
        detector1.init()
        
        print(f"   Classes after init: {detector1.classes}")
        print(f"   Model mapping: {detector1.get_model_class_mapping()}")
        print()
        
        # Test 2: Classes with names (should now work)
        print("Test 2: Classes with names")
        detector2 = ObjectDetectorYolo()
        detector2.set_params(classes=["person", "bicycle", "car"])
        detector2.init()
        
        print(f"   Classes after init: {detector2.classes}")
        print(f"   Model mapping: {detector2.get_model_class_mapping()}")
        
        # Wait a bit for model to load
        print("   Waiting for model to load...")
        time.sleep(2)
        
        # Check again
        mapping = detector2.get_model_class_mapping()
        print(f"   Model mapping after wait: {mapping}")
        print(f"   Classes after wait: {detector2.classes}")
        
        # Check if classes were updated
        if detector2.classes and detector2.classes != []:
            print("   ✅ Classes were updated successfully!")
        else:
            print("   ❌ Classes were not updated")
            
        print()
        
        # Test 3: Check thread classes
        print("Test 3: Thread classes")
        if detector2.detection_threads:
            thread_classes = detector2.detection_threads[0].classes
            print(f"   Thread classes: {thread_classes}")
            if thread_classes and thread_classes != []:
                print("   ✅ Thread classes were updated!")
            else:
                print("   ❌ Thread classes were not updated")
        
        print()
        print("🎉 Test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_classes_parameter_fix()


