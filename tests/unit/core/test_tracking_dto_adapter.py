from evileye.core.tracking_dto import ensure_tracking_result_list, TrackingDTO, TrackingObjectDTO


def test_ensure_tracking_result_list_from_dict():
    payload = {
        "source_id": 1,
        "frame_id": 7,
        "tracks": [
            {"track_id": 11, "class_id": 2, "confidence": 0.8, "bbox_xyxy": [1, 2, 3, 4], "global_id": 99},
        ],
    }
    out = ensure_tracking_result_list(payload)
    assert out.source_id == 1
    assert out.frame_id == 7
    assert len(out.tracks) == 1
    assert out.tracks[0].track_id == 11
    assert out.tracks[0].tracking_data.get("global_id") == 99


class _Wrapper:
    def __init__(self):
        self.tracking_dto = TrackingDTO(
            source_id=3,
            frame_id=9,
            tracks=[TrackingObjectDTO(track_id=5, class_id=1, confidence=0.7, bbox_xyxy=[0, 0, 1, 1])],
        )


def test_ensure_tracking_result_list_from_wrapper():
    out = ensure_tracking_result_list(_Wrapper())
    assert out.source_id == 3
    assert out.frame_id == 9
    assert len(out.tracks) == 1
    assert out.tracks[0].track_id == 5
