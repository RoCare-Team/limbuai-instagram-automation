import sqlite3
import time
from contextlib import contextmanager
from .config import DB_PATH, IG_ACCESS_TOKEN, IG_USER_ID, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comment_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                reply_text TEXT NOT NULL,
                match_type TEXT NOT NULL DEFAULT 'contains',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                reply_text TEXT NOT NULL,
                match_type TEXT NOT NULL DEFAULT 'contains',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                detail TEXT,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ig_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ig_user_id TEXT NOT NULL,
                username TEXT,
                access_token TEXT NOT NULL,
                expires_at INTEGER,
                connected_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Connected Instagram account (populated by the OAuth login flow).
# Falls back to the .env token so local testing works before anyone logs in.
# ---------------------------------------------------------------------------

def save_account(ig_user_id: str, access_token: str, expires_in: int | None = None,
                 username: str | None = None):
    expires_at = int(time.time()) + expires_in if expires_in else None
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ig_account (id, ig_user_id, username, access_token, expires_at,
                                       connected_at)
               VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                   ig_user_id = excluded.ig_user_id,
                   username = excluded.username,
                   access_token = excluded.access_token,
                   expires_at = excluded.expires_at,
                   connected_at = CURRENT_TIMESTAMP""",
            (ig_user_id, username, access_token, expires_at),
        )
        conn.commit()


def get_account() -> dict | None:
    """Stored account, or the .env fallback, or None if nothing is configured."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ig_account WHERE id = 1").fetchone()
    if row:
        return dict(row)
    if IG_ACCESS_TOKEN:
        return {
            "ig_user_id": IG_USER_ID,
            "username": None,
            "access_token": IG_ACCESS_TOKEN,
            "expires_at": None,
            "connected_at": None,
            "source": "env",
        }
    return None


def clear_account():
    with get_conn() as conn:
        conn.execute("DELETE FROM ig_account WHERE id = 1")
        conn.commit()


class _DictCursor:
    """Wraps a DB-API cursor so fetchone()/fetchall() return plain dicts
    (row["col"] and dict(row) both work), matching sqlite3.Row's behavior."""

    def __init__(self, cursor):
        self._cursor = cursor

    def _columns(self):
        return [d[0] for d in self._cursor.description] if self._cursor.description else []

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(zip(self._columns(), row)) if row is not None else None

    def fetchall(self):
        cols = self._columns()
        return [dict(zip(cols, row)) for row in self._cursor.fetchall()]


class _TursoConn:
    """Thin sqlite3-compatible wrapper around the libsql remote connection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return _DictCursor(self._conn.execute(sql, params))

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


@contextmanager
def get_conn():
    if TURSO_DATABASE_URL:
        import libsql
        conn = _TursoConn(libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN))
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def log_activity(event_type: str, detail: str, status: str = "success"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log (event_type, detail, status) VALUES (?, ?, ?)",
            (event_type, detail, status),
        )
        conn.commit()
