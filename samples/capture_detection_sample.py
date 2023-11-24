# Sample to check whether object detection works properly
"""
To work with image sequences filename argument in OpenCV VideoCapture class should be
"c:/fullpath/name%03d.format". Here "name%03d" shows that
program should expect every file name starting as "name"
and "%03d" indicates that it takes 3 digit entries as "001" and accept 'integer increment'
"""
import background_subtraction_gmm
import object_detection_yolov8
import video_capture_files as video_cap
import cv2


video = video_cap.VideoCaptureFile()
back_sub = background_subtraction_gmm.BackgroundSubtractorMOG2()
object_detector = object_detection_yolov8.YoloV8ObjectDetector('yolov8n.pt')

capture_params = {'filename': 'fullpath', 'apiPreference': cv2.CAP_ANY}
video.init()
video.set_params(**capture_params)

if not video.is_opened():
    print("Error opening video stream or file")

while video.is_opened():
    ret, frame = video.process()
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        break
    frame_copy = frame.copy()
    frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
    # back_sub.init()       # Uncomment to enable detection using ROI
    # fgMask, all_roi = back_sub.process(frame_copy)
    object_detector.init()
    object_detector.set_params(show=True, conf=0.4, save=False)
    bboxes_coords, confidences, class_ids = object_detector.process(frame)

    cv2.imshow('Frame', frame)
    if cv2.waitKey(1) == ord('q'):
        break
video.release()
cv2.destroyAllWindows()
