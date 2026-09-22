import time
from threading import Event, Lock

from evileye.core.event_time import obj_found_datetime, obj_lost_datetime

from .event_schedule_alarm import ScheduleAlarmEvent
from .events_detector import EventsDetector
from .schedule_alarm_logic import (
    DetectorScheduleConfig,
    effective_schedule_for_source,
    find_first_schedule_hit_in_history,
    infer_active_source_ids,
    matches_class,
    parse_detector_params,
    detector_params_to_json,
    schedule_to_json,
    normalize_schedule_dict,
)


class ScheduleAlarmEventsDetector(EventsDetector):
    def __init__(self, objects_handler, pipeline_source_ids=None):
        super().__init__()
        self.obj_handler = objects_handler
        self._pipeline_source_ids = list(pipeline_source_ids or [])
        self.event = Event()
        self._state_lock = Lock()

        self._cfg: DetectorScheduleConfig = DetectorScheduleConfig()
        self._source_ids: set[int] = set()
        self.active_obj_ids: dict[int, set[int]] = {}
        self.lost_obj_ids: dict[int, set[int]] = {}
        self.last_alarm_at: dict[int, float] = {}

    def set_pipeline_source_ids(self, source_ids: list[int]) -> None:
        self._pipeline_source_ids = [int(x) for x in source_ids]
        self.set_params_impl()

    def _reset_runtime_state(self, *, preserve_active: bool = False) -> None:
        if not preserve_active:
            self.active_obj_ids = {sid: set() for sid in self._source_ids}
            self.lost_obj_ids = {sid: set() for sid in self._source_ids}
            self.last_alarm_at = {sid: 0.0 for sid in self._source_ids}
        else:
            for sid in self._source_ids:
                self.active_obj_ids.setdefault(sid, set())
                self.lost_obj_ids.setdefault(sid, set())
                self.last_alarm_at.setdefault(sid, 0.0)

    def _cooldown_allows(self, source_id: int) -> bool:
        cooldown = self._cfg.camera_cooldown_sec
        if cooldown <= 0:
            return True
        last = self.last_alarm_at.get(source_id)
        if last is None or last <= 0:
            return True
        return (time.time() - last) >= cooldown

    def process(self):
        while self.run_flag:
            time.sleep(0.01)
            self.event.wait()
            if not self.run_flag:
                break
            events = []
            with self._state_lock:
                for source_id in sorted(self._source_ids):
                    schedule = effective_schedule_for_source(self._cfg, source_id)
                    if not schedule.enabled:
                        continue

                    active_bucket = self.active_obj_ids.setdefault(source_id, set())
                    lost_bucket = self.lost_obj_ids.setdefault(source_id, set())

                    source_objects = self.obj_handler.get("active", source_id)
                    if source_objects and source_objects.objects:
                        for obj in source_objects.objects:
                            if obj.object_id in active_bucket:
                                continue
                            if not matches_class(obj, schedule.class_ids):
                                continue
                            idx = find_first_schedule_hit_in_history(obj.history, schedule)
                            if idx == -1:
                                continue
                            if not self._cooldown_allows(source_id):
                                continue
                            hist_obj = obj.history[idx]
                            active_bucket.add(obj.object_id)
                            self.last_alarm_at[source_id] = time.time()
                            events.append(
                                ScheduleAlarmEvent(obj_found_datetime(hist_obj), "Alarm", hist_obj)
                            )

                    lost_objects = self.obj_handler.get("lost", source_id)
                    lost_obj_ids = set()
                    if lost_objects and lost_objects.objects:
                        for obj in lost_objects.objects:
                            if obj.object_id in active_bucket:
                                timestamp = obj_lost_datetime(obj)
                                active_bucket.remove(obj.object_id)
                                lost_obj_ids.add(obj.object_id)
                                events.append(
                                    ScheduleAlarmEvent(timestamp, "Alarm", obj, is_finished=True)
                                )
                                continue
                            if obj.object_id in lost_bucket:
                                lost_obj_ids.add(obj.object_id)
                                continue
                            if not matches_class(obj, schedule.class_ids):
                                continue
                            idx = find_first_schedule_hit_in_history(obj.history, schedule)
                            if idx == -1:
                                continue
                            timestamp = obj_lost_datetime(obj)
                            events.append(
                                ScheduleAlarmEvent(timestamp, "Alarm", obj, is_finished=True)
                            )
                            lost_obj_ids.add(obj.object_id)
                    lost_bucket.clear()
                    lost_bucket.update(lost_obj_ids)

            if events:
                self.queue_out.put(events)
            self.event.clear()

    def update(self):
        if not self.event.is_set():
            self.event.set()

    def set_params_impl(self):
        self._cfg = parse_detector_params(self.params)
        self._source_ids = infer_active_source_ids(self._cfg, self._pipeline_source_ids)
        self._reset_runtime_state(preserve_active=False)

    def get_params_impl(self):
        return detector_params_to_json(self._cfg)

    def apply_schedule(self, params: dict) -> None:
        with self._state_lock:
            self.params = dict(params or {})
            self.set_params_impl()
        if not self.event.is_set():
            self.event.set()

    def apply_source_schedule(self, source_id: int, override: dict | None) -> None:
        with self._state_lock:
            sid = int(source_id)
            if override is None:
                self._cfg.sources.pop(sid, None)
            else:
                self._cfg.sources[sid] = normalize_schedule_dict(override, default_enabled=True)
            self.params = detector_params_to_json(self._cfg)
            self.set_params_impl()
        if not self.event.is_set():
            self.event.set()

    def apply_global_params(
        self,
        *,
        camera_cooldown_sec: int | None = None,
        default_schedule: dict | None = None,
    ) -> None:
        with self._state_lock:
            if camera_cooldown_sec is not None:
                self._cfg.camera_cooldown_sec = max(0, int(camera_cooldown_sec))
            if default_schedule is not None:
                self._cfg.default_schedule = normalize_schedule_dict(default_schedule, default_enabled=True)
            self.params = detector_params_to_json(self._cfg)
            self.set_params_impl()
        if not self.event.is_set():
            self.event.set()

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
