#!/usr/bin/env python3
"""
Test script to verify that classes parameter works with both IDs and names.
"""


from evileye.object_detector.object_detection_base import ObjectDetectorBase
from evileye.object_detector.object_detection_yolo import ObjectDetectorYolo
from evileye.core.class_manager import ClassManager

def test_classes_with_ids():
    """Test classes parameter with IDs (old behavior)"""
    print("🧪 Testing classes with IDs...")
    
    detector = ObjectDetectorYolo()
    detector.set_params(classes=[0, 1, 2])
    detector.init()
    
    print(f"   Classes after init: {detector.classes}")
    print(f"   Model mapping: {detector.get_model_class_mapping()}")
    
    # Simulate model loading
    if detector.detection_threads:
        detector.get_model_class_mapping()
        print(f"   Classes after model loading: {detector.classes}")
    
    return detector.classes

def test_classes_with_names():
    """Test classes parameter with names (new behavior)"""
    print("🧪 Testing classes with names...")
    
    detector = ObjectDetectorYolo()
    detector.set_params(classes=["person", "bicycle", "car"])
    detector.init()
    
    print(f"   Classes after init: {detector.classes}")
    print(f"   Model mapping: {detector.get_model_class_mapping()}")
    
    # Simulate model loading
    if detector.detection_threads:
        detector.get_model_class_mapping()
        print(f"   Classes after model loading: {detector.classes}")
    
    return detector.classes

def test_class_manager():
    """Test ClassManager functionality"""
    print("🧪 Testing ClassManager...")
    
    class_manager = ClassManager()
    
    # Add some mappings
    mapping = {"person": 0, "bicycle": 1, "car": 2}
    success = class_manager.add_class_mapping(mapping, "TestDetector")
    print(f"   Added mapping: {success}")
    print(f"   Class mapping: {class_manager.get_class_mapping()}")
    
    # Test conversion
    classes_ids = class_manager.convert_classes_to_ids(["person", "car"])
    print(f"   Converted classes: {classes_ids}")
    
    return classes_ids

if __name__ == "__main__":
    print("🚀 Testing classes parameter fix...")
    print("=" * 50)
    
    try:
        # Test 1: Classes with IDs
        result1 = test_classes_with_ids()
        print(f"✅ Test 1 result: {result1}")
        print()
        
        # Test 2: Classes with names
        result2 = test_classes_with_names()
        print(f"✅ Test 2 result: {result2}")
        print()
        
        # Test 3: ClassManager
        result3 = test_class_manager()
        print(f"✅ Test 3 result: {result3}")
        print()
        
        print("🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


