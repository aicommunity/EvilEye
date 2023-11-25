import object_detector.background_subtraction_gmm as background_subtraction_gmm
import object_detector.object_detection_yolov8 as object_detection_yolov8
import cv2

video = cv2.VideoCapture("football.mp4")
back_sub = background_subtraction_gmm.BackgroundSubtractorMOG2()
object_detector = object_detection_yolov8.ObjectDetectorYoloV8('yolov8n.pt')

if not video.isOpened():
    print("Error opening video stream or file")

while video.isOpened():
    ret, frame = video.read()
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        break
    frame_copy = frame.copy()
    frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
    fgMask = back_sub.subtractor.apply(frame_copy)
    cv2.rectangle(frame, (10, 2), (100, 20), (255, 255, 255), -1)
    cv2.putText(frame, str(video.get(cv2.CAP_PROP_POS_FRAMES)), (15, 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0))
    # dilation = back_sub.apply_morphology(fgMask)
    # cv2.imshow("DIl", dilation)
    all_roi = back_sub.get_roi(frame_copy, fgMask)
    object_detector.init()
    object_detector.set_params(show=True, conf=0.4, save=False)
    object_detector.detect(frame, all_roi)

    cv2.imshow('Frame', frame)
    if cv2.waitKey(1) == ord('q'):
        break
video.release()
cv2.destroyAllWindows()
