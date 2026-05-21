"""IPC ownership transfer for shared-memory frames."""

import numpy as np

from evileye.core.frame_transport import SharedFrameTransport


def test_relinquish_then_consume_unlinks_segment():
    producer = SharedFrameTransport()
    consumer = SharedFrameTransport()
    image = np.ones((2, 2, 3), dtype=np.uint8)
    handle = producer.alloc_frame(image, frame_id=1, timestamp=0.0)
    producer.relinquish_frame(handle)
    assert handle.shm_name not in producer._segments

    copy = consumer.consume_frame(handle)
    assert np.array_equal(copy, image)

    # Second unlink must be a no-op.
    consumer.release_frame(handle)
