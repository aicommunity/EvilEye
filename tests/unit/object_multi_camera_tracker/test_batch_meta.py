from evileye.object_multi_camera_tracker.custom_object_tracking import ObjectMultiCameraTracking
from evileye.object_tracker.tracking_results import TrackingResultList


class _Image:
    def __init__(self):
        self.frame_handle = "fh-1"


def test_attach_batch_meta_sets_contract_fields():
    tracker = ObjectMultiCameraTracking()
    info = TrackingResultList()
    info.source_id = 3
    info.frame_id = 10
    image = _Image()
    tracker._attach_batch_meta((info, image), {3: 10}, is_partial=False)
    assert hasattr(info, "batch_meta")
    assert info.batch_meta["payload_version"] == 1
    assert info.batch_meta["source_id"] == 3
    assert info.batch_meta["frame_id"] == 10
    assert info.batch_meta["is_partial"] is False
    assert info.batch_meta_obj.payload_version == 1
    assert info.batch_meta_obj.source_id == 3
    assert getattr(info, "frame_ref", None) == "fh-1"
    assert hasattr(info, "tracking_dto")
    assert info.tracking_dto.source_id == 3
