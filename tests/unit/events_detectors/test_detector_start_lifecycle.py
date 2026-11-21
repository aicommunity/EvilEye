import time
from threading import Event as ThreadEvent

from evileye.controller.services.events_service import EventsService
from evileye.events_detectors.events_detector import EventsDetector
from evileye.events_detectors.schedule_alarm_logic import (
    DETECTOR_CONFIG_KEY,
    LEGACY_DETECTOR_CONFIG_KEY,
)


class _StubDetector(EventsDetector):
    def __init__(self):
        super().__init__()
        self._ready = ThreadEvent()
        self.starts = 0

    def process(self):
        self.starts += 1
        self._ready.set()
        while self.run_flag:
            time.sleep(0.01)
            try:
                item = self.queue_in.get(timeout=0.05)
            except Exception:
                continue
            if item is None:
                break

    def update(self):
        pass

    def default(self):
        pass

    def init_impl(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}


def test_events_service_unique_start_for_alias_keys():
    service = EventsService()
    detector = _StubDetector()
    service._detectors[DETECTOR_CONFIG_KEY] = detector
    service._detectors[LEGACY_DETECTOR_CONFIG_KEY] = detector

    service.start_detectors()
    assert detector._ready.wait(timeout=2.0)
    assert detector.starts == 1
    service.stop_detectors()


def test_events_detector_restart_after_stop():
    detector = _StubDetector()
    detector.start()
    assert detector._ready.wait(timeout=2.0)
    detector.stop()

    detector._ready.clear()
    detector.starts = 0
    detector.start()
    assert detector._ready.wait(timeout=2.0)
    assert detector.starts == 1
    detector.stop()
