# from torch.multiprocessing.queue import Queue
from queue import Queue
import threading
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
        self.models = None
        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = 1  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить
        self.id = ObjectDetectorYoloV8.id_cnt  # ID детектора
        self.roi = [[]]
        ObjectDetectorYoloV8.id_cnt += 1
        print(self.id)

    def init_impl(self):
        self.models = []
        num_models = 1
        if len(self.roi[0]) > 0:
            num_models = len(self.roi[0])
        for i in range(num_models):
            self.models.append(YOLO(self.model_name))

        return True

    def release_impl(self):
        self.models = None

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.model_name = self.params['model']
        self.stride = self.params.get('vid_stride', 1)
        self.stride_cnt = self.stride
        self.source_ids = self.params.get('source_ids', [])
        self.roi = self.params.get('roi', [[]])

    def default(self):
        self.model_name = None
        self.models = None
        self.stride = 1
        self.stride_cnt = self.stride
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            try:
                if not self.queue_in.empty():
                    image = self.queue_in.get()
                else:
                    image = None
            except ValueError:
                break
            if not image:
                continue

            if not self.roi[0]:
                split_image = [[image, [0, 0]]]
            else:
                roi_idx = self.params['source_ids'].index(image.source_id)
                split_image = utils.create_roi(image, self.roi[roi_idx])
            detection_result_list = self.process_stride(split_image)
            if detection_result_list:
                self.queue_out.put(detection_result_list)

    def process_stride(self, split_image):
        bboxes_coords = []
        confidences = []
        class_ids = []
        detection_result_list = DetectionResultList()
        inf_params = {"show": self.params['show'], 'conf': self.params['conf'], 'save': self.params['save']}
        curr_time = int(time.time() * 1000)
        if (((self.params.get('stride_type', 'frames') == "time") and (curr_time - self.prev_time >= self.stride)) or
                ((self.params.get('stride_type', 'frames') == "frames") and (self.stride_cnt == self.stride))):  # Если прошло нужное количество времени, запускаем детекцию
            self.prev_time = curr_time
            self.stride_cnt = 1

            split_predictions_queue = Queue()
            threads = []
            for i in range(len(split_image)):
                threads.append(threading.Thread(target=self._predict, args=(i, self.models[i], split_image[i][0].image, split_predictions_queue, inf_params)))

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

            while not split_predictions_queue.empty():
                index, results = split_predictions_queue.get()
                if len(results[0]) == 0:  # Если детекций не было, пропускаем
                    continue
                roi_bboxes, roi_confs, roi_ids = self.get_bboxes(results[0], split_image[index])  # Получаем координаты рамок на изображении
                confidences.extend(roi_confs)
                class_ids.extend(roi_ids)
                bboxes_coords.extend(roi_bboxes)

            bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)
            bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(self.params['roi'][0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
            # frame_objects = utils.get_objs_info(bboxes_coords, confidences, class_ids)
            detection_result_list.source_id = split_image[0][0].source_id
            detection_result_list.time_stamp = time.time()
            detection_result_list.frame_id = split_image[0][0].frame_id

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
            if self.models[0].names[class_id] not in ['car', 'truck', 'bus', 'person']:
                continue
            abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids

    def _predict(self, i, model, image, result_queue, params):
        result = model.predict(source=image, verbose=False, **params)
        result_queue.put((i, result))
