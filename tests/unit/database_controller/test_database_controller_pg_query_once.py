from unittest.mock import Mock
from types import SimpleNamespace

import psycopg2

from evileye.database_controller.database_controller_pg import DatabaseControllerPg


class _BrokenCursor:
    def __init__(self, connection, error):
        self.connection = connection
        self.error = error

    def execute(self, query, values):
        self.connection.query = (query, values)
        raise self.error

    def close(self):
        pass


class _BrokenConnection:
    closed = 0

    def __init__(self, error):
        self.cursor_instance = _BrokenCursor(self, error)
        self.rollback_attempted = False
        self.close_attempted = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rollback_attempted = True
        raise psycopg2.InterfaceError("connection already closed")

    def close(self):
        self.close_attempted = True
        self.closed = 1


class _Pool:
    def __init__(self, connection):
        self.connection = connection
        self.returned = []

    def getconn(self):
        return self.connection

    def putconn(self, connection, close=False):
        self.returned.append((connection, close))
        if close:
            connection.close()


def test_query_once_discards_broken_connection_and_preserves_original_error():
    query_error = psycopg2.OperationalError("socket closed during query")
    connection = _BrokenConnection(query_error)
    pool = _Pool(connection)
    controller = SimpleNamespace(conn_pool=pool, logger=Mock())

    try:
        DatabaseControllerPg.query_once(controller, "SELECT 1")
    except psycopg2.OperationalError as error:
        assert error is query_error
    else:
        raise AssertionError("query_once must preserve the database query error")

    assert connection.rollback_attempted is True
    assert connection.close_attempted is True
    assert pool.returned == [(connection, True)]
    controller.logger.exception.assert_not_called()
