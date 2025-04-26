# Sample to check whether object detection works properly
"""
To work with image sequences filename argument in OpenCV VideoCapture class should be
"c:/fullpath/name%03d.format". Here "name%03d" shows that
program should expect every file name starting as "name"
and "%03d" indicates that it takes 3 digit entries as "001" and accept 'integer increment'
"""
import object_detector.background_subtraction_gmm as background_subtraction_gmm
import object_detector.object_detection_yolo as object_detection_yolov8
import capture.video_capture as video_cap
import cv2
import argparse
import json
from object_tracker import object_tracking_impl
import imutils


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source',
                        help='The source such as: video file(file), image sequence(sequence) or IP camera(IPcam)',
                        type=str, choices=['file', 'sequence', 'IPcam'], default=None, nargs="?")
    parser.add_argument('fullpath', help='Full path to file or images. Or RTSP for IP camera',
                        type=str, default=None, nargs="?")
    parser.add_argument('apiPreference', help='VideoCapture API backends identifier',
                        type=str, default="CAP_GSTREAMER", nargs='?')
    parser.add_argument('split', help='Split stream flag', type=bool,
                        default=False, nargs='?')

    params_file = open('./capture_detection.json')
    data = json.load(params_file)
    det_params = data['det_params']
    args = parser.parse_args()
    print()
    if args.source is None or args.fullpath is None:
        cap_params = data['cap_params']
        capture_params = {'source': cap_params['source'], 'filename': cap_params['fullpath'],
                          'apiPreference': cap_params['apiPreference'], 'split': cap_params['split'],
                          'num_split': cap_params['num_split'], 'src_coords': cap_params['src_coords']}
    else:
        capture_params = {'source': args.source, 'filename': args.fullpath,
                          'apiPreference': args.apiPreference, 'split': args.split}

    video = video_cap.VideoCapture()
    object_detector = object_detection_yolov8.ObjectDetectorYolo(det_params['model'])
    tracker = object_tracking_impl.ObjectTrackingImpl()
    video.set_params(**capture_params)
    video.init()
    object_detector.set_params(**det_params)
    object_detector.init()
    tracker.init()

    if not video.is_opened():
        print("Error opening video stream or file")

    while video.is_opened():
        ret, frame = video.process()
        if not ret:
            print("Can't receive frame (stream end?). Exiting ...")
            break
        frame_copy = frame.copy()
        frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
        bboxes_coords, confidences, class_ids = object_detector.process(frame)
        tracker.process(frame, bboxes_coords)
        (h, w) = frame.shape[:2]
        if w > 1280:
            frame = imutils.resize(frame, width=1280)
        cv2.imshow('Frame', frame)
        if cv2.waitKey(1) == ord('q'):
            break
    video.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
