"""Unified PG/JSON event image persistence for database adapters."""

from __future__ import annotations

from typing import Any, Optional

from .image_storage_service import ImageStorageService


class EventImageWriter:
    """Delegate to db_controller._save_image when available, else ImageStorageService."""

    def __init__(
            self,
            image_dir: str,
            preview_width: int = 150,
            preview_height: int = 100,
            db_controller: Any = None,
            db_params: Optional[dict] = None,
            logger=None,
    ):
        params = db_params or {}
        image_dir = params.get("image_dir", image_dir)
        preview_width = int(params.get("preview_width", preview_width))
        preview_height = int(params.get("preview_height", preview_height))
        self._db_controller = db_controller
        self._storage = ImageStorageService(
            image_dir, preview_width, preview_height, logger=logger
        )
        self.logger = logger or self._storage.logger

    def save(
            self,
            preview_path: str,
            frame_path: str,
            image,
            box: Optional[list] = None,
            zone_coords: Optional[list] = None,
            draw_boxes: bool = True,
    ) -> None:
        if self._db_controller is not None and hasattr(self._db_controller, "_save_image"):
            try:
                self._db_controller._save_image(
                    preview_path,
                    frame_path,
                    image,
                    box,
                    zone_coords=zone_coords,
                )
                return
            except Exception as exc:
                self.logger.warning(
                    "db_controller._save_image failed, using filesystem fallback: %s",
                    exc,
                )
        self._storage.save_image(
            preview_path,
            frame_path,
            image,
            box=box,
            zone_coords=zone_coords,
            draw_boxes=draw_boxes,
        )
