import datetime
import time
from threading import Lock, Event
from .event_fov import FieldOfViewEvent
from .events_detector import EventsDetector
from datetime import datetime
from .zone import Zone, ZoneForm
from ..utils import threading_events
from queue import Queue
from .event_zone import ZoneEvent
import math


class ZoneEventsDetector(EventsDetector):
    def __init__(self, objects_handler):
        super().__init__()
        self.sources = set()
        self.sources_list = dict()
        self.sources_zones = {}  # Айди источника: список зон
        self.zone_id_people = {}
        self.left_frame_id = {}  # Для отслеживания в истории айди кадров, на которых объект вышел из зоны
        self.entered_frame_id = {}  # Для отслеживания в истории айди кадров, на которых объект зашел в зону
        self.zones = None
        self.new_zones = Queue()
        self.deleted_zones = Queue()
        self.obj_handler = objects_handler
        self.zone_counter = 0
        self.event_threshold = 0
        self.zone_left_threshold = 0

        self.obj_ids_zone = dict()  # Словарь для хранения айди активных объектов
        threading_events.subscribe('new zone', self.add_zone)
        threading_events.subscribe('zone deleted', self.delete_zone)
        self.event = Event()

    def add_zone(self, source_id, zone_coords, zone_form):
        zone = Zone(source_id, zone_coords, zone_form, is_active=True)
        self.new_zones.put(zone)

    def delete_zone(self, source_id, zone_coords):
        zone = Zone(source_id, zone_coords, is_active=True)
        self.deleted_zones.put(zone)

    def process(self):
        while self.run_flag:
            time.sleep(0.01)
            self.event.wait()
            if not self.run_flag:
                break
            events = []
            objects = []
            lost_objects = []
            for source_id in self.sources:
                objects.append((source_id, self.obj_handler.get('active', source_id)))
                lost_objects.append((source_id, self.obj_handler.get('lost', source_id)))

            self._update_zones()

            for source_id, source_objects in objects:  # Проходим по объектам от каждого источника в отдельности
                if source_id not in self.sources or not source_objects.objects:
                    continue

                zones = self.sources_zones[source_id]
                timestamp = datetime.now()
                img_height, img_width, _ = source_objects.objects[0].last_image.image.shape
                for cur_zone in zones:
                    for obj in source_objects.objects:
                        timestamp = datetime.now()
                        # Если объект ранее не появлялся в зоне
                        if (obj.object_id not in self.obj_ids_zone or
                                cur_zone.get_zone_id() not in self.obj_ids_zone[obj.object_id]):
                            # Находим в истории объекта момент попадания в зону
                            zone_id = cur_zone.get_zone_id()
                            idx = self._check_event_in_history(obj, cur_zone, img_width, img_height)
                            if idx == -1:
                                continue
                            hist_obj = obj.history[idx]
                            # Если айди кадра нового попадания в зону меньше айди выхода из этой зоны в первый раз, пропускаем
                            if (hist_obj.object_id in self.left_frame_id[source_id] and
                                    zone_id in self.left_frame_id[source_id][hist_obj.object_id] and
                                    hist_obj.frame_id <= self.left_frame_id[source_id][hist_obj.object_id][zone_id]):
                                continue
                            # Проверяем, находится ли объект в зоне дольше указанного времени
                            if not self._is_threshold_passed(idx, obj, cur_zone, img_width, img_height):
                                continue
                            if obj.object_id not in self.entered_frame_id[source_id]:
                                self.entered_frame_id[source_id][obj.object_id] = {}
                            self.entered_frame_id[source_id][obj.object_id][zone_id] = hist_obj.frame_id
                            if hist_obj.object_id not in self.obj_ids_zone:
                                self.obj_ids_zone[hist_obj.object_id] = {}
                            self.obj_ids_zone[hist_obj.object_id][zone_id] = cur_zone
                            event = ZoneEvent(hist_obj.time_stamp, 'Alarm', hist_obj, cur_zone)
                            self.zone_id_people[zone_id] += 1
                            # print(f'New event: {obj.last_image.frame_id}, Event: {event}')
                            events.append(event)
                        else:
                            # Иначе проверяем, остался ли объект в зоне, завершаем события
                            zone = self.obj_ids_zone[obj.object_id][cur_zone.get_zone_id()]
                            zone_id = zone.get_zone_id()
                            # Находим в истории момент выхода из зоны
                            idx = self._check_finished_event_in_history(obj, zone, img_width, img_height)
                            if idx == -1:
                                continue
                            hist_obj = obj.history[idx]
                            is_returned, return_idx = self._get_zone_return_idx(idx, obj, zone, img_width, img_height)
                            if is_returned:
                                # Если объект вернулся, то изменяем кадр его попадания в зону на более поздний
                                # для облегчения поиска дальнейшего выхода из зоны
                                if return_idx != -1:
                                    self.entered_frame_id[source_id][obj.object_id][zone_id] = obj.history[return_idx].frame_id
                                continue
                            event = ZoneEvent(hist_obj.time_stamp, 'Alarm', hist_obj, zone, is_finished=True)
                            if obj.object_id not in self.left_frame_id[source_id]:
                                self.left_frame_id[source_id][obj.object_id] = {}
                            self.left_frame_id[source_id][obj.object_id][zone_id] = hist_obj.frame_id
                            self.zone_id_people[zone_id] -= 1
                            del self.entered_frame_id[source_id][obj.object_id][zone_id]
                            del self.obj_ids_zone[obj.object_id][zone_id]
                            # print(f'Finished event: {obj.last_image.frame_id}, Event: {event}')
                            events.append(event)

            for source_id, source_objects in lost_objects:  # Определяем завершившиеся события среди потерянных объектов
                if source_id not in self.sources or not source_objects.objects:
                    continue
                for obj in source_objects.objects:
                    if obj.object_id in self.obj_ids_zone:  # Если объект был в запрещенной зоне
                        timestamp = datetime.now()
                        for zone_id in self.obj_ids_zone[obj.object_id]:
                            zone = self.obj_ids_zone[obj.object_id][zone_id]
                            event = ZoneEvent(timestamp, 'Alarm', obj, zone, is_finished=True)
                            self.zone_id_people[zone.get_zone_id()] -= 1
                            # print(f'Finished event: {obj.last_image.frame_id}, Event: {event}')
                            events.append(event)
                        del self.obj_ids_zone[obj.object_id]
                    # После того как объект был потерян
                    if obj.object_id in self.left_frame_id[source_id]:
                        del self.left_frame_id[source_id][obj.object_id]
                    if obj.object_id in self.entered_frame_id[source_id]:
                        del self.entered_frame_id[source_id][obj.object_id]
            if events:
                self.queue_out.put(events)
            self.event.clear()

    def _check_event_in_history(self, obj, zone, img_width, img_height) -> int:
        history = obj.history
        end = len(history) - 1
        beg = 0
        idx = None
        while beg <= end:
            mid = (beg + end) // 2
            history_obj = history[mid]
            # print(history_obj.track.bounding_box)
            box = history_obj.track.bounding_box  # Определяем присутствие в зоне по средней точке нижней границы рамки
            box_bottom_mid = ((box[0] + box[2]) / 2, box[3])
            if self._is_obj_in_zone(box_bottom_mid, zone, img_width, img_height):
                idx = mid
                end = mid - 1
            else:
                beg = mid + 1
        if idx is None:
            return -1
        else:
            return idx

    def _is_threshold_passed(self, beg_idx, obj, zone, img_width, img_height) -> int:
        history = obj.history
        beg_obj = history[beg_idx]
        end = len(history) - 1
        beg = beg_idx
        while beg <= end:
            mid = (beg + end) // 2
            history_obj = history[mid]
            # print(history_obj.track.bounding_box)
            box = history_obj.track.bounding_box  # Определяем присутствие в зоне по средней точке нижней границы рамки
            box_bottom_mid = ((box[0] + box[2]) / 2, box[3])
            if (history_obj.time_stamp - beg_obj.time_stamp).total_seconds() >= self.event_threshold:
                if self._is_obj_in_zone(box_bottom_mid, zone, img_width, img_height):
                    return True
                else:
                    end = mid - 1
            else:
                beg = mid + 1
        return False

    def _check_finished_event_in_history(self, obj, zone, img_width, img_height) -> int:
        history = obj.history
        end = len(history) - 1
        beg = 0
        idx = None
        while beg <= end:
            mid = (beg + end) // 2
            history_obj = history[mid]
            box = history_obj.track.bounding_box  # Определяем присутствие в зоне по средней точке нижней границы рамки
            box_bottom_mid = ((box[0] + box[2]) / 2, box[3])
            if history_obj.frame_id > self.entered_frame_id[obj.source_id][obj.object_id][zone.get_zone_id()]:
                if not self._is_obj_in_zone(box_bottom_mid, zone, img_width, img_height):
                    idx = mid
                    end = mid - 1
                else:
                    beg = mid + 1
            else:
                beg = mid + 1
        if idx is None:
            return -1
        else:
            return idx

    def _get_zone_return_idx(self, beg_idx, obj, zone, img_width, img_height) -> tuple[bool, int]:
        history = obj.history
        beg_obj = history[beg_idx]
        end = len(history) - 1
        beg = beg_idx
        idx = None
        is_returned = True
        while beg <= end:
            mid = (beg + end) // 2
            history_obj = history[mid]
            box = history_obj.track.bounding_box  # Определяем присутствие в зоне по средней точке нижней границы рамки
            box_bottom_mid = ((box[0] + box[2]) / 2, box[3])
            if (history_obj.time_stamp - beg_obj.time_stamp).total_seconds() <= self.zone_left_threshold:
                if self._is_obj_in_zone(box_bottom_mid, zone, img_width, img_height):
                    idx = mid
                    end = mid - 1
                else:
                    beg = mid + 1
            else:
                end = mid - 1
        if idx is None:
            last_hist_obj = history[-1]
            # Если не нашли индекс возвращения в зону, но порог потери еще не превышен
            if (last_hist_obj.time_stamp - beg_obj.time_stamp).total_seconds() <= self.zone_left_threshold:
                return is_returned, -1
            else:
                is_returned = False
                return is_returned, -1
        return is_returned, idx

    def _is_obj_in_zone(self, box_bottom_mid, zone, img_width, img_height):
        zone_coords_norm = zone.get_coords()
        zone_coords = [(point[0] * img_width, point[1] * img_height) for point in zone_coords_norm]
        if zone.get_zone_form() == ZoneForm.Rectangle:
            if (zone_coords[0][0] <= box_bottom_mid[0] <= zone_coords[1][0] and
                    zone_coords[0][1] <= box_bottom_mid[1] <= zone_coords[2][1]):
                return True
        elif zone.get_zone_form() == ZoneForm.Polygon:
            # Ray-casting algorithm для определения принадлежности точки полигону
            # Еще раз добавляем первую точку для формирования ребер полигона
            zone_coords.append((zone_coords_norm[0][0] * img_width, zone_coords_norm[0][1] * img_height))
            x_obj, y_obj = box_bottom_mid[0], box_bottom_mid[1]
            count = 0
            for i in range(len(zone_coords) - 1):
                (x1, y1), (x2, y2) = zone_coords[i], zone_coords[i + 1]  # Получаем ребро
                if (y_obj < y1) != (y_obj < y2) and x_obj < x1 + ((y_obj - y1) / (y2 - y1)) * (x2 - x1):
                    count += 1
            if count % 2 == 1:
                return True
        return False

    def _update_zones(self):
        while not self.new_zones.empty():
            zone = self.new_zones.get()
            src_id = zone.get_src_id()
            zone.set_id(self.zone_counter)
            self.zone_id_people[self.zone_counter] = 0
            self.zone_counter += 1
            if src_id not in self.sources:
                self.sources.add(src_id)
                self.sources_zones[src_id] = []
                self.left_frame_id[src_id] = {}
                self.entered_frame_id[src_id] = {}
            self.sources_zones[src_id].append(zone)

        while not self.deleted_zones.empty():
            zone = self.deleted_zones.get()
            src_id = zone.get_src_id()
            idx = self.sources_zones[src_id].index(zone)
            self.zone_id_people[self.sources_zones[src_id][idx].get_zone_id()] = 0
            del self.sources_zones[src_id][idx]

    def update(self):
        if not self.event.is_set():
            self.event.set()
        # active_objs = []
        # lost_objs = []
        # for source_id in self.sources:
        #     active_objs.append((source_id, self.obj_handler.get('active', source_id)))
        #     lost_objs.append((source_id, self.obj_handler.get('lost', source_id)))
        # self.queue_in.put((active_objs, lost_objs))

    def set_params_impl(self):
        self.sources_list = self.params.get('sources', dict())
        self.sources = {int(key) for key in self.sources_list.keys()}
        self.left_frame_id = {source: {} for source in self.sources}
        self.entered_frame_id = {source: {} for source in self.sources}
        self.event_threshold = self.params.get('event_threshold', self.event_threshold)
        self.zone_left_threshold = self.params.get('zone_left_threshold', self.zone_left_threshold)

        self.sources_zones = {int(key): [] for key in self.sources}

    def get_params_impl(self):
        params = dict()
        params['sources'] = self.sources_list
        params['event_threshold'] = self.event_threshold
        params['zone_left_threshold'] = self.zone_left_threshold
        return params

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def default(self):
        pass

    def init_impl(self):
        sources_zones = {int(key): value for key, value in self.params.get('sources', dict()).items()}
        for src_id in sources_zones:
            for zone_coords in sources_zones[src_id]:
                self.add_zone(src_id, zone_coords, 'poly')

    def stop(self):
        self.run_flag = False
        self.event.set()
        self.queue_in.put((None, None))
        if self.processing_thread.is_alive():
            self.processing_thread.join()
