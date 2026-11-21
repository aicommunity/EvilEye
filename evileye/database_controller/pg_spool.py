"""Local spool for event items that could not be written to PostgreSQL.

Audit 2026-11 (A5): after the adapter retry budget a failed write used to be
dropped. The spool persists a JSON record under ``<image_dir>/pg_spool/<adapter>/``
and replays it once the connection recovers.

Records are JSON, never pickle. Legacy ``*.pkl`` files are moved to quarantine
and are not loaded. Budget: total spool size is capped (default 200 MB); the
oldest files are dropped first.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from evileye.core.logger import get_module_logger

_SPOOL_DIR_NAME = "pg_spool"
DEFAULT_MAX_SPOOL_BYTES = 200 * 1024 * 1024
DEFAULT_REPLAY_BURST = 200
_STOP_REPLAY = frozenset({"OperationalError", "InterfaceError"})
_QUARANTINE_ERRORS = frozenset(
    {"ValueError", "TypeError", "DataError", "ProgrammingError", "IntegrityError"}
)


class PgSpool:
    def __init__(
        self,
        image_dir: str | Path,
        *,
        namespace: str = "default",
        max_bytes: int = DEFAULT_MAX_SPOOL_BYTES,
        logger=None,
    ):
        safe_namespace = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(namespace or "default")
        ) or "default"
        self.root = Path(image_dir) / _SPOOL_DIR_NAME / safe_namespace
        self.quarantine = Path(image_dir) / _SPOOL_DIR_NAME / "quarantine"
        self.max_bytes = max(0, int(max_bytes))
        self.logger = logger or get_module_logger("db.pg_spool")
        self._lock = threading.Lock()
        self.last_reject: Optional[str] = None

    def append(self, record: dict[str, Any]) -> bool:
        """Persist one JSON record. False when the spool refuses it."""
        self.last_reject = None
        if not isinstance(record, dict):
            self.last_reject = "encode"
            self.logger.error("pg_spool: refused non-dict record")
            return False
        try:
            payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            self.last_reject = "encode"
            self.logger.error("pg_spool: record is not JSON-serializable: %s", exc)
            return False
        if self.max_bytes and len(payload) > self.max_bytes:
            self.last_reject = "budget"
            self.logger.error("pg_spool: record exceeds the spool budget")
            return False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            name = f"{time.time_ns()}-{uuid.uuid4().hex}.json"
            path = self.root / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
        except OSError as exc:
            self.last_reject = "io"
            self.logger.error("pg_spool: failed to append: %s", exc)
            return False
        if not self._enforce_budget(path):
            self.last_reject = "budget"
            return False
        return True

    def _enforce_budget(self, newest: Path) -> bool:
        """Drop oldest files until the directory fits. False if ``newest`` was removed."""
        if self.max_bytes <= 0:
            return True
        try:
            with self._lock:
                files = self._files_oldest_first()
                total = sum(path.stat().st_size for path in files)
                for path in files:
                    if total <= self.max_bytes:
                        break
                    total -= path.stat().st_size
                    path.unlink(missing_ok=True)
                    self.logger.warning("pg_spool: budget exceeded, dropped oldest %s", path.name)
            return newest.exists()
        except OSError:
            return newest.exists()

    def _files_oldest_first(self) -> list[Path]:
        try:
            return sorted(
                (path for path in self.root.glob("*.json") if path.is_file()),
                key=lambda path: path.name,
            )
        except OSError:
            return []

    def _legacy_pickles(self) -> list[Path]:
        try:
            return sorted(path for path in self.root.glob("*.pkl") if path.is_file())
        except OSError:
            return []

    def pending_count(self) -> int:
        return len(self._files_oldest_first()) + len(self._legacy_pickles())

    def _quarantine(self, path: Path) -> None:
        try:
            self.quarantine.mkdir(parents=True, exist_ok=True)
            target = self.quarantine / f"{path.parent.name}-{path.name}"
            path.replace(target)
        except OSError:
            path.unlink(missing_ok=True)
        self.logger.error("pg_spool: quarantined %s", path.name)

    def replay(
        self,
        processor: Callable[[Any], None],
        *,
        max_items: int = DEFAULT_REPLAY_BURST,
    ) -> int:
        """Re-feed spooled records oldest-first.

        Connection errors stop the burst and keep the file. Corrupt JSON, legacy
        pickles, and data errors are quarantined so one bad file cannot block
        the rest.
        """
        replayed = 0
        for path in self._legacy_pickles():
            self._quarantine(path)
        for path in self._files_oldest_first():
            if replayed >= max_items:
                break
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                self._quarantine(path)
                continue
            if not isinstance(record, dict):
                self._quarantine(path)
                continue
            try:
                processor(record)
            except Exception as exc:
                if type(exc).__name__ in _STOP_REPLAY:
                    break
                if type(exc).__name__ in _QUARANTINE_ERRORS:
                    self._quarantine(path)
                    continue
                break
            path.unlink(missing_ok=True)
            replayed += 1
        return replayed
