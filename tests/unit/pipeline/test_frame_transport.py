import numpy as np

from evileye.core.frame_transport import SharedFrameTransport


def test_shared_frame_transport_roundtrip():
    transport = SharedFrameTransport()
    image = np.arange(60, dtype=np.uint8).reshape(4, 5, 3)

    handle = transport.alloc_frame(image, frame_id=7, timestamp=123.0)
    view = transport.get_frame_view(handle)

    assert view.shape == image.shape
    assert np.array_equal(view, image)

    transport.release_frame(handle)
