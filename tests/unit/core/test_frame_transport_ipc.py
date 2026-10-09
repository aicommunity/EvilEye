"""IPC ownership transfer for shared-memory frames."""

import numpy as np

from evileye.core.frame_transport import SharedFrameTransport


def test_relinquish_then_consume_unlinks_segment():
    producer = SharedFrameTransport()
    consumer = SharedFrameTransport()
    image = np.ones((2, 2, 3), dtype=np.uint8)
    handle = producer.alloc_frame(image, frame_id=1, timestamp=0.0)
    producer.relinquish_frame(handle)
    assert handle.shm_name in producer._segments

    copy = consumer.consume_frame(handle)
    assert np.array_equal(copy, image)

    # Release the producer pin after consumer has opened and unlinked the name.
    producer.release_frame(handle)
    consumer.release_frame(handle)
    assert handle.shm_name not in producer._segments


def test_alloc_relinquish_consume_cycle_releases_all():
    """MEM-2: repeated SHM handoff does not accumulate producer segments."""
    producer = SharedFrameTransport()
    consumer = SharedFrameTransport()
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    for i in range(5):
        handle = producer.alloc_frame(image, frame_id=i, timestamp=float(i))
        producer.relinquish_frame(handle)
        consumer.consume_frame(handle)
        producer.release_frame(handle)
        consumer.release_frame(handle)
    assert len(producer._segments) == 0
    assert len(consumer._segments) == 0


def test_consume_missing_shm_returns_none():
    """H1: missing SHM must not yield an empty ndarray for the pipeline."""
    from evileye.core.frame_transport import FrameHandle

    consumer = SharedFrameTransport()
    handle = FrameHandle(
        frame_id=1,
        shm_name="nonexistent_psm_audit_h1",
        shape=(2, 2, 3),
        dtype="uint8",
        stride=(6, 3, 1),
        timestamp=0.0,
    )
    assert consumer.consume_frame(handle) is None
