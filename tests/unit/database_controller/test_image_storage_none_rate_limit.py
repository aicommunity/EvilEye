import logging
import time

from evileye.database_controller.image_storage_service import ImageStorageService


def test_save_image_none_is_rate_limited(caplog, tmp_path):
    ImageStorageService._none_warn_ts = 0.0
    svc = ImageStorageService(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert svc.save_image("p.jpg", "f.jpg", None) == (False, False)
        assert svc.save_image("p.jpg", "f.jpg", None) == (False, False)
    warnings = [r for r in caplog.records if "Image is None" in r.getMessage()]
    assert len(warnings) == 1

    ImageStorageService._none_warn_ts = time.time() - 61.0
    with caplog.at_level(logging.WARNING):
        svc.save_image("p.jpg", "f.jpg", None)
    warnings = [r for r in caplog.records if "Image is None" in r.getMessage()]
    assert len(warnings) == 2
