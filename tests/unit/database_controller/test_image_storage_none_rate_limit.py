import time
from unittest.mock import Mock

from evileye.database_controller.image_storage_service import ImageStorageService


def test_save_image_none_is_rate_limited(tmp_path):
    ImageStorageService._none_warn_ts = 0.0
    logger = Mock()
    svc = ImageStorageService(str(tmp_path), logger=logger)
    assert svc.save_image("p.jpg", "f.jpg", None) == (False, False)
    assert svc.save_image("p.jpg", "f.jpg", None) == (False, False)
    warnings = [call for call in logger.warning.call_args_list if "Image is None" in call.args[0]]
    assert len(warnings) == 1

    ImageStorageService._none_warn_ts = time.time() - 61.0
    svc.save_image("p.jpg", "f.jpg", None)
    warnings = [call for call in logger.warning.call_args_list if "Image is None" in call.args[0]]
    assert len(warnings) == 2
