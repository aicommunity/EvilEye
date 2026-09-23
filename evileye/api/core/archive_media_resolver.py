"""Archive media resolution facade (T19 / reaudit architecture).

Thin adapter over ``media_access`` so playback and journals share one
canonical ACL entry point without growing route handlers.
"""

from __future__ import annotations

from pathlib import Path

from evileye.api.core.camera_access import CameraAccess
from evileye.api.core.media_access import (
    ResolvedMedia,
    assert_resolved_media_allowed,
    resolve_authorized_media,
)


class ArchiveMediaResolver:
    """Resolve + authorize Streams/Events media under a data root."""

    def __init__(self, data_root: Path):
        self.data_root = data_root

    def resolve(self, access: CameraAccess, raw_path: str, *, allow_kinds: frozenset[str] | None = None) -> ResolvedMedia:
        return resolve_authorized_media(
            access, raw_path, data_root=self.data_root, allow_kinds=allow_kinds
        )

    def authorize_existing(
        self,
        access: CameraAccess,
        resolved: Path,
        *,
        allow_kinds: frozenset[str] | None = None,
    ) -> ResolvedMedia:
        return assert_resolved_media_allowed(
            access, resolved, data_root=self.data_root, allow_kinds=allow_kinds
        )
