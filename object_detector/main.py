import background_subtraction
import object_detection
import cv2


video = cv2.VideoCapture("4ktraffic.mp4")
back_sub = background_subtraction.BackgroundSubtractorMOG2(500, 16, False)
object_detector = object_detection.YoloV8ObjectDetector('yolov8n.pt')

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
    # cv.imshow("Mask", fgMask)
    cv2.rectangle(frame, (10, 2), (100, 20), (255, 255, 255), -1)
    cv2.putText(frame, str(video.get(cv2.CAP_PROP_POS_FRAMES)), (15, 15),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0))

    dilation = back_sub.apply_morphology(fgMask)
    cv2.imshow('dilation2', dilation)
    all_roi = back_sub.get_roi(frame_copy, dilation)
    # cv.imshow('dilation1', closing2)
    object_detector.detect(frame, all_roi, True, 0.4, False)

    cv2.imshow('Frame', frame)
    if cv2.waitKey(1) == ord('q'):
        break
        # results[0].plot()
        # frame[y0:y + 2 * height, x0:x + 2 * width] = roi
        # cv.destroyWindow("Roi")
        # cv.waitKey(0)
        # cv.rectangle(frame_copy, (x, y), (x + width, y + height), (0, 0, 255), 2)
    # height, width,_ = frame.shape
    # dilation = cv.resize(dilation, (width, height))
    # cv.imshow('dilation2', dilation)
    # edged = cv.Canny(dilation, 30, 200)
    # cv.imshow("Real part", real_part)
    # frame_copy = cv.cvtColor(frame_copy, cv.COLOR_GRAY2BGR)
    # stacked = np.hstack((frame_copy, frame))
    # cv.imshow('Mask', cv.resize(stacked, None, fx=0.65, fy=0.65))
    # cv.imshow('Mask2', real_part2)
    # cv.imshow("dilation", edged)
    # cv.imshow('Mask', result)

video.release()
cv2.destroyAllWindows()
