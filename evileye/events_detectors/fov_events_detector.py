import datetime
import time
from threading import Event
from .event_fov import FieldOfViewEvent
from .events_detector import EventsDetector
from datetime import datetime


class FieldOfViewEventsDetector(EventsDetector):
    def __init__(self, objects_handler):
        super().__init__()
        self.sources = set()
        self.sources_list = dict()
        self.sources_periods = dict()  # Айди источника: периоды времени
        self.periods = None
        self.obj_handler = objects_handler
        self.event = Event()

        self.active_obj_ids = dict()  # Словарь для хранения айди активных объектов
        self.lost_obj_ids = dict()

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
            # objects, lost_objects = self.queue_in.get()
            # if objects is None or lost_objects is None:
            #     continue
            for source_id, source_objects in objects:  # Проходим по объектам от каждого источника в отдельности
                if source_id not in self.sources:
                    continue
                if not source_objects.objects:
                    continue

                for obj in source_objects.objects:  # Для каждого объекта
                    if obj.object_id not in self.active_obj_ids[source_id]:  # Если объект ранее не появлялся в зоне
                        idx = self._check_event_in_history(source_id, obj)
                        if idx == -1:
                            continue
                        hist_obj = obj.history[idx]
                        timestamp = datetime.now()
                        self.active_obj_ids[source_id].add(obj.object_id)
                        event = FieldOfViewEvent(timestamp, 'Alarm', hist_obj)
                        # print(f'New event: {obj.last_image.frame_id}, Event: {event}')
                        events.append(event)

            for source_id, source_objects in lost_objects:  # Определяем завершившиеся события
                lost_obj_ids = set()
                if source_id not in self.sources:
                    continue
                if not source_objects.objects:
                    continue
                for obj in source_objects.objects:  # Для каждого объекта
                    if obj.object_id in self.active_obj_ids[source_id]:  # Если объект был активен в запрещенный период
                        timestamp = datetime.now()
                        self.active_obj_ids[source_id].remove(obj.object_id)
                        lost_obj_ids.add(obj.object_id)
                        event = FieldOfViewEvent(timestamp, 'Alarm', obj, is_finished=True)
                        # print(f'Finished event: {obj.last_image.frame_id}, Event: {event}')
                        events.append(event)
                    else:  # Проверяем по истории потерянных объектов, если потеряли объект, до того как он был
                        # обработан детектором
                        if obj.object_id in self.lost_obj_ids[source_id]:
                            lost_obj_ids.add(obj.object_id)
                            continue
                        idx = self._check_event_in_history(source_id, obj)
                        if idx == -1:
                            continue
                        hist_obj = obj.history[idx]
                        timestamp = datetime.now()
                        # Сразу же создаем завершенное событие, так как данный объект уже потерян
                        event = FieldOfViewEvent(timestamp, 'Alarm', obj, is_finished=True)
                        events.append(event)
                        lost_obj_ids.add(obj.object_id)
                self.lost_obj_ids[source_id] = lost_obj_ids
            if events:
                self.queue_out.put(events)
            self.event.clear()

    def _check_event_in_history(self, src_id, obj) -> int:
        time_periods = self.sources_periods[src_id]
        history = obj.history
        end = len(history) - 1
        beg = 0
        idx = None
        for i in range(len(time_periods)):  # Проходим по периодам, в которые запрещено появляться
            start_time = time_periods[i][0]
            end_time = time_periods[i][1]
            while beg <= end:
                mid = (beg + end) // 2
                history_obj = history[mid]
                if start_time <= history_obj.time_stamp.time() <= end_time:
                    idx = mid
                    end = mid - 1
                else:
                    if history_obj.time_stamp.time() > end_time:
                        end = mid - 1
                    elif history_obj.time_stamp.time() < start_time:
                        beg = mid + 1
            if idx is not None:
                return idx
        if idx is None:
            return -1

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
        self.active_obj_ids = {source: set() for source in self.sources}
        self.lost_obj_ids = {source: set() for source in self.sources}

        sources_periods = {int(key): value for key, value in self.sources_list.items()}
        for source in sources_periods:  # Перевод периодов времени из строк к типу datetime
            periods = []
            for period in sources_periods[source]:
                start_time = datetime.strptime(period[0], '%H:%M:%S').time()
                end_time = datetime.strptime(period[1], '%H:%M:%S').time()
                periods.append((start_time, end_time))
            self.sources_periods[source] = periods

    def get_params_impl(self):
        params = dict()
        params['sources'] = self.sources_list
        return params

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
        self.event.set()
        self.queue_in.put((None, None))
        if self.processing_thread.is_alive():
            self.processing_thread.join()
