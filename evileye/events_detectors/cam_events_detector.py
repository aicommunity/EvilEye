import time
from .event import Event
from threading import Thread
from queue import Queue
from .events_detector import EventsDetector
from .event_cameras import CameraEvent
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
            # По каждому отключению получаем адрес камеры, время и состояние камеры
            for disconnect in discon_iter:
                address, timestamp, is_connected = disconnect
                event = CameraEvent(address, is_connected, timestamp, 'Warning')
                events.append(event)

            for reconnect in recon_iter:
                address, timestamp, is_connected = reconnect
                event = CameraEvent(address, is_connected, timestamp, 'Warning')
                events.append(event)

            if events:
                self.queue_out.put(events)

    def update(self):
        disconnects_iter = iter([])
        reconnects_iter = iter([])
        # Получаем информацию об отключениях и переподключениях от всех источников и отправляем в детектор
        for source in self.sources:
            disconnects_iter = itertools.chain(disconnects_iter, source.get_disconnects_info())
            reconnects_iter = itertools.chain(reconnects_iter, source.get_reconnects_info())

        self.queue_in.put((disconnects_iter, reconnects_iter))

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

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
        if self.processing_thread.is_alive():
            self.processing_thread.join()
