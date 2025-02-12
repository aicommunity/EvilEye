import time
from events_detectors.event import Event
from threading import Thread
from queue import Queue
from events_detectors.events_detector import EventsDetector
from events_detectors.event_cameras import CameraEvent
import itertools


class CamEventsDetector(EventsDetector):
    def __init__(self, sources):
        super().__init__()
        self.sources = sources

    def process(self):
        while self.run_flag:
            time.sleep(0.2)
            events = []
            discon_iter, recon_iter = self.queue_in.get()
            if discon_iter is None or recon_iter is None:
                continue

            for disconnect in discon_iter:
                address, timestamp, is_connected = disconnect
                event1 = CameraEvent(address, 'disconnect', is_connected, timestamp, 'Alarm')
                events.append(event1)

            for reconnect in recon_iter:
                address, timestamp, is_connected = reconnect
                event2 = CameraEvent(address, 'reconnect', is_connected, timestamp, 'Alarm')
                events.append(event2)

            if events:
                self.queue_out.put(events)

    def update(self):
        disconnects_iter = iter([])
        reconnects_iter = iter([])
        for source in self.sources:
            disconnects_iter = itertools.chain(disconnects_iter, source.get_disconnects_info())
            reconnects_iter = itertools.chain(reconnects_iter, source.get_reconnects_info())

        self.queue_in.put((disconnects_iter, reconnects_iter))

    def set_params_impl(self):
        pass

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
