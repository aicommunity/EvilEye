import cv2
import numpy as np
import ultralytics
from ultralytics import YOLO
import utils
import object_detector


class ObjectDetectorYoloV8(object_detector.ObjectDetectorBase):
    def __init__(self, model_name):
        super().__init__()
        self.model = YOLO(model_name)

    def init_impl(self):
        return True

    def reset_impl(self):
        pass

    def set_params_impl(self):
        pass

    def default(self):
        self.params.clear()

    def process_impl(self, image, all_roi):
        bboxes_coords = []
        confidences = []
        class_ids = []
        if all_roi is None:
            all_roi = [[image, [0, 0]]]
        for roi in all_roi:
            results = self.model(source=roi[0], **self.params)
            if len(results[0]) == 0:  # Если детекций не было, пропускаем
                continue
            for result in results:
                print(self.is_inited)
                bboxes_coord, confidence, class_id = self.get_bboxes(result, roi)  # Получаем координаты рамок на изображении
                confidences.extend(confidence)
                class_ids.extend(class_id)
                bboxes_coords.extend(bboxes_coord)
        bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)
        self.draw_boxes(image, bboxes_coords, confidences, class_ids)
        return bboxes_coords, confidences, class_ids

    def draw_boxes(self, image, bboxes_coords, confidences, class_ids):
        for coord, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            cv2.rectangle(image, (int(coord[0]), int(coord[1])),
                          (int(coord[2]), int(coord[3])), (0, 255, 0))
            cv2.putText(image, str(self.model.names[class_id]) + " " + "{:.2f}".format(conf),
                        (int(coord[0]), int(coord[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (255, 255, 255), 2)

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if self.model.names[class_id] not in ['car', 'truck', 'bus', 'person']:
                continue
            abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids
