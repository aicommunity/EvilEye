"""EventImageWriter delegates to db_controller or ImageStorageService."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from evileye.database_controller.event_image_writer import EventImageWriter


class _Img:
    def __init__(self, arr):
        self.image = arr


@pytest.mark.unit
def test_event_image_writer_prefers_db_controller():
    db = MagicMock()
    writer = EventImageWriter("/tmp/img", 100, 80, db_controller=db)
    img = _Img(np.zeros((10, 10, 3), dtype=np.uint8))
    writer.save("p.jpg", "f.jpg", img, box=[0.1, 0.2, 0.3, 0.4])
    db._save_image.assert_called_once()


@pytest.mark.unit
def test_event_image_writer_falls_back_to_storage():
    db = MagicMock()
    db._save_image.side_effect = RuntimeError("db down")
    writer = EventImageWriter("/tmp/img", 100, 80, db_controller=db)
    img = _Img(np.zeros((10, 10, 3), dtype=np.uint8))
    with patch.object(writer._storage, "save_image", return_value=(True, True)) as save:
        writer.save("p.jpg", "f.jpg", img)
    save.assert_called_once()
