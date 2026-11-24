"""Objects DB adapter must enqueue JPEG snapshots, not live BGR frames."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from evileye.database_controller.db_adapter_objects import DatabaseAdapterObjects
from evileye.events_detectors.event_zone import LazyJpegFrame


def test_snapshot_queued_image_uses_lazy_jpeg():
    pixels = np.zeros((48, 64, 3), dtype=np.uint8)
    frame = SimpleNamespace(image=pixels, width=64, height=48, source_id=0, frame_id=1)
    snap = DatabaseAdapterObjects._snapshot_queued_image(frame)
    assert isinstance(snap, LazyJpegFrame)
    assert snap.image is not None
    assert snap.image.shape == (48, 64, 3)
    # Live frame must remain independent of the queued snapshot.
    assert frame.image is pixels


def test_insert_queues_snapshot_not_live_frame():
    adapter = DatabaseAdapterObjects.__new__(DatabaseAdapterObjects)
    adapter.logger = MagicMock()
    adapter.queue_in = MagicMock()
    adapter._prepare_for_saving = MagicMock(
        return_value=(["object_id"], [42], "preview.jpg", "frame.jpg")
    )
    adapter.table_name = "objects"

    live = SimpleNamespace(
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        width=32,
        height=32,
        source_id=0,
        frame_id=7,
    )
    obj = SimpleNamespace(last_image=live, object_id=42)

    adapter._insert_impl(obj)
    assert adapter.queue_in.put.called
    queued = adapter.queue_in.put.call_args[0][0][-1]
    assert isinstance(queued, LazyJpegFrame)
    assert queued is not live