# Sample to check whether video capturing works properly
"""
To work with image sequences filename argument in OpenCV VideoCapture class should be
"c:/fullpath/name%03d.format". Here "name%03d" shows that
program should expect every file name starting as "name"
and "%03d" indicates that it takes 3 digit entries as "001" and accept 'integer increment'
"""
import capture.video_capture as video_cap
from capture import video_capture_base as base
import argparse
import json
import cv2
import imutils


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source',
                        help='The source such as: video file(file), image sequence(sequence) or IP camera(IPcam)',
                        type=str, choices=['file', 'sequence', 'IPcam'], default=None, nargs="?")
    parser.add_argument('fullpath', help='Full path to file or images. Or RTSP for IP camera',
                        type=str, default=None, nargs="?")
    parser.add_argument('apiPreference', help='VideoCapture API backends identifier',
                        type=str, default=0, nargs='?')

    args = parser.parse_args()
    if args.source is None or args.fullpath is None:
        params_file = open('./capture.json')
        data = json.load(params_file)
        cap_params = data['cap_params']
        capture_params = {'source': cap_params['source'], 'filename': cap_params['fullpath'],
                          'apiPreference': cap_params['apiPreference']}
    else:
        capture_params = {'source': args.source, 'filename': args.fullpath,
                          'apiPreference': base.VideoCaptureBase.VideoCaptureAPIs[args.apiPreference]}
    video = video_cap.VideoCapture()
    video.init()
    video.set_params(**capture_params)

    if not video.is_opened():
        print("Error opening video stream or file")

    print('Press R to restart a video or image sequence. (Reset not implemented for IP camera)')

    while video.is_opened():
        roi = [[0, 300, video.capture.get(cv2.CAP_PROP_FRAME_WIDTH), video.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)]]
        ret, frames = video.process(split_stream=True, num_split=2, roi=roi)
        if not ret:
            print("Can't receive frame (stream end?). Exiting ...")
            break
        (h, w) = frames[0].shape[:2]
        if w > 1280:
            for frame in frames:
                frame = imutils.resize(frame, width=1280)
        cv2.imshow('Frame', frames[0])
        cv2.imshow('Frame2', frames[1])
        if cv2.waitKey(1) == ord('r'):
            video.reset()
        # for roi in all_roi:  # Uncomment to see ROIs
        #     cv2.imshow('Roi', roi[0])
        #     cv2.waitKey(0)
        if cv2.waitKey(50) == ord('q'):
            break
    video.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
