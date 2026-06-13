"""Parent process must not construct BOTSORT when execution_mode is process."""

from unittest.mock import MagicMock, patch

from evileye.core.processor_base import EXEC_MODE_PROCESS, EXEC_MODE_THREAD
from evileye.object_tracker.object_tracking_botsort import ObjectTrackingBotsort


def test_botsort_not_created_in_parent_for_process_mode():
    tracker = ObjectTrackingBotsort()
    tracker.params = {"execution_mode": EXEC_MODE_PROCESS, "source_ids": [0]}
    tracker.execution_mode = EXEC_MODE_PROCESS

    with patch(
        "evileye.object_tracker.object_tracking_botsort.BOTSORT",
        MagicMock(),
    ) as mock_botsort:
        with patch.object(
            ObjectTrackingBotsort,
            "_init_process_mode",
            MagicMock(),
        ):
            tracker.init_impl()
    mock_botsort.assert_not_called()
    assert tracker.tracker is None


def test_botsort_created_in_parent_for_thread_mode():
    tracker = ObjectTrackingBotsort()
    tracker.params = {"execution_mode": EXEC_MODE_THREAD, "source_ids": [0]}
    tracker.execution_mode = EXEC_MODE_THREAD
    tracker.botsort_cfg = tracker.botsort_cfg

    with patch(
        "evileye.object_tracker.object_tracking_botsort.BOTSORT",
        MagicMock(return_value=MagicMock()),
    ) as mock_botsort:
        tracker.processing_thread = MagicMock()
        tracker.init_impl()
    mock_botsort.assert_called_once()
    assert tracker.tracker is not None
