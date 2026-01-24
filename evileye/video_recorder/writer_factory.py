"""
Video writer factory for codec/container fallback.
"""

from pathlib import Path
from typing import Optional, Tuple, List

import cv2


class VideoWriterFactory:
    @staticmethod
    def get_fourcc_candidates(container: str) -> List[str]:
        c = container.lower()
        if c == "mp4":
            return ["mp4v", "avc1", "H264", "X264"]
        return ["XVID", "MJPG", "mp4v", "H264"]

    @staticmethod
    def create_writer(
        path: str | Path,
        fps: float,
        frame_size: Tuple[int, int],
        container: str,
        fallback_container: Optional[str] = None,
    ) -> Tuple[Optional[cv2.VideoWriter], str, str]:
        if fallback_container is None:
            fallback_container = "mkv"

        containers_to_try = [container]
        if container.lower() != fallback_container.lower():
            containers_to_try.append(fallback_container)

        path_obj = Path(path) if isinstance(path, str) else path

        for cont in containers_to_try:
            for fourcc_code in VideoWriterFactory.get_fourcc_candidates(cont):
                try:
                    test_path = path_obj.with_suffix(f".{cont}") if cont != container else path_obj
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_code)
                    writer = cv2.VideoWriter(str(test_path), fourcc, fps, frame_size)
                    if writer and writer.isOpened():
                        return writer, fourcc_code, cont
                    if writer:
                        writer.release()
                except Exception:
                    continue

        return None, "", ""

