# Sample to check whether video capturing and background subtraction work properly
"""
To work with image sequences filename argument in OpenCV VideoCapture class should be
"c:/fullpath/name%03d.format". Here "name%03d" shows that
program should expect every file name starting as "name"
and "%03d" indicates that it takes 3 digit entries as "001" and accept 'integer increment'
"""
import background_subtraction_gmm
import video_capture_files as video_cap
import cv2

video = video_cap.VideoCaptureFile()
back_sub = background_subtraction_gmm.BackgroundSubtractorMOG2()

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
    back_sub.init()
    fgMask, all_roi = back_sub.process(frame_copy)

    cv2.imshow('Frame', frame)
    cv2.imshow('Foreground Mask', fgMask)
    # for roi in all_roi:  # Uncomment to see ROIs
    #     cv2.imshow('Roi', roi[0])
    #     cv2.waitKey(0)
    if cv2.waitKey(25) == ord('q'):
        break
video.release()
cv2.destroyAllWindows()
