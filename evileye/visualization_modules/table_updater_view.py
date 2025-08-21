from ..utils import threading_events

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QObject, pyqtSignal
    pyqt_version = 5


class TableUpdater(QObject):
    append_object_signal = pyqtSignal()
    update_object_signal = pyqtSignal()
    append_event_signal = pyqtSignal()
    update_event_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        threading_events.subscribe('handler new object', self.update_objects)
        threading_events.subscribe('handler update object', self.update_objects_on_lost)
        threading_events.subscribe('new event', self.update_events)
        threading_events.subscribe('update event', self.update_events_on_lost)

    def update_objects(self):
        self.append_object_signal.emit()

    def update_objects_on_lost(self):
        self.update_object_signal.emit()

    def update_events(self):
        self.append_event_signal.emit()

    def update_events_on_lost(self):
        self.update_event_signal.emit()
