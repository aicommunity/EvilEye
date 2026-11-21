"""Local spool for event items that could not be written to PostgreSQL.

Audit 2026-11 (A5): after the adapter retry budget (~0.3 s) a failed write was
dropped forever. The spool persists the queue item (pickled) under
``<image_dir>/pg_spool/`` and replays it once the connection recovers, so a
PostgreSQL outage degrades to delayed delivery instead of event loss.

Budget: total spool size is capped (default 200 MB); the oldest files are
dropped first. Losing the oldest spooled events under a very long outage is
the explicit trade-off — the newest events survive.
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional

from evileye.core.logger import get_module_logger

_SPOOL_DIR_NAME = "pg_spool"
DEFAULT_MAX_SPOOL_BYTES = 200 * 1024 * 1024
# Bound a single replay burst so one recovery cannot monopolize the writer.
DEFAULT_REPLAY_BURST = 200


class PgSpool:
    def __init__(
        self,
        image_dir: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_SPOOL_BYTES,
        logger=None,
    ):
        self.root = Path(image_dir) / _SPOOL_DIR_NAME
        self.max_bytes = max(0, int(max_bytes))
        self.logger = logger or get_module_logger("db.pg_spool")

    # -- Writing ----------------------------------------------------------

    def append(self, item: Any) -> bool:
        """Persist one adapter queue item; False when the spool refuses it."""
        try:
            payload = pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            self.logger.error("pg_spool: item is not picklable: %s", exc)
            return False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            name = f"{time.time_ns()}.pkl"
            (self.root / name).write_bytes(payload)
        except OSError as exc:
            self.logger.error("pg_spool: failed to append: %s", exc)
            return False
        self._enforce_budget()
        return True

    def _enforce_budget(self) -> None:
        if self.max_bytes <= 0:
            return
        try:
            files = self._files_oldest_first()
            total = sum(f.stat().st_size for f in files)
            for path in files:
                if total <= self.max_bytes:
                    break
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
                self.logger.warning(
                    "pg_spool: budget exceeded, dropped oldest %s", path.name
                )
        except OSError:
            pass

    # -- Reading ----------------------------------------------------------

    def _files_oldest_first(self) -> list[Path]:
        try:
            return sorted(
                (p for p in self.root.glob("*.pkl") if p.is_file()),
                key=lambda p: p.name,
            )
        except OSError:
            return []

    def pending_count(self) -> int:
        return len(self._files_oldest_first())

    def replay(
        self,
        processor: Callable[[Any], None],
        *,
        max_items: int = DEFAULT_REPLAY_BURST,
    ) -> int:
        """Re-feed spooled items oldest-first; stops at the first failure.

        Returns the number of successfully replayed items. Items that cannot be
        unpickled are dropped (corrupt spool entries must not wedge replay).
        """
        replayed = 0
        for path in self._files_oldest_first():
            if replayed >= max_items:
                break
            try:
                item = pickle.loads(path.read_bytes())
            except Exception:
                self.logger.error("pg_spool: dropping corrupt entry %s", path.name)
                path.unlink(missing_ok=True)
                continue
            try:
                processor(item)
            except Exception:
                # Database still unhealthy: keep the file, retry later.
                break
            path.unlink(missing_ok=True)
            replayed += 1
        return replayed
