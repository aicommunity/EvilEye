import time
from datetime import datetime
from threading import Event as ThreadEvent
from .events_detector import EventsDetector
from .event_attribute import AttributeEvent


class AttributeEventsDetector(EventsDetector):
    def __init__(self, objects_handler):
        super().__init__()
        self.obj_handler = objects_handler
        self.event = ThreadEvent()
        # mapping: source_id -> expected events {event_name: set(attr_names)}
        self.sources_expected: dict[int, dict[str, set[str]]] = {}
        self.sources: set[int] = set()
        # track active events: (source_id, object_id, event_name) -> bool
        self.active_events: set[tuple[int, int, str]] = set()

    def process(self):
        while self.run_flag:
            time.sleep(0.01)
            self.event.wait()
            if not self.run_flag:
                break

            events = []

            # Iterate over configured sources
            for source_id in self.sources:
                active_objects = self.obj_handler.get('active', source_id)
                lost_objects = self.obj_handler.get('lost', source_id)

                # Check active objects for match
                if active_objects and active_objects.objects:
                    for obj in active_objects.objects:
                        if not hasattr(obj, 'attributes') or not obj.attributes:
                            continue
                        current_attrs = {name for name, st in obj.attributes.items() if isinstance(st, dict) and st.get('state') == 'exists'}
                        expected_map = self.sources_expected.get(source_id, {})
                        for event_name, expected_set in expected_map.items():
                            key = (source_id, obj.object_id, event_name)
                            if current_attrs == expected_set and key not in self.active_events:
                                ts = datetime.now()
                                event = AttributeEvent(ts, 'AttributeEvent', source_id, obj.object_id, event_name, sorted(list(expected_set)), is_finished=False, obj=obj)
                                events.append(event)
                                self.active_events.add(key)
                                # Log start of attribute event
                                self.logger.info(f"AttributeEventsDetector: START event='{event_name}' src={source_id} obj={obj.object_id} attrs={sorted(list(expected_set))}")

                # Check lost objects to finish events
                if lost_objects and lost_objects.objects:
                    for obj in lost_objects.objects:
                        expected_map = self.sources_expected.get(source_id, {})
                        for event_name in expected_map.keys():
                            key = (source_id, obj.object_id, event_name)
                            if key in self.active_events:
                                ts = datetime.now()
                                event = AttributeEvent(ts, 'AttributeEvent', source_id, obj.object_id, event_name, sorted(list(expected_map[event_name])), is_finished=True, obj=obj)
                                events.append(event)
                                self.active_events.remove(key)
                                # Log finish of attribute event
                                self.logger.info(f"AttributeEventsDetector: FINISH event='{event_name}' src={source_id} obj={obj.object_id} attrs={sorted(list(expected_map[event_name]))}")

            if events:
                self.queue_out.put(events)
            self.event.clear()

    def update(self):
        if not self.event.is_set():
            self.event.set()

    def set_params_impl(self):
        # params structure example:
        # {
        #   "sources": {
        #       "1": {"no_hard_hat_event": ["no_hard_hat"]},
        #       "2": {"ppe_ok": ["hard_hat"]}
        #   }
        # }
        cfg_sources = self.params.get('sources', {})
        self.sources_expected = {}
        self.sources = set()
        for src_str, events_map in cfg_sources.items():
            try:
                src_id = int(src_str)
            except Exception:
                continue
            self.sources.add(src_id)
            self.sources_expected[src_id] = {evt_name: set(attr_list) for evt_name, attr_list in events_map.items()}

    def get_params_impl(self):
        out = {'sources': {str(src): {evt: sorted(list(attrs)) for evt, attrs in events.items()} for src, events in self.sources_expected.items()}}
        return out

    def init_impl(self):
        pass

    def stop(self):
        self.run_flag = False
        self.event.set()
        self.queue_in.put((None, None))
        if self.processing_thread.is_alive():
            self.processing_thread.join()

    def reset_impl(self):
        # No stateful external resources; clear runtime state
        self.active_events.clear()
        self.event.clear()

    def release_impl(self):
        # Nothing to release explicitly
        pass

    def default(self):
        # Provide empty defaults
        self.sources_expected = {}
        self.sources = set()


