import time
from datetime import datetime
from .events_detector import EventsDetector
from .event_system import SystemEvent


class SystemEventsDetector(EventsDetector):
    def __init__(self):
        super().__init__()
        self.pending_events = []

    def emit_message(self, type: str, message: str):
        self.pending_events.append(SystemEvent(datetime.now(), type, message))
        # nudge processing thread
        try:
            self.queue_in.put('tick', timeout=0.01)
        except Exception:
            pass

    def emit_started(self):
        # Called by Controller on start
        self.emit_message('SystemStart', '')

    def emit_stopped(self):
        # Called by Controller on stop
        self.emit_message('SystemStop', '')

    def process(self):
        while self.run_flag:
            _ = self.queue_in.get()
            if _ is None:
                break
            if self.pending_events:
                self.queue_out.put(self.pending_events[:])
                self.pending_events.clear()

    def update(self):
        # No periodic updates required
        pass

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

    def init_impl(self):
        pass

    def stop(self):
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()

    def reset_impl(self):
        # Очистка внутреннего буфера событий
        try:
            self.pending_events.clear()
        except Exception:
            pass

    def release_impl(self):
        # Нечего освобождать явно
        pass

    def default(self):
        # Значения по умолчанию отсутствуют
        pass


