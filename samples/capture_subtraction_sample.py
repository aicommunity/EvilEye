# Sample to check whether video capturing and background subtraction work properly
"""
To work with image sequences filename argument in OpenCV VideoCapture class should be
"c:/fullpath/name%03d.format". Here "name%03d" shows that
program should expect every file name starting as "name"
and "%03d" indicates that it takes 3 digit entries as "001" and accept 'integer increment'
"""
import object_detector.background_subtraction_gmm as background_subtraction_gmm
import capture.video_capture as video_cap
import cv2
import argparse
import json
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

    params_file = open('./capture_subtraction.json')
    data = json.load(params_file)
    subt_params = data['sub_params']
    args = parser.parse_args()
    if args.source is None or args.fullpath is None:
        cap_params = data['cap_params']
        capture_params = {'source': cap_params['source'], 'filename': cap_params['fullpath'],
                          'apiPreference': cap_params['apiPreference'], 'split': cap_params['split'],
                          'num_split': cap_params['num_split'], 'src_coords': cap_params['src_coords']}
    else:
        capture_params = {'source': args.source, 'filename': args.fullpath,
                          'apiPreference': args.apiPreference, 'split': args.split}

    video = video_cap.VideoCapture()
    back_sub = background_subtraction_gmm.BackgroundSubtractorMOG2()
    video.set_params(**capture_params)
    video.init()
    back_sub.set_params(**subt_params)
    back_sub.init()

    if not video.is_opened():
        print("Error opening video stream or file")

    while video.is_opened():
        ret, frames = video.process(split_stream=capture_params['split'],
                                    num_split=capture_params['num_split'], src_coords=capture_params['src_coords'])
        if not ret:
            print("Can't receive frame (stream end?). Exiting ...")
            break
        frame_copy = frames[0].copy()
        frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
        fg_mask, all_roi = back_sub.process(frame_copy)

        (h, w) = frames[0].shape[:2]
        if w > 1280:
            frames[0] = imutils.resize(frames[0], width=1280)
            fg_mask = imutils.resize(fg_mask, width=1280)
        cv2.imshow('Frame', frames[0])
        cv2.imshow('Foreground Mask', fg_mask)
        # for roi in all_roi:  # Uncomment to see ROIs
        #     cv2.imshow('Roi', roi[0])
        #     cv2.waitKey(0)
        if cv2.waitKey(25) == ord('q'):
            break
    video.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
