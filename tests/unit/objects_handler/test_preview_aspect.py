from __future__ import annotations

import numpy as np

from evileye.database_controller.image_storage_service import ImageStorageService


def test_resize_preserving_aspect_keeps_16_9_ratio():
    source = np.zeros((1080, 1920, 3), dtype=np.uint8)
    preview = ImageStorageService.resize_preserving_aspect(source, 300, 150)
    h, w = preview.shape[:2]
    source_aspect = 1920 / 1080
    preview_aspect = w / h
    assert abs(preview_aspect - source_aspect) < 0.02
    assert w <= 300
    assert h <= 150
