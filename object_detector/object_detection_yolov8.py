from ultralytics import YOLO
from utils import utils
import object_detector
import time
from time import sleep
from object_detector.object_detection_base import DetectionResultList
from object_detector.object_detection_base import DetectionResult
from capture.video_capture_base import CaptureImage


class ObjectDetectorYoloV8(object_detector.ObjectDetectorBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self):
        super().__init__()

        #self.objects = []
        self.model_name = None
        self.model = None
        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = 1  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить
        self.id = ObjectDetectorYoloV8.id_cnt  # ID детектора
        ObjectDetectorYoloV8.id_cnt += 1
        print(self.id)

    def init_impl(self):
        self.model = YOLO(self.model_name)
        return True

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.model_name = self.params['model']
        self.stride = self.params.get('vid_stride', 1)
        self.stride_cnt = self.stride

    def default(self):
        self.model_name = None
        self.model = None
        self.stride = 1
        self.stride_cnt = self.stride
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            try:
                image = self.queue_in.get()
            except ValueError:
                break
            # self.id = image.source_id
            roi_idx = self.params['source_ids'].index(image.source_id)
            if not self.params['roi'][0]:
                roi = [[image, [0, 0]]]
            else:
                roi = utils.create_roi(image, self.params['roi'][roi_idx])
            detection_result_list = self.process_stride(roi)
            if detection_result_list:
                self.queue_out.put(detection_result_list)
            sleep(0.01)

    def process_stride(self, all_roi):
        bboxes_coords = []
        confidences = []
        class_ids = []
        detection_result_list = DetectionResultList()
        inf_params = {"show": self.params['show'], 'conf': self.params['conf'], 'save': self.params['save']}
        curr_time = int(time.time() * 1000)
        if ((self.params.get('stride_type', 'frames') == "time") and (curr_time - self.prev_time >= self.stride)) or ((self.params.get('stride_type', 'frames') == "frames") and (self.stride_cnt == self.stride)):  # Если прошло нужное количество времени, запускаем детекцию
            self.prev_time = curr_time
            self.stride_cnt = 1
            for roi in all_roi:
                results = self.model(source=roi[0].image, **inf_params)
                if len(results[0]) == 0:  # Если детекций не было, пропускаем
                    continue
                roi_bboxes, roi_confs, roi_ids = self.get_bboxes(results[0], roi)  # Получаем координаты рамок на изображении
                confidences.extend(roi_confs)
                class_ids.extend(roi_ids)
                bboxes_coords.extend(roi_bboxes)
            bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)
            bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(self.params['roi'][0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
            frame_objects = utils.get_objs_info(bboxes_coords, confidences, class_ids)
            detection_result_list.source_id = all_roi[0][0].source_id
            detection_result_list.time_stamp = time.time()

            for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
                detection_result = DetectionResult()
                detection_result.bounding_box = bbox
                detection_result.class_id = class_id
                detection_result.confidence = conf
                detection_result_list.detections.append(detection_result)
            return detection_result_list
        else:
            self.stride_cnt += 1

        return None


    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
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
