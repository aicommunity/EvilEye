from unittest.mock import MagicMock

from evileye.controller.controller import Controller


def test_stop_stops_database_workers_when_connection_is_down():
    controller = Controller.__new__(Controller)
    controller.logger = MagicMock()
    controller.run_flag = True
    controller._stop_control_ipc = MagicMock()
    controller._publish_runtime_snapshot = MagicMock()
    controller._pipeline_service = MagicMock()
    controller.control_thread = None
    controller.obj_handler = None
    controller.visualizer = None
    controller._events_service = None
    controller.events_detectors_controller = None
    controller.events_processor = None
    controller.event_recorders = {}
    controller.event_buffers = {}
    controller._database_service = MagicMock()
    controller._database_service.is_connected.return_value = False
    controller.db_controller = MagicMock()
    controller.storage_monitor = None
    controller.system_diagnostics = None
    controller.memory_monitor = None
    controller._server_process_manager = None
    controller._preview_render_service = None
    controller._streaming_service = None

    controller.stop()

    controller._database_service.stop_adapters.assert_called_once_with()
    controller.db_controller.disconnect.assert_called_once_with()



def test_stop_quiesces_event_controller_before_stopping_detectors():
    calls = []

    class _EventController:
        def stop(self):
            calls.append("controller_stop")

        def flush_once(self):
            calls.append("flush")

        def get(self):
            calls.append("get")
            return {}

    controller = Controller.__new__(Controller)
    controller.logger = MagicMock()
    controller.run_flag = True
    controller._stop_control_ipc = MagicMock()
    controller._publish_runtime_snapshot = MagicMock()
    controller._pipeline_service = MagicMock()
    controller.control_thread = None
    controller.obj_handler = None
    controller.visualizer = None
    controller._events_service = MagicMock()
    controller._events_service.stop_detectors.side_effect = (
        lambda: calls.append("detectors_stop")
    )
    controller.events_detectors_controller = _EventController()
    controller.events_processor = MagicMock()
    controller.event_recorders = {}
    controller.event_buffers = {}
    controller._database_service = MagicMock()
    controller._database_service.is_connected.return_value = False
    controller.db_controller = MagicMock()
    controller.storage_monitor = None
    controller.system_diagnostics = None
    controller.memory_monitor = None
    controller._server_process_manager = None
    controller._preview_render_service = None
    controller._streaming_service = None

    controller.stop()

    assert calls == ["controller_stop", "flush", "get", "detectors_stop"]
