import time
from threading import Event, RLock
from types import SimpleNamespace
from datetime import datetime
from .events_detector import EventsDetector
from evileye.core.event_time import obj_found_datetime, obj_lost_datetime
from .zone import Zone, ZoneForm
from ..utils import threading_events
from queue import Queue
from .event_zone import ZoneEvent

_DEFAULT_FRAME_SIZE = (1920, 1080)


class ZoneEventsDetector(EventsDetector):
    def __init__(self, objects_handler, *, listen_for_ui_events=True):
        super().__init__()
        self.sources = set()
        self.sources_list = dict()
        self.sources_zones = {}  # Айди источника: список зон
        self.zone_id_people = {}
        self.left_frame_id = {}  # Для отслеживания в истории айди кадров, на которых объект вышел из зоны
        self.entered_frame_id = {}  # Для отслеживания в истории айди кадров, на которых объект зашел в зону
        self._states = {}
        self._pending_events = []
        self._state_lock = RLock()
        self.last_success_at = None
        self.updates_processed = 0
        self.events_created = 0
        self.last_error = None
        self.zones = None
        self.new_zones = Queue()
        self.deleted_zones = Queue()
        self.obj_handler = objects_handler
        self.zone_counter = 0
        self.event_threshold = 0
        self.zone_left_threshold = 0

        self.obj_ids_zone = dict()  # Словарь для хранения айди активных объектов
        self._listen_for_ui_events = bool(listen_for_ui_events)
        if self._listen_for_ui_events:
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
            self.event.wait(timeout=5.0)
            self.event.clear()
            if not self.run_flag:
                break
            try:
                events = self._process_once()
                if events:
                    self.queue_out.put(events)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.logger.exception("Zone processing failed")

    def get_runtime_stats(self):
        return dict(worker_running=self.processing_thread.is_alive(),
                    last_success_at=self.last_success_at,
                    updates_processed=self.updates_processed,
                    events_created=self.events_created,
                    degraded=self.last_error is not None, last_error=self.last_error)

    def _process_once(self, source_ids=None):
        with self._state_lock:
            self._update_zones()
            events = self.drain_pending_events()
            sources = self.sources if source_ids is None else self.sources.intersection(map(int, source_ids))
            for source_id in list(sources):
                present = set()
                for kind in ('active', 'lost'):
                    for obj in list(self.obj_handler.get(kind, source_id).objects):
                        width, height = self._resolve_frame_size([obj])
                        for zone in list(self.sources_zones[source_id]):
                            key = (source_id, obj.object_id, zone.get_zone_id())
                            present.add(key)
                            state = self._states.setdefault(key, dict(
                                cursor=None, entered=None, left=None, active=False,
                                lost=False, obj=None, zone=zone))
                            if state['lost']:
                                continue
                            history = list(getattr(obj, 'history', None) or [])
                            if getattr(obj, 'track', None) is not None:
                                history.append(obj)
                            observations = {}
                            for hist in history:
                                stamp = getattr(hist, 'time_stamp', None)
                                box = getattr(getattr(hist, 'track', None), 'bounding_box', None)
                                if stamp is not None and box is not None:
                                    observations[(stamp, int(getattr(hist, 'frame_id', None) or 0))] = hist
                            for cursor, hist in sorted(observations.items()):
                                if state['cursor'] is not None and cursor <= state['cursor']:
                                    continue
                                state['cursor'] = cursor
                                stamp = cursor[0]
                                box = hist.track.bounding_box
                                inside = self._is_obj_in_zone(((box[0]+box[2])/2, box[3]), zone, width, height)
                                if state['active'] and state['left'] is not None and (
                                    stamp - state['left'].time_stamp
                                ).total_seconds() > self.zone_left_threshold:
                                    events.append(self._finish(state, obj, state['left'].time_stamp))
                                if inside:
                                    state['left'] = None
                                    if state['entered'] is None:
                                        state['entered'] = self._observation(hist, obj)
                                    if not state['active'] and (
                                        stamp - state['entered'].time_stamp
                                    ).total_seconds() >= self.event_threshold:
                                        event_obj = self._observation(state['entered'], obj)
                                        event_obj.last_image = getattr(obj, 'last_image', None)
                                        event = ZoneEvent(state['entered'].time_stamp, 'Alarm', event_obj, zone)
                                        # Do not retain full live frames while an event is open.
                                        event_obj.last_image = None
                                        state['entered'].last_image = None
                                        state['obj'] = event_obj
                                        state['active'] = True
                                        self.obj_ids_zone.setdefault((source_id, obj.object_id), {})[zone.get_zone_id()] = zone
                                        self.zone_id_people[zone.get_zone_id()] += 1
                                        events.append(event)
                                elif state['active']:
                                    if state['left'] is None:
                                        state['left'] = self._observation(hist, obj)
                                        state['left'].last_image = None
                                    if (stamp-state['left'].time_stamp).total_seconds() > self.zone_left_threshold:
                                        events.append(self._finish(state, obj, state['left'].time_stamp))
                                else:
                                    state['entered'] = None
                            if kind == 'lost':
                                if state['active']:
                                    events.append(self._finish(state, obj, obj_lost_datetime(obj)))
                                state.update(lost=True, entered=None, left=None, obj=None)
                for key in list(self._states):
                    if key[0] == source_id and key not in present and not self._states[key]['active']:
                        del self._states[key]
            self.last_success_at = time.time()
            self.updates_processed += 1
            self.events_created += len(events)
            return events

    @staticmethod
    def _observation(hist, obj):
        return SimpleNamespace(
            source_id=obj.source_id, object_id=obj.object_id,
            frame_id=getattr(hist, 'frame_id', None), time_stamp=hist.time_stamp,
            track=SimpleNamespace(bounding_box=list(hist.track.bounding_box)),
            last_image=None, history=[],
            _zone_event_sticky_image=getattr(obj, '_zone_event_sticky_image', None))

    def _finish(self, state, obj, stamp):
        event_obj = self._observation(state['left'] or state['entered'], obj)
        event_obj.last_image = getattr(obj, 'last_image', None)
        event_obj._zone_event_sticky_image = getattr(state['obj'], '_zone_event_sticky_image', None)
        event = ZoneEvent(stamp, 'Alarm', event_obj, state['zone'], is_finished=True)
        zone_id = state['zone'].get_zone_id()
        self.zone_id_people[zone_id] = max(0, self.zone_id_people.get(zone_id, 0)-1)
        key = (obj.source_id, obj.object_id)
        zones = self.obj_ids_zone.get(key, {})
        zones.pop(zone_id, None)
        if not zones:
            self.obj_ids_zone.pop(key, None)
        state.update(active=False, entered=None, left=None, obj=None)
        return event

    def drain_pending_events(self):
        with self._state_lock:
            events, self._pending_events = self._pending_events, []
            return events

    def _remove_zone(self, zone):
        for key, state in list(self._states.items()):
            if key[0] == zone.get_src_id() and key[2] == zone.get_zone_id():
                if state['active']:
                    self._pending_events.append(self._finish(state, state['obj'], datetime.now()))
                del self._states[key]
        self.zone_id_people.pop(zone.get_zone_id(), None)

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

    def _resolve_frame_size(self, objects) -> tuple[int | None, int | None]:
        for obj in objects or []:
            last_img = getattr(obj, "last_image", None)
            img = getattr(last_img, "image", None)
            if img is not None and hasattr(img, "shape") and len(img.shape) >= 2:
                height, width = img.shape[:2]
                if width > 0 and height > 0:
                    return int(width), int(height)
        default_w, default_h = _DEFAULT_FRAME_SIZE
        return default_w, default_h

    @staticmethod
    def _normalize_zone_coords_list(zone_coords_list) -> list:
        normalized = []
        for entry in zone_coords_list or []:
            coords = ZoneEventsDetector._normalize_polygon_coords(entry)
            if coords:
                normalized.append(coords)
        return normalized

    @staticmethod
    def _normalize_polygon_coords(entry):
        if isinstance(entry, dict):
            points = entry.get("points") or entry.get("coords") or entry.get("coordinates")
            if not isinstance(points, list):
                return None
            entry = points
        if not isinstance(entry, (list, tuple)) or not entry:
            return None
        while (
            len(entry) == 1
            and isinstance(entry[0], (list, tuple))
            and entry[0]
            and isinstance(entry[0][0], (list, tuple))
        ):
            entry = entry[0]
        if not entry or not isinstance(entry[0], (list, tuple)) or len(entry[0]) < 2:
            return None
        if not isinstance(entry[0][0], (int, float)):
            return None
        try:
            return [[float(p[0]), float(p[1])] for p in entry]
        except (TypeError, ValueError, IndexError):
            return None

    def replace_zones_for_source(self, source_id: int, zone_coords_list) -> None:
        with self._state_lock:
            self._update_zones()
            src_id = int(source_id)
            normalized = self._normalize_zone_coords_list(zone_coords_list)
            for zone in self.sources_zones.get(src_id, []):
                self._remove_zone(zone)
            self.left_frame_id[src_id] = {}
            self.entered_frame_id[src_id] = {}
            self.sources_zones[src_id] = []
            self.sources.add(src_id)
            self.sources_list[str(src_id)] = normalized
            for coords in normalized:
                self.add_zone(src_id, coords, 'poly')
            self._update_zones()
            self.event.set()

    def apply_thresholds(
        self,
        *,
        event_threshold: int | None = None,
        zone_left_threshold: int | None = None,
    ) -> None:
        if event_threshold is not None:
            self.event_threshold = max(0, int(event_threshold))
        if zone_left_threshold is not None:
            self.zone_left_threshold = max(0, int(zone_left_threshold))

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
            zones = self.sources_zones.get(src_id, [])
            for existing in list(zones):
                if existing == zone:
                    self._remove_zone(existing)
                    zones.remove(existing)
                    break

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
        if self._listen_for_ui_events:
            threading_events.unsubscribe('new zone', self.add_zone)
            threading_events.unsubscribe('zone deleted', self.delete_zone)
            self._listen_for_ui_events = False

    def default(self):
        pass

    def init_impl(self):
        sources_zones = {int(key): value for key, value in self.params.get('sources', dict()).items()}
        for src_id in sources_zones:
            for zone_coords in self._normalize_zone_coords_list(sources_zones[src_id]):
                self.add_zone(src_id, zone_coords, 'poly')

    def stop(self):
        self.run_flag = False
        self.event.set()
        self.queue_in.put((None, None))
        if self.processing_thread.is_alive():
            self.processing_thread.join()
