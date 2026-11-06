from datetime import datetime
from types import SimpleNamespace as S

from evileye.database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents


def test_display_name_is_resolved_to_existing_camera_information_key():
    address = 'rtsp://camera/live'
    db = S(get_params=lambda: {}, get_cameras_params=lambda: [
        {'camera': address, 'source_names': ['Cam2', 'Cam3']}],
        get_project_id=lambda: 1, get_job_id=lambda: 2)
    adapter = DatabaseAdapterCamEvents(db)
    event = S(camera_address='Cam2, Cam3', timestamp=datetime.now(), event_id=3, con_status=False)
    fields, values = adapter._prepare_for_saving(event)
    assert dict(zip(fields, values))['camera_full_address'] == address
    assert event.camera_address == 'Cam2, Cam3'
