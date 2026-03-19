"""Сервис для сохранения изображений."""

from __future__ import annotations

from typing import Optional, Tuple
import os
import cv2
import numpy as np
from ..core.logger import get_module_logger
from ..utils import utils


class ImageStorageService:
    """Сервис для сохранения изображений в файловую систему."""

    def __init__(self, image_dir: str, preview_width: int = 150, preview_height: int = 100, logger=None):
        """Инициализация сервиса сохранения изображений.

        Args:
            image_dir: Базовый каталог для сохранения изображений
            preview_width: Ширина превью в пикселях
            preview_height: Высота превью в пикселях
            logger: Логгер для записи сообщений. Если не указан, создается новый.
        """
        self.image_dir = image_dir
        self.preview_width = preview_width
        self.preview_height = preview_height
        self.preview_size = (preview_width, preview_height)
        self.logger = logger or get_module_logger("image_storage_service")

    def save_image(
        self,
        preview_path: str,
        frame_path: str,
        image,
        box: Optional[list] = None,
        zone_coords: Optional[list] = None,
        draw_boxes: bool = True,
    ) -> Tuple[bool, bool]:
        """Сохранить превью и полный кадр.

        Args:
            preview_path: Относительный путь для сохранения превью
            frame_path: Относительный путь для сохранения полного кадра
            image: Объект изображения с атрибутом .image (numpy array)
            box: Координаты bounding box [x1, y1, x2, y2] (нормализованные 0-1)
            zone_coords: Координаты зоны для отрисовки (опционально)
            draw_boxes: Рисовать ли bounding box на превью

        Returns:
            Кортеж (preview_saved, frame_saved): True если сохранение успешно
        """
        if image is None:
            self.logger.warning("Image is None in save_image; skipping image save")
            return False, False

        if not hasattr(image, 'image') or image.image is None:
            self.logger.warning("Image object has no image attribute or image.image is None; skipping image save")
            return False, False

        # Разрешаем относительные пути относительно базового каталога
        image_dir_resolved = self.image_dir
        if not os.path.isabs(image_dir_resolved):
            image_dir_resolved = os.path.join(os.getcwd(), image_dir_resolved)

        preview_save_dir = os.path.join(image_dir_resolved, preview_path)
        frame_save_dir = os.path.join(image_dir_resolved, frame_path)

        # Создаем директории если нужно
        os.makedirs(os.path.dirname(preview_save_dir), exist_ok=True)
        os.makedirs(os.path.dirname(frame_save_dir), exist_ok=True)

        # Сохраняем полный кадр (без изменений)
        frame_saved = cv2.imwrite(frame_save_dir, image.image)

        # Создаем и сохраняем превью
        preview = cv2.resize(image.image.copy(), self.preview_size, cv2.INTER_NEAREST)

        if draw_boxes and box is not None:
            # Проверяем тип box
            if not isinstance(box, (list, tuple, np.ndarray)):
                self.logger.warning(f"Invalid box type: {type(box)}, expected list/tuple/array")
                draw_boxes = False

            if draw_boxes and len(box) >= 4:
                if zone_coords is not None:
                    # Для зон используем специальную функцию отрисовки
                    preview = utils.draw_preview_boxes_zones(
                        preview, self.preview_width, self.preview_height, box, zone_coords
                    )
                else:
                    # Обычная отрисовка bounding box
                    preview = utils.draw_preview_boxes(
                        preview, self.preview_width, self.preview_height, box
                    )

        preview_saved = cv2.imwrite(preview_save_dir, preview)

        if not preview_saved or not frame_saved:
            self.logger.error(f"ERROR: can't save image file {frame_save_dir}")

        return preview_saved, frame_saved

    def save_image_simple(
        self,
        preview_path: str,
        frame_path: str,
        image,
    ) -> Tuple[bool, bool]:
        """Сохранить превью и полный кадр без отрисовки bounding box."""
        return self.save_image(preview_path, frame_path, image, draw_boxes=False)
