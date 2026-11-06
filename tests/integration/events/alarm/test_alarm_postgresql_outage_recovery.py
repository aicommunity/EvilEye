from __future__ import annotations

import json
import select
import socket
import socketserver
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql

from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.database_controller.db_adapter_alarm_events import DatabaseAdapterAlarmEvents
from evileye.events_detectors.alarm_event import AlarmEvent


class _PostgresProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _PostgresProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        client = self.request
        if not server.forward_enabled.is_set():
            return
        try:
            upstream = socket.create_connection(server.target, timeout=3.0)
        except OSError:
            return

        with server.active_lock:
            if not server.forward_enabled.is_set():
                upstream.close()
                return
            server.active_sockets.update((client, upstream))

        try:
            client.setblocking(True)
            upstream.setblocking(True)
            while server.forward_enabled.is_set():
                readable, _, _ = select.select((client, upstream), (), (), 0.1)
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is client else client
                    target.sendall(data)
        except (OSError, ValueError):
            return
        finally:
            with server.active_lock:
                server.active_sockets.discard(client)
                server.active_sockets.discard(upstream)
            for connection in (client, upstream):
                try:
                    connection.close()
                except OSError:
                    pass


class _PostgresFaultProxy:
    def __init__(self, host: str, port: int):
        self.server = _PostgresProxyServer(
            ("127.0.0.1", 0), _PostgresProxyHandler
        )
        self.server.target = (host, port)
        self.server.forward_enabled = threading.Event()
        self.server.forward_enabled.set()
        self.server.active_lock = threading.Lock()
        self.server.active_sockets = set()
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="PostgresFaultProxy",
            daemon=True,
        )
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def pause(self) -> None:
        self.server.forward_enabled.clear()
        with self.server.active_lock:
            active = tuple(self.server.active_sockets)
            self.server.active_sockets.clear()
        for connection in active:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass

    def resume(self) -> None:
        self.server.forward_enabled.set()

    def close(self) -> None:
        self.pause()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


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


def _database_for_proxy(config, proxy, image_dir: Path):
    values = dict(config["database"])
    values.setdefault("user_name", "postgres")
    values.setdefault("password", "")
    values.setdefault("admin_user_name", "postgres")
    values.setdefault("admin_password", "")
    values.update(
        host_name="127.0.0.1",
        port=proxy.port,
        connect_timeout_secs=2,
        statement_timeout_ms=5000,
        image_dir=str(image_dir),
    )
    database = DatabaseControllerPg({"pipeline": {"sources": []}})
    database.set_params(
        user_name=values["user_name"],
        password=values["password"],
        database_name=values.get("database_name", "evil_eye_db"),
        host_name=values["host_name"],
        port=values["port"],
        connect_timeout_secs=values["connect_timeout_secs"],
        statement_timeout_ms=values["statement_timeout_ms"],
        admin_user_name=values["admin_user_name"],
        admin_password=values["admin_password"],
        image_dir=values["image_dir"],
        create_new_project=values.get("create_new_project", False),
        tables=values["tables"],
        preview_width=values.get("preview_width", 300),
        preview_height=values.get("preview_height", 150),
    )
    return database


@pytest.mark.integration
def test_alarm_adapter_recovers_after_postgresql_connection_outage(tmp_path):
    config = _load_database_config()
    database_config = config["database"]
    proxy = _PostgresFaultProxy(
        database_config.get("host_name", "localhost"),
        int(database_config.get("port", 5432)),
    )
    database = _database_for_proxy(config, proxy, tmp_path)
    adapter = None
    alarm_id = f"outage-recovery-{uuid4()}"
    first_connection_error = threading.Event()
    connection_errors = []
    query_once = database.query_once

    def observed_query_once(query, values=None):
        try:
            return query_once(query, values)
        except psycopg2.OperationalError as error:
            connection_errors.append(type(error).__name__)
            first_connection_error.set()
            raise

    try:
        database.init()
        database.connect()
        if not database.is_connected():
            pytest.skip("Configured PostgreSQL database is unavailable")

        from evileye.database_controller.migrations import apply_startup_migrations

        apply_startup_migrations(database)
        database.query_checked("SELECT 1")

        adapter = DatabaseAdapterAlarmEvents(database)
        adapter.set_params(table_name="alarm_events", queue_maxsize=8)
        adapter.init()
        database.query_once = observed_query_once
        adapter.start()
        proxy.pause()
        alarm = AlarmEvent(
            "connection_recovery_test",
            severity="warning",
            source_id=0,
            details={"test": "PostgreSQL outage recovery"},
            alarm_id=alarm_id,
        )
        alarm.set_id(int(time.time() * 1000) % 2_000_000_000)
        adapter.insert(alarm)

        assert first_connection_error.wait(timeout=5.0), (
            "The controlled proxy outage did not reach the alarm adapter"
        )
        proxy.resume()

        deadline = time.monotonic() + 8.0
        while adapter.get_runtime_stats()["processed_items"] < 1:
            if time.monotonic() >= deadline:
                pytest.fail(
                    "Alarm adapter did not recover after PostgreSQL forwarding "
                    f"was restored: {adapter.get_runtime_stats()}"
                )
            time.sleep(0.02)

        # Replaying the same alarm after recovery must remain idempotent.
        adapter.insert(alarm)
        adapter.stop()

        records = database.query_checked(
            sql.SQL(
                "SELECT alarm_id FROM alarm_events WHERE alarm_id = %s"
            ),
            (alarm_id,),
        )
        assert records == [(alarm_id,)]
        assert connection_errors
        stats = adapter.get_runtime_stats()
        assert stats["processed_items"] == 2
        assert stats["queue_size"] == 0
        assert stats["terminal_write_failures"] == 0
        assert stats["degraded"] is False
        assert stats["worker_alive"] is False
    finally:
        proxy.resume()
        database.query_once = query_once
        if adapter is not None:
            adapter.stop()
        if database.is_connected():
            database.query_checked(
                sql.SQL("DELETE FROM alarm_events WHERE alarm_id = %s"),
                (alarm_id,),
            )
            database.disconnect()
        proxy.close()
