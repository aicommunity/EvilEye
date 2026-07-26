from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2

from evileye.core.logger import get_module_logger


@dataclass
class JpegEncodeSettings:
    quality: int = 85


class JpegEncoderBackend:
    def encode(self, image) -> Optional[bytes]:
        raise NotImplementedError


class OpenCvJpegEncoder(JpegEncoderBackend):
    def __init__(self, settings: JpegEncodeSettings):
        self._settings = settings

    def encode(self, image) -> Optional[bytes]:
        ok, buf = cv2.imencode(
            ".jpg",
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self._settings.quality)],
        )
        if not ok:
            return None
        return buf.tobytes()


class TurboJpegEncoder(JpegEncoderBackend):
    def __init__(self, settings: JpegEncodeSettings):
        self._settings = settings
        self._encoder = self._create_encoder()
        self._compress_fn = getattr(self._encoder, "compress", None)
        self._pixel_format = getattr(self._encoder, "BGR", None)
        self._subsample = getattr(self._encoder, "Y420", None)

    def _create_encoder(self):
        try:
            from turbojpeg import TurboJPEG  # type: ignore

            return TurboJPEG()
        except Exception:
            import turbojpeg  # type: ignore

            if hasattr(turbojpeg, "TurboJPEG"):
                return turbojpeg.TurboJPEG()
            return turbojpeg

    def encode(self, image) -> Optional[bytes]:
        if callable(self._compress_fn) and self._pixel_format is not None and self._subsample is not None:
            return self._compress_fn(
                image,
                quality=int(self._settings.quality),
                subsamp=self._subsample,
                pixelformat=self._pixel_format,
            )
        return self._encoder.encode(image, quality=int(self._settings.quality))


def create_jpeg_encoder(preferred: str = "auto", quality: int = 85) -> JpegEncoderBackend:
    logger = get_module_logger("jpeg_encoder")
    settings = JpegEncodeSettings(quality=max(1, min(100, int(quality or 85))))
    preferred_normalized = str(preferred or "auto").strip().lower()

    if preferred_normalized in {"auto", "turbojpeg"}:
        try:
            encoder = TurboJpegEncoder(settings)
            logger.info("Using TurboJPEG preview encoder backend")
            return encoder
        except Exception as e:
            if preferred_normalized == "turbojpeg":
                logger.warning("TurboJPEG requested but unavailable: %s. Falling back to OpenCV.", e)
            else:
                logger.debug("TurboJPEG backend unavailable, falling back to OpenCV: %s", e)

    logger.info("Using OpenCV preview encoder backend")
    return OpenCvJpegEncoder(settings)
