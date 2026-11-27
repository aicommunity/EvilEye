"""
Startup migrations for EvilEye PostgreSQL schema.

Goal: keep DDL out of hot paths (adapters / GUI reads).
"""

from __future__ import annotations

from typing import Iterable, Tuple, Optional


def _apply_alter_statements(db_controller, statements: Iterable[str]) -> None:
    for stmt in statements:
        db_controller.query(stmt, None)


def _align_event_id_sequence(db_controller, logger=None) -> None:
    """Advance event_id_seq past MAX(event_id) across the event tables."""
    from psycopg2 import sql

    tables = [
        name for name in (
            "zone_events", "attribute_events", "cam_events",
            "schedule_alarm_events", "alarm_events", "system_events",
        )
        if name in (getattr(db_controller, "tables", None) or {})
    ]
    max_id = 0
    for table in tables:
        query = sql.SQL("SELECT COALESCE(MAX(event_id), 0) FROM {table}").format(
            table=sql.Identifier(table)
        )
        try:
            record = db_controller.query(query, None)
        except Exception:
            continue
        if record and record[0] and record[0][0] is not None:
            try:
                max_id = max(max_id, int(record[0][0]))
            except (TypeError, ValueError):
                continue
    try:
        db_controller.query(
            "SELECT setval('event_id_seq', %s, %s)",
            (max_id, max_id > 0),
        )
    except Exception as exc:
        if logger:
            try:
                logger.warning(f"event_id_seq alignment failed: {exc}")
            except Exception:
                pass


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
        """
        CREATE TABLE IF NOT EXISTS alarm_events (
          event_id integer,
          alarm_id text PRIMARY KEY,
          time_stamp timestamp NOT NULL,
          alarm_type text NOT NULL,
          severity text NOT NULL,
          source_id integer,
          source_name text,
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          project_id integer,
          job_id integer
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_alarm_events_time_stamp ON alarm_events (time_stamp);",
        # TD-AUD-D1: race-free event-id allocation across concurrent
        # instances. The sequence is advanced past the current MAX(event_id)
        # below so existing rows keep their ids.
        "CREATE SEQUENCE IF NOT EXISTS event_id_seq START 1;",
    )

    try:
        _apply_alter_statements(db_controller, stmts)
        _align_event_id_sequence(db_controller, logger)
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
