import pathlib
import json
import datetime
import numpy as np
import cv2
from object_tracker.object_tracking_base import TrackingResult
from objects_handler.object_result import ObjectResultHistory
import copy
from pathlib import Path

from sympy.multipledispatch.dispatcher import source

from database_controller import database_controller_pg
from psycopg2 import sql
from capture.video_capture_base import CaptureImage
from object_tracker.object_tracking_botsort import BOTrack


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def boxes_iou(box1, box2):
    area1 = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
    area2 = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)
    if (((box1[0] <= box2[0] and box1[1] <= box2[1]) and (
            box2[2] <= box1[2] and box2[3] <= box1[3])) or  # Находится ли один bbox внутри другого
            ((box2[0] <= box1[0] and box2[1] <= box1[1]) and (box1[2] <= box2[2] and box1[3] <= box2[3]))):
        return 1.0, box1 if area1 > area2 else box2
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])
    if x_right - x_left + 1 <= 0 or y_bottom - y_top + 1 <= 0:  # Если рамки никак не пересекаются
        return -1.0, None
    intersection = (x_right - x_left + 1) * (y_bottom - y_top + 1)
    iou = intersection / float(area1 + area2 - intersection)
    return iou, box1 if area1 > area2 else box2


def non_max_sup(boxes_coords, confidences, class_ids):
    confidences = np.array(confidences, dtype='float64')
    boxes_coords = np.array(boxes_coords, dtype='float64')
    class_ids = np.array(class_ids, dtype='float64')
    sorted_idxs = np.argsort(confidences)
    iou_thresh = 0.5
    keep_idxs = []
    while len(sorted_idxs) > 0:
        last = len(sorted_idxs) - 1
        suppress_idxs = [last]  # Индекс рамки с наибольшей вероятностью
        keep_idxs.append(sorted_idxs[last])
        for i in range(len(sorted_idxs) - 1):
            idx = sorted_idxs[i]
            iou, max_box = boxes_iou(boxes_coords[sorted_idxs[last]], boxes_coords[idx])
            if iou > iou_thresh:  # Если iou превышает порог, то добавляем данную рамку на удаление
                boxes_coords[idx] = copy.deepcopy(max_box)
                suppress_idxs.append(i)
        sorted_idxs = np.delete(sorted_idxs, suppress_idxs)
    boxes_coords = boxes_coords[keep_idxs].tolist()
    class_ids = class_ids[keep_idxs].tolist()
    confidences = confidences[keep_idxs].tolist()
    return boxes_coords, confidences, class_ids


def roi_to_image(roi_box_coords, x0, y0):
    image_box_coords = [x0 + int(roi_box_coords[0]), y0 + int(roi_box_coords[1]),
                        x0 + int(roi_box_coords[2]), y0 + int(roi_box_coords[3])]
    return image_box_coords


def create_roi(capture_image: CaptureImage, coords):
    rois = []
    for count in range(len(coords)):
        roi_image = copy.deepcopy(capture_image)
        roi_image.image = capture_image.image[coords[count][1]:coords[count][1] + coords[count][3],
                          coords[count][0]:coords[count][0] + coords[count][2]]
        # rois_path = pathlib.Path(get_project_root(), 'images', 'rois')
        # if not rois_path.exists():
        #     pathlib.Path.mkdir(rois_path)
        # if det_id == 2:
        #     roi_path = pathlib.Path(rois_path, str(det_id) + str(count) + '.jpg')
        #     cv2.imwrite(roi_path.as_posix(), roi_image.image)
        rois.append([roi_image, [coords[count][0], coords[count][1]]])
    return rois


