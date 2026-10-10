from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg2 import sql

from evileye.database_controller.db_adapter_alarm_events import DatabaseAdapterAlarmEvents
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.events_detectors.alarm_event import AlarmEvent


def _load_database_config():
    project_root = Path(__file__).resolve().parents[4]
    candidates = (
        project_root / "evileye" / "database_config.json",
        project_root / "database_config.json",
    )
    config_path = next((path for path in candidates if path.exists()), None)
    if config_path is None:
        pytest.skip("database_config.json is not configured")
    with config_path.open(encoding="utf-8") as stream:
        return json.load(stream)


@pytest.mark.integration
def test_alarm_postgresql_adapter_writes_idempotently_and_cleans_up(tmp_path):
    config = _load_database_config()
    database_params = dict(config["database"])
    database_params.setdefault("user_name", "postgres")
    database_params.setdefault("password", "")
    database_params.setdefault("host_name", "localhost")
    database_params.setdefault("port", 5432)
    database_params.setdefault("admin_user_name", "postgres")
    database_params.setdefault("admin_password", "")
    database_params["image_dir"] = str(tmp_path)

    database = DatabaseControllerPg({"pipeline": {"sources": []}})
    database.set_params(
        user_name=database_params["user_name"],
        password=database_params["password"],
        database_name=database_params.get("database_name", "evil_eye_db"),
        host_name=database_params["host_name"],
        port=database_params["port"],
        admin_user_name=database_params["admin_user_name"],
        admin_password=database_params["admin_password"],
        image_dir=database_params["image_dir"],
        create_new_project=database_params.get("create_new_project", False),
        tables=database_params["tables"],
        preview_width=database_params.get("preview_width", 300),
        preview_height=database_params.get("preview_height", 150),
    )
    adapter = None
    alarm_id = f"integration-{uuid4()}"

    try:
        database.init()
        database.connect()
        if not database.is_connected():
            pytest.skip("Configured PostgreSQL database is unavailable")

        from evileye.database_controller.migrations import apply_startup_migrations

        apply_startup_migrations(database)
        adapter = DatabaseAdapterAlarmEvents(database)
        adapter.set_params(table_name="alarm_events", queue_maxsize=8)
        adapter.init()
        adapter.start()

        alarm = AlarmEvent(
            "integration_test_alarm",
            severity="warning",
            source_id=0,
            details={"test": "alarm persistence"},
            alarm_id=alarm_id,
        )
        alarm.set_id(int(time.time() * 1000) % 2_000_000_000)
        adapter.insert(alarm)
        adapter.insert(alarm)
        adapter.stop()

        records = database.query_checked(
            sql.SQL(
                "SELECT alarm_id, alarm_type, severity, source_id, details "
                "FROM alarm_events WHERE alarm_id = %s"
            ),
            (alarm_id,),
        )
        assert records == [
            (alarm_id, "integration_test_alarm", "warning", 0, {"test": "alarm persistence"})
        ]
        assert adapter.get_runtime_stats()["processed_items"] == 2
        assert adapter.get_runtime_stats()["degraded"] is False
    finally:
        if adapter is not None:
            adapter.stop()
        if database.is_connected():
            database.query_checked(
                sql.SQL("DELETE FROM alarm_events WHERE alarm_id = %s"),
                (alarm_id,),
            )
            remaining = database.query_checked(
                sql.SQL("SELECT alarm_id FROM alarm_events WHERE alarm_id = %s"),
                (alarm_id,),
            )
            assert remaining == []
        if database.get_init_flag():
            database.disconnect()
