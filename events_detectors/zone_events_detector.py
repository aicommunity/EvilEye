import datetime
import time
from threading import Lock
from events_detectors.event_fov import FieldOfViewEvent
from events_detectors.events_detector import EventsDetector
from datetime import datetime
from events_detectors.zone import Zone, ZoneForm
from utils import threading_events
from queue import Queue
from events_detectors.event_zone import ZoneEvent
import math


class ZoneEventsDetector(EventsDetector):
    def __init__(self, objects_handler):
        super().__init__()
        self.sources = set()
        self.sources_zones = {}  # Айди источника: список зон
        self.zone_id_people = {}
        self.zones = None
        self.new_zones = Queue()
        self.deleted_zones = Queue()
        self.obj_handler = objects_handler
        self.zone_counter = 0

        self.obj_ids_zone = dict()  # Словарь для хранения айди активных объектов
        threading_events.subscribe('new zone', self.add_zone)
        threading_events.subscribe('zone deleted', self.delete_zone)
        self.mutex = Lock()

    def add_zone(self, source_id, zone_coords, zone_form):
        zone = Zone(source_id, zone_coords, zone_form, is_active=True)
        self.new_zones.put(zone)

    def delete_zone(self, source_id, zone_coords):
        zone = Zone(source_id, zone_coords, is_active=True)
        self.deleted_zones.put(zone)

    def process(self):
        while self.run_flag:
            time.sleep(0.01)
            events = []
            objects, lost_objects = self.queue_in.get()
            if objects is None or lost_objects is None:
                continue

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
                        box = obj.track.bounding_box  # Определяем присутствие в зоне по средней точке нижней границы рамки
                        box_bottom_mid = ((box[0] + box[2]) / 2, box[3])
                        if obj.object_id not in self.obj_ids_zone:  # Если объект ранее не появлялся в зонах
                            if self._is_obj_in_zone(box_bottom_mid, cur_zone, img_width, img_height):
                                self.obj_ids_zone[obj.object_id] = cur_zone
                                event = ZoneEvent(timestamp, 'Alarm', obj, cur_zone)
                                self.zone_id_people[cur_zone.get_zone_id()] += 1
                                print(f'New event: {obj.last_image.frame_id}, Event: {event}')
                                events.append(event)
                        elif cur_zone == self.obj_ids_zone[obj.object_id]:
                            # Иначе проверяем, остался ли объект в зоне, завершаем события
                            zone = self.obj_ids_zone[obj.object_id]
                            if not self._is_obj_in_zone(box_bottom_mid, zone, img_width, img_height):
                                zone = self.obj_ids_zone[obj.object_id]
                                event = ZoneEvent(timestamp, 'Alarm', obj, zone, is_finished=True)
                                self.zone_id_people[cur_zone.get_zone_id()] -= 1
                                del self.obj_ids_zone[obj.object_id]
                                print(f'Finished event: {obj.last_image.frame_id}, Event: {event}')
                                events.append(event)

            for source_id, source_objects in lost_objects:  # Определяем завершившиеся события среди потерянных объектов
                if source_id not in self.sources or not source_objects.objects:
                    continue
                for obj in source_objects.objects:
                    if obj.object_id in self.obj_ids_zone:  # Если объект был в запрещенной зоне
                        timestamp = datetime.now()
                        zone = self.obj_ids_zone[obj.object_id]
                        event = ZoneEvent(timestamp, 'Alarm', obj, zone, is_finished=True)
                        self.zone_id_people[zone.get_zone_id()] -= 1
                        del self.obj_ids_zone[obj.object_id]
                        print(f'Finished event: {obj.last_image.frame_id}, Event: {event}')
                        events.append(event)
            if events:
                self.queue_out.put(events)

    def _is_obj_in_zone(self, box_bottom_mid, zone, img_width, img_height):
        zone_coords_norm = zone.get_coords()
        zone_coords = [(point[0] * img_width, point[1] * img_height) for point in zone_coords_norm]
        if zone.get_zone_form() == ZoneForm.Rectangle:
            if (zone_coords[0][0] <= box_bottom_mid[0] <= zone_coords[1][0] and
                    zone_coords[2][1] <= box_bottom_mid[1] <= zone_coords[2][1]):
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
            self.sources_zones[src_id].append(zone)

        while not self.deleted_zones.empty():
            zone = self.deleted_zones.get()
            src_id = zone.get_src_id()
            idx = self.sources_zones[src_id].index(zone)
            self.zone_id_people[self.sources_zones[src_id][idx].get_zone_id()] = 0
            del self.sources_zones[src_id][idx]

    def update(self):
        active_objs = []
        lost_objs = []
        for source_id in self.sources:
            active_objs.append((source_id, self.obj_handler.get('active', source_id)))
            lost_objs.append((source_id, self.obj_handler.get('lost', source_id)))
        self.queue_in.put((active_objs, lost_objs))

    def set_params_impl(self):
        self.sources = {int(key) for key in self.params['sources'].keys()}

        sources_zones = {int(key): value for key, value in self.params['sources'].items()}
        for source in sources_zones:  # Добавление зон из конфига
            zones = []
            for zone_coords in sources_zones[source]:
                zones.append(Zone(source, zone_coords, is_active=True, zone_id=self.zone_counter))
                self.zone_id_people[self.zone_counter] = 0
                self.zone_counter += 1
            self.sources_zones[source] = zones

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def default(self):
        pass

    def init_impl(self):
        pass

    def stop(self):
        self.run_flag = False
        self.queue_in.put((None, None))
        self.processing_thread.join()