def merge_roi_boxes(all_roi, bboxes_coords, confidences, class_ids):
    bboxes_merged = []
    conf_merged = []
    ids_merged = []
    merged_idxs = []
    for i in range(len(bboxes_coords)):
        intersected_idxs = []
        if i in merged_idxs:
            continue
        for j in range(i + 1, len(bboxes_coords)):
            # Если рамки пересекаются, но находятся в разных регионах, то добавляем их в список пересекающихся
            if ((len(all_roi) != 0) and is_intersected(bboxes_coords[i], bboxes_coords[j])
                    and not is_same_roi(all_roi, bboxes_coords[i], bboxes_coords[j])):
                intersected_idxs.append(j)
        # Если рамка пересекается больше, чем с одной, то проверяем, с какой она пересекается больше, чтобы их объединить
        if len(intersected_idxs) > 1:
            iou = []
            # Определяем, с какой рамкой iou выше
            for k in range(len(intersected_idxs)):
                iou.append(boxes_iou(bboxes_coords[i], bboxes_coords[intersected_idxs[k]]))
            max_idx = iou.index(max(iou))
            # Объединяем с этой рамкой
            bboxes_coords[i] = [min(bboxes_coords[i][0], bboxes_coords[intersected_idxs[max_idx]][0]),
                                min(bboxes_coords[i][1], bboxes_coords[intersected_idxs[max_idx]][1]),
                                max(bboxes_coords[i][2], bboxes_coords[intersected_idxs[max_idx]][2]),
                                max(bboxes_coords[i][3], bboxes_coords[intersected_idxs[max_idx]][3])]
            confidences[i] = max(confidences[i], confidences[intersected_idxs[max_idx]])
            merged_idxs.append(intersected_idxs[max_idx])
        # Если пересекается только с одной, объединяем
        elif len(intersected_idxs) == 1:
            bboxes_coords[i] = [min(bboxes_coords[i][0], bboxes_coords[intersected_idxs[0]][0]),
                                min(bboxes_coords[i][1], bboxes_coords[intersected_idxs[0]][1]),
                                max(bboxes_coords[i][2], bboxes_coords[intersected_idxs[0]][2]),
                                max(bboxes_coords[i][3], bboxes_coords[intersected_idxs[0]][3])]
            confidences[i] = max(confidences[i], confidences[intersected_idxs[0]])
            merged_idxs.append(intersected_idxs[0])
        bboxes_merged.append(bboxes_coords[i])
        conf_merged.append(confidences[i])
        ids_merged.append(class_ids[i])
    return bboxes_merged, conf_merged, ids_merged


def is_same_roi(all_roi, box1, box2):
    if len(all_roi) == 0:
        return True
    surrounding_rois_box1 = []
    surrounding_rois_box2 = []
    for i, roi in enumerate(all_roi):
        if (((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3]))) and
                ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])))):
            # Если рамки находятся в одном регионе, но хотя бы одна из рамок уже находится в другом, значит
            # регионы вложенные, поэтому возвращаем False и объединяем рамки
            if len(surrounding_rois_box1) > 0 or len(surrounding_rois_box2) > 0:
                return False
            return True
        elif ((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3])) and not
        ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])))):
            # Проверка на вложенность регионов интереса, создаем для каждой рамки список окружающих регионов
            surrounding_rois_box1.append(i)
        elif ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])) and not
        ((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3])))):
            # Проверка на вложенность регионов интереса, создаем для каждой рамки список окружающих регионов
            surrounding_rois_box2.append(i)
    return False


def is_intersected(box1, box2):
    if ((box1[2] >= box2[0]) and (box2[2] >= box1[0])) and ((box1[3] >= box2[1]) and (box2[3] >= box1[1])):
        return True
    else:
        return False


def get_objs_info(bboxes_coords, confidences, class_ids):
    objects = []
    for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
        obj = {"bbox": bbox, "conf": conf, "class": class_id}
        objects.append(obj)
    return objects


