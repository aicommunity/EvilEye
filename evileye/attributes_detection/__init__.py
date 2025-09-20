# Attributes Detection Module
# This module contains components for attribute detection and classification

from .roi_feeder import RoiFeeder
from .attribute_classifier import AttributeClassifier
from .attribute_detector import AttributeDetector
from .attribute_detection_thread import AttributeDetectionThread

__all__ = ['RoiFeeder', 'AttributeClassifier', 'AttributeDetector', 'AttributeDetectionThread']
