import numpy as np
import cv2
import time


def boxes_iou(box1, box2):
    if (((box1[0] <= box2[0] and box1[1] <= box2[1]) and (
            box2[2] <= box1[2] and box2[3] <= box1[3])) or  # Находится ли один bbox внутри другого
            ((box2[0] <= box1[0] and box2[1] <= box1[1]) and (box1[2] <= box2[2] and box1[3] <= box2[3]))):
        return 1.0
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])
    if x_right - x_left + 1 <= 0 or y_bottom - y_top + 1 <= 0:  # Если рамки никак не пересекаются
        return -1.0
    area1 = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
    area2 = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)
    intersection = (x_right - x_left + 1) * (y_bottom - y_top + 1)
    iou = intersection / float(area1 + area2 - intersection)
    return iou


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
            iou = boxes_iou(boxes_coords[sorted_idxs[last]], boxes_coords[idx])
            if iou > iou_thresh:  # Если iou превышает порог, то добавляем данную рамку на удаление
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


def create_roi(image, coords):
    rois = []
    for count in range(len(coords)):
        rois.append([image[coords[count][1]:coords[count][1] + coords[count][3],
                     coords[count][0]:coords[count][0] + coords[count][2]], [coords[count][0], coords[count][1]]])
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
    for roi in all_roi:
        if (((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3]))) and
                ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])))):
            return True
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


def draw_boxes_tracking(image, cameras_objs, cam_id, model_names):
    # Для трекинга отображаем только последние данные об объекте из истории
    for cam_objs in cameras_objs:
        if cam_objs['cam_id'] == cam_id:
            for obj in cam_objs['objects']:
                # if obj['obj_info']
                last_info = obj['obj_info'][-1]
                cv2.rectangle(image, (int(last_info['bbox'][0]), int(last_info['bbox'][1])),
                              (int(last_info['bbox'][2]), int(last_info['bbox'][3])), (0, 255, 0), thickness=8)
                cv2.putText(image, str(last_info['track_id']) + ' ' + str(model_names[last_info['class']]) +
                            " " + "{:.2f}".format(last_info['conf']),
                            (int(last_info['bbox'][0]), int(last_info['bbox'][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 0, 255), 2)
