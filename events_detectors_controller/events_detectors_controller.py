from threading import Thread
from queue import Queue
from events_detectors.cam_events_detector import CamEventsDetector
from events_detectors.perimeter_events_detector import PerimeterEventsDetector
from timeit import default_timer as timer
import time
import copy
from core.base_class import EvilEyeBase


class EventsDetectorsController(EvilEyeBase):
    def __init__(self, events_detectors: list):
        super().__init__()
        self.control_thread = Thread(target=self.run)
        self.queue_in = Queue()
        self.queue_out = Queue()
        self.detectors = events_detectors
        self.run_flag = False

        self.params = None
        self.events_detectors_params = None
        self.events_detectors = {}  # Сопоставляет имена событий с соответствующими им детекторами

        self.is_empty = True
        self.cam_events_detector = None
        self.perimeter_events_detector = None

    def set_params_impl(self):
        pass

    def init_impl(self):
        self.events_detectors = {detector.get_name(): [] for detector in self.detectors}

    def is_running(self):
        return self.run_flag

    def put(self, frames, objects):
        self.queue_in.put((frames, objects))

    def get(self):
        if self.queue_out.empty():
            return {}
        else:
            return self.queue_out.get()

    def run(self):
        while self.run_flag:
            time.sleep(0.01)
            self.is_empty = True  # Для отслеживания, были ли обнаружены события
            begin_it = timer()

            # Получаем от детекторов события
            for detector in self.detectors:
                events = detector.get()
                if events:
                    self.events_detectors[detector.get_name()] = events
                    self.is_empty = False
                else:
                    self.events_detectors[detector.get_name()] = []

            if not self.is_empty:
                self.queue_out.put(copy.deepcopy(self.events_detectors))
            end_it = timer()

    def start(self):
        self.run_flag = True
        self.control_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put((None, None))
        self.control_thread.join()
        print('Everything in controller stopped')

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        self.stop()
        print('Everything in controller released')