def draw_boxes(image, objects, cam_id, model_names):
    for cam_objs in objects:
        if cam_objs['cam_id'] == cam_id:
            for obj in cam_objs['objects']:
                cv2.rectangle(image, (int(obj['bbox'][0]), int(obj['bbox'][1])),
                              (int(obj['bbox'][2]), int(obj['bbox'][3])), (0, 255, 0), thickness=8)
                cv2.putText(image, str(model_names[obj['class']]) + " " + "{:.2f}".format(obj['conf']),
                            (int(obj['bbox'][0]), int(obj['bbox'][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (255, 255, 255), 2)


def draw_preview_boxes(image, width, height, box):
    cv2.rectangle(image, (int(box[0] * width), int(box[1] * height)),
                  (int(box[2] * width), int(box[3] * height)), (0, 255, 0), thickness=1)
    return image


def draw_boxes_from_db(db_controller, table_name, load_folder, save_folder):
    query = sql.SQL(
        'SELECT object_id, confidence, bounding_box, lost_bounding_box, frame_path, lost_frame_path FROM {table};').format(
        table=sql.Identifier(table_name))
    res = db_controller.query(query)
    for obj_id, conf, box, lost_box, image_path, lost_image_path in res:
        lost_load_dir = pathlib.Path(load_folder, 'lost')
        detected_load_dir = pathlib.Path(load_folder, 'detected')

        if not lost_load_dir.exists():
            Path.mkdir(lost_load_dir)
        lost_load_path = pathlib.Path(lost_load_dir, Path(lost_image_path).name)
        if not detected_load_dir.exists():
            Path.mkdir(detected_load_dir)
        detected_load_path = pathlib.Path(detected_load_dir, Path(image_path).name)

        if not save_folder.exists():
            pathlib.Path.mkdir(save_folder)

        lost_save_dir = pathlib.Path(save_folder, 'lost')
        if not lost_save_dir.exists():
            Path.mkdir(lost_save_dir)
        detected_save_dir = pathlib.Path(save_folder, 'detected')
        if not detected_save_dir.exists():
            Path.mkdir(detected_save_dir)
        lost_save_path = pathlib.Path(lost_save_dir, Path(lost_image_path).name)
        detected_save_path = pathlib.Path(detected_save_dir, Path(image_path).name)

        lost_image = cv2.imread(lost_load_path.as_posix())
        cv2.rectangle(lost_image, (int(box[0]), int(box[1])),
                      (int(box[2]), int(box[3])), (0, 255, 0), thickness=8)
        cv2.putText(lost_image, str(obj_id) + " " + "{:.2f}".format(conf),
                    (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (255, 255, 255), 2)

        detected_image = cv2.imread(detected_load_path.as_posix())
        cv2.rectangle(detected_image, (int(box[0]), int(box[1])),
                      (int(box[2]), int(box[3])), (0, 255, 0), thickness=8)
        cv2.putText(detected_image, str(obj_id) + " " + "{:.2f}".format(conf),
                    (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (255, 255, 255), 2)
        lost_saved = cv2.imwrite(lost_save_path.as_posix(), lost_image)
        detected_saved = cv2.imwrite(detected_save_path.as_posix(), detected_image)
        if not lost_saved or not detected_saved:
            print('Error saving image with boxes')


def draw_boxes_tracking(image: CaptureImage, cameras_objs, source_name, source_duration_msecs, font_scale, font_thickness, font_color):
    height, width, channels = image.image.shape
    if source_name is int:
        cv2.putText(image.image, "Source Id: " + str(source_name), (100, height - 100), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, font_color, font_thickness)
    else:
        cv2.putText(image.image, str(source_name), (100, height - 100), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, font_color, font_thickness)

    if image.current_video_position and source_duration_msecs is not None:
        time_position_secs = image.current_video_position / 1000.0
        pos_string = "{:.1f}".format(time_position_secs) + " [" + "{:.1f}".format(source_duration_msecs / 1000.0) + "]"
        cv2.putText(image.image, pos_string, (width - 900, height - 100), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, font_color, font_thickness)

    # Для трекинга отображаем только последние данные об объекте из истории
    # print(cameras_objs)
    for obj in cameras_objs:
        # if obj.frame_id < image.frame_id:
        #     continue

        last_hist_index = len(obj.history) - 1
        last_info = obj.track
        if obj.frame_id != image.frame_id:
            for i in range(len(obj.history) - 1):
                if obj.history[i].frame_id == image.frame_id:
                    last_hist_index = i
                    last_info = obj.history[i].track
                    break

        cv2.rectangle(image.image, (int(last_info.bounding_box[0]), int(last_info.bounding_box[1])),
                      (int(last_info.bounding_box[2]), int(last_info.bounding_box[3])), (0, 255, 0), thickness=font_thickness)
        if obj.global_id is not None:
            cv2.putText(image.image,
                        str(last_info.track_id) + ':' + str(obj.global_id) + ' ' + str([last_info.class_id]) +
                        " " + "{:.2f}".format(last_info.confidence),
                        (int(last_info.bounding_box[0]), int(last_info.bounding_box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, font_color, font_thickness)
        else:
            cv2.putText(image.image, str(last_info.track_id) + ' ' + str([last_info.class_id]) +
                        " " + "{:.2f}".format(last_info.confidence),
                        (int(last_info.bounding_box[0]), int(last_info.bounding_box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, font_color, font_thickness)

        # print(len(obj['obj_info']))
        if len(obj.history) > 1:
            for i in range(0, last_hist_index):
                first_info = obj.history[i].track
                second_info = obj.history[i + 1].track
                first_cm_x = int((first_info.bounding_box[0] + first_info.bounding_box[2]) / 2)
                first_cm_y = int(first_info.bounding_box[3])
                second_cm_x = int((second_info.bounding_box[0] + second_info.bounding_box[2]) / 2)
                second_cm_y = int(second_info.bounding_box[3])
                cv2.line(image.image, (first_cm_x, first_cm_y),
                         (second_cm_x, second_cm_y), (0, 0, 255), thickness=font_thickness)


def draw_debug_info(image: CaptureImage, debug_info: dict):
    if not debug_info:
        return
    if 'detectors' not in debug_info.keys():
        return

    for det_id, det_debug_info in debug_info['detectors'].items():
        if image.source_id in det_debug_info['source_ids']:
            source_id_index = det_debug_info['source_ids'].index(image.source_id)
            rois = det_debug_info['roi']
            if type(rois) is list and source_id_index in range(len(rois)):
                for roi in rois[source_id_index]:
                    cv2.rectangle(image.image, (int(roi[0]), int(roi[1])),
                                  (int(roi[0] + roi[2]), int(roi[1] + roi[3])), (255, 0, 0), thickness=9)


class ObjectResultEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        if isinstance(obj, TrackingResult):
            return obj.__dict__
        if isinstance(obj, ObjectResultHistory):
            return obj.__dict__
        if isinstance(obj, CaptureImage):
            return None
        if isinstance(obj, BOTrack):
            return None

        return super().default(obj)

