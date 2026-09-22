"""
Startup migrations for EvilEye PostgreSQL schema.

Goal: keep DDL out of hot paths (adapters / GUI reads).
"""

from __future__ import annotations

from typing import Iterable, Tuple, Optional


def _apply_alter_statements(db_controller, statements: Iterable[str]) -> None:
    for stmt in statements:
        db_controller.query(stmt, None)


def apply_startup_migrations(db_controller, logger: Optional[object] = None) -> None:
    """
    Apply lightweight, idempotent migrations required by recent features.

    This intentionally does not try to be a full migration framework; it only ensures
    presence of columns that are assumed by runtime code.
    """
    if db_controller is None:
        return
    try:
        if hasattr(db_controller, "is_connected") and not db_controller.is_connected():
            return
    except Exception:
        # If controller doesn't support check properly, try anyway.
        pass

    stmts: Tuple[str, ...] = (
        # Rename legacy FOV events table if present
        """
        DO $$
        BEGIN
          IF to_regclass('public.fov_events') IS NOT NULL
             AND to_regclass('public.schedule_alarm_events') IS NULL THEN
            ALTER TABLE fov_events RENAME TO schedule_alarm_events;
          END IF;
        END $$;
        """,
        # zone_events video fragments
        "ALTER TABLE zone_events ADD COLUMN IF NOT EXISTS video_path_entered text;",
        "ALTER TABLE zone_events ADD COLUMN IF NOT EXISTS video_path_left text;",
        # schedule_alarm_events video fragments
        "ALTER TABLE schedule_alarm_events ADD COLUMN IF NOT EXISTS video_path text;",
        "ALTER TABLE schedule_alarm_events ADD COLUMN IF NOT EXISTS video_path_lost text;",
        # legacy fov_events video fragments
        "ALTER TABLE fov_events ADD COLUMN IF NOT EXISTS video_path text;",
        "ALTER TABLE fov_events ADD COLUMN IF NOT EXISTS video_path_lost text;",
        # attribute_events additional payload
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS preview_path_found text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS frame_path_found text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS preview_path_finished text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS frame_path_finished text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS video_path_found text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS video_path_finished text;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS class_id integer;",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS box_found real[];",
        "ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS box_finished real[];",
    )

    try:
        _apply_alter_statements(db_controller, stmts)
        if logger:
            try:
                logger.info("DB startup migrations applied (idempotent)")
            except Exception:
                pass
    except Exception as e:
        if logger:
            try:
                logger.warning(f"DB startup migrations failed: {e}")
            except Exception:
                pass
