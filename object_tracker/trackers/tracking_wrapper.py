import os
import cv2
from typing import List
from ultralytics import YOLO
from ultralytics.engine.results import Results, Boxes
from polytech_reid.trackers.bot_sort import BOTSORT
from polytech_reid.trackers.byte_tracker import BYTETracker

# A mapping of tracker types to corresponding tracker classes
TRACKER_MAP = {"bytetrack": BYTETracker, "botsort": BOTSORT}

class TrackingWrapper:
    def __init__(self, detector: YOLO, tracker: BYTETracker):
    
        self.tracker = tracker
        self.detector = detector

    def run(self, img_paths: List[str]):
        img_paths = sorted(img_paths)

        for i, path in enumerate(img_paths):
            img = cv2.imread(path)
            results = self.detector(img, stream=True)
            for result in results:
                boxes = result.boxes
                tracks = self.update(boxes)
                break
            print(tracks)
            
            # Display the annotated frame
            cv2.imshow("YOLOv8 Tracking", cv2.resize(img, (600, 600)))

            # Break the loop if 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    def update(self, boxes: Boxes):
        det = boxes.cpu().numpy()
        if len(det) == 0:
            return None
        
        tracks = self.tracker.update(det.cls, det.xywh, det.conf, None)
        return tracks

        

