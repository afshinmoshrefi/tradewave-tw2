"""Gateway Postgres pooling and write-throttling contracts."""

import pytest

from apiserver import db


pytestmark = pytest.mark.unit


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, params):
        self.statements.append((" ".join(statement.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    closed = False

    def __init__(self, rows):
        self.fake_cursor = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_):
        return self.fake_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePool:
    def __init__(self, conn):
        self.conn = conn
        self.returned = []

    def getconn(self):
        return self.conn

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))


def test_cursor_returns_connection_and_commits(monkeypatch):
    conn = FakeConnection([])
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_connection_pool", lambda: pool)

    with db.cursor(commit=True) as cur:
        cur.execute("SELECT %s", (1,))

    assert conn.commits == 1 and conn.rollbacks == 0
    assert pool.returned == [(conn, False)]


def test_key_lookup_throttles_last_used_write(monkeypatch):
    row = {"user_id": "u1", "key_id": "k1"}
    conn = FakeConnection([row])
    monkeypatch.setattr(db, "_connection_pool", lambda: FakePool(conn))

    assert db.get_user_by_key_hash("hash") == row
    update = conn.fake_cursor.statements[1][0]
    assert "last_used_at < now() - interval '60 seconds'" in update
    assert conn.commits == 1
