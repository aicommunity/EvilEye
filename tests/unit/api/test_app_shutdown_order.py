from unittest.mock import MagicMock, patch

from evileye.api import app as app_module


def test_runtime_producers_stop_before_internal_frame_relay():
    shutdown_order = []
    config_manager = MagicMock()
    pipeline_manager = MagicMock()
    config_manager.shutdown.side_effect = lambda: shutdown_order.append("config")
    pipeline_manager.shutdown.side_effect = lambda: shutdown_order.append("pipeline")

    with patch.object(app_module, "get_config_run_manager", return_value=config_manager), \
         patch("evileye.core.runtime_services.get_pipeline_manager", return_value=pipeline_manager), \
         patch("evileye.api.core.internal_unix.stop_internal_unix_server", side_effect=lambda: shutdown_order.append("internal")):
        app_module._shutdown_runtime_components()

    assert shutdown_order == ["config", "pipeline", "internal"]
