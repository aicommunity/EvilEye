import numpy as np

from evileye.core.frame_transport import SharedFrameTransport, materialize_payload_list


def test_materialize_payload_list_with_frame_handle():
    transport = SharedFrameTransport()
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    handle = transport.alloc_frame(image, frame_id=0, timestamp=0.0)
    try:
        out = materialize_payload_list([handle], transport)
        assert len(out) == 1
        assert out[0].shape == image.shape
    finally:
        transport.release_frame(handle)
