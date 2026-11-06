"""Replay a saved logical-camera clip through YOLO/BoT-SORT and the actual zone rules."""
import argparse
from collections import deque
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace as S

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-id', type=int, default=2)
    args = parser.parse_args()
    import cv2
    import numpy as np
    from ultralytics import YOLO
    from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
    cfg = json.loads((args.site/'configs/poly-cameras-gst.json').read_text())
    detector_cfg = next(item for item in cfg['pipeline']['detectors'] if args.source_id in item['source_ids'])
    model = YOLO(str(args.site/detector_cfg['model']))
    handler = S(active=S(objects=[]), lost=S(objects=[]))
    handler.get = lambda kind, source: getattr(handler, kind)
    detector = ZoneEventsDetector(handler, listen_for_ui_events=False)
    detector.set_params(**cfg['events_detectors']['ZoneEventsDetector'])
    detector.init()
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    assert fps > 0 and cap.isOpened()
    objects, last_seen = {}, {}
    events, contacts = [], []
    frame_id = 0
    base = datetime.now()
    def record(batch):
        for event in batch:
            events.append(dict(object_id=event.object_id, finished=event.finished,
                               seconds=round((event.timestamp-base).total_seconds(), 3)))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            stamp = base+timedelta(seconds=frame_id/fps)
            result = model.track(frame, persist=True, tracker='botsort.yaml',
                                 classes=detector_cfg['classes'], verbose=False)[0]
            seen = set()
            if result.boxes.id is not None:
                for box, track_id in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.id.cpu().tolist()):
                    track_id = int(track_id)
                    seen.add(track_id)
                    last_seen[track_id] = frame_id
                    hist = S(source_id=args.source_id, object_id=track_id, frame_id=frame_id,
                             time_stamp=stamp, track=S(bounding_box=box))
                    obj = objects.setdefault(track_id, S(source_id=args.source_id, object_id=track_id,
                        history=deque(maxlen=30), last_image=None))
                    obj.history.append(hist)
                    obj.time_stamp, obj.frame_id, obj.track = stamp, frame_id, hist.track
                    obj.last_image = S(image=frame, source_id=args.source_id, frame_id=frame_id, time_stamp=stamp)
            lost = [key for key in objects if frame_id-last_seen[key] > fps*3]
            handler.lost.objects = []
            for key in lost:
                obj = objects.pop(key)
                obj.time_lost = stamp
                handler.lost.objects.append(obj)
            handler.active.objects = list(objects.values())
            record(detector._process_once({args.source_id}))
            if frame_id % max(1, int(fps*5)) == 0:
                annotated = frame.copy()
                h, w = frame.shape[:2]
                for zone in detector.sources_zones.get(args.source_id, []):
                    points = np.array([[x*w,y*h] for x,y in zone.get_coords()], dtype=np.int32)
                    cv2.polylines(annotated, [points], True, (0,0,255), 4)
                for key in seen:
                    box = objects[key].track.bounding_box
                    cv2.rectangle(annotated, (int(box[0]),int(box[1])), (int(box[2]),int(box[3])), (0,255,0), 3)
                    cv2.circle(annotated, (int((box[0]+box[2])/2),int(box[3])), 9, (255,0,0), -1)
                thumb = cv2.resize(annotated, (576,323))
                cv2.putText(thumb, f'{frame_id/fps:.1f}s', (10,25), cv2.FONT_HERSHEY_SIMPLEX, .7, (255,255,255), 2)
                contacts.append(thumb)
            for obj in objects.values():
                obj.last_image = None
            frame_id += 1
        handler.active.objects = []
        handler.lost.objects = list(objects.values())
        for obj in handler.lost.objects:
            obj.time_lost = base+timedelta(seconds=frame_id/fps)
        record(detector._process_once({args.source_id}))
        args.output.mkdir(parents=True, exist_ok=True)
        while len(contacts) % 3:
            contacts.append(np.zeros((323,576,3), dtype=np.uint8))
        if contacts:
            sheet = np.vstack([np.hstack(contacts[i:i+3]) for i in range(0,len(contacts),3)])
            cv2.imwrite(str(args.output/'contacts.jpeg'), sheet)
        summary = dict(frames=frame_id, fps=fps, events=events)
        (args.output/'result.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary))
    finally:
        cap.release()
        detector.release()


if __name__ == '__main__':
    main()
