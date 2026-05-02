"""
SQLite persistence layer.  All functions accept an open sqlite3.Connection.
Callers are responsible for connection lifecycle and commits.
"""

import sqlite3
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'user',
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT    UNIQUE NOT NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            label       TEXT,
            assigned_at TEXT
        );

        CREATE TABLE IF NOT EXISTS time_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id   INTEGER REFERENCES cards(id) ON DELETE SET NULL,
            user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action    TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT    PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT    NOT NULL
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(conn: sqlite3.Connection, name: str, email: str,
                password_hash: str, role: str = "user") -> int:
    cur = conn.execute(
        "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
        (name, email, password_hash, role),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())


def list_users(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn.execute("SELECT * FROM users ORDER BY name").fetchall())


def count_admins(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'"
    ).fetchone()[0]


def list_users_with_status(conn: sqlite3.Connection) -> list[dict]:
    """List all users with their most-recent time-log action and timestamp."""
    return _rows(conn.execute("""
        SELECT u.id, u.name, u.email, u.role,
               last.action    AS last_action,
               last.timestamp AS last_timestamp
        FROM users u
        LEFT JOIN (
            SELECT t1.user_id, t1.action, t1.timestamp
            FROM time_logs t1
            WHERE t1.id = (
                SELECT id FROM time_logs t2
                WHERE t2.user_id = t1.user_id
                ORDER BY timestamp DESC, id DESC LIMIT 1
            )
        ) last ON last.user_id = u.id
        ORDER BY u.name
    """).fetchall())


def update_user(conn: sqlite3.Connection, user_id: int, **fields) -> None:
    allowed = {"name", "email", "password", "role"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE users SET {set_clause} WHERE id = ?",
        (*updates.values(), user_id),
    )
    conn.commit()


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

def create_card(conn: sqlite3.Connection, uid: str,
                label: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO cards (uid, label) VALUES (?, ?)", (uid, label)
    )
    conn.commit()
    return cur.lastrowid


def get_card_by_uid(conn: sqlite3.Connection, uid: str) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM cards WHERE uid = ?", (uid,)).fetchone())


def get_card_by_id(conn: sqlite3.Connection, card_id: int) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone())


def list_cards(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn.execute("""
        SELECT c.*, u.name AS user_name
        FROM cards c
        LEFT JOIN users u ON c.user_id = u.id
        ORDER BY c.id
    """).fetchall())


def assign_card(conn: sqlite3.Connection, card_id: int,
                user_id: Optional[int], label: Optional[str] = None) -> None:
    """
    Update a card's user assignment and/or label.

    `assigned_at` is only touched when `user_id` actually changes:
      - reassigning  → set to now
      - unassigning  → set to NULL
      - label-only   → unchanged (preserves history)
    """
    current = get_card_by_id(conn, card_id)
    if current is None:
        return

    if current["user_id"] == user_id:
        # User unchanged — only update the label
        conn.execute(
            "UPDATE cards SET label = ? WHERE id = ?",
            (label, card_id),
        )
    elif user_id is None:
        # Unassign — clear assigned_at
        conn.execute(
            "UPDATE cards SET user_id = NULL, label = ?, assigned_at = NULL WHERE id = ?",
            (label, card_id),
        )
    else:
        # New or different assignment — stamp assigned_at
        conn.execute(
            "UPDATE cards SET user_id = ?, label = ?, assigned_at = datetime('now') WHERE id = ?",
            (user_id, label, card_id),
        )
    conn.commit()


def delete_card(conn: sqlite3.Connection, card_id: int) -> None:
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    conn.commit()


def count_checked_in(conn: sqlite3.Connection) -> int:
    """Return the number of users currently checked in (last action = check_in)."""
    return conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT user_id, action
            FROM time_logs t1
            WHERE id = (
                SELECT id FROM time_logs t2
                WHERE t2.user_id = t1.user_id
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
            )
            AND action = 'check_in'
        )
    """).fetchone()[0]


# ---------------------------------------------------------------------------
# Time logs
# ---------------------------------------------------------------------------

def get_last_log_for_user(conn: sqlite3.Connection,
                           user_id: int) -> Optional[dict]:
    return _row(conn.execute(
        "SELECT * FROM time_logs WHERE user_id = ? ORDER BY timestamp DESC, id DESC LIMIT 1",
        (user_id,),
    ).fetchone())


def insert_log(conn: sqlite3.Connection, card_id: Optional[int],
               user_id: int, action: str) -> int:
    cur = conn.execute(
        "INSERT INTO time_logs (card_id, user_id, action) VALUES (?, ?, ?)",
        (card_id, user_id, action),
    )
    conn.commit()
    return cur.lastrowid


def list_logs(
    conn: sqlite3.Connection,
    user_id: Optional[int] = None,
    from_dt: Optional[str] = None,
    to_dt: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return (rows, total_count).  Timestamps are ISO-8601 strings."""
    conditions = []
    params: list[Any] = []

    if user_id is not None:
        conditions.append("tl.user_id = ?")
        params.append(user_id)
    if from_dt is not None:
        conditions.append("tl.timestamp >= ?")
        params.append(from_dt)
    if to_dt is not None:
        conditions.append("tl.timestamp <= ?")
        params.append(to_dt)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total: int = conn.execute(
        f"SELECT COUNT(*) FROM time_logs tl {where}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = _rows(conn.execute(f"""
        SELECT
            tl.id, tl.action, tl.timestamp,
            tl.card_id, tl.user_id,
            c.uid  AS card_uid,
            c.label AS card_label,
            u.name  AS user_name
        FROM time_logs tl
        LEFT JOIN cards c ON tl.card_id = c.id
        LEFT JOIN users u ON tl.user_id = u.id
        {where}
        ORDER BY tl.timestamp DESC
        LIMIT ? OFFSET ?
    """, [*params, per_page, offset]).fetchall())

    return rows, total


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(conn: sqlite3.Connection, token: str,
                   user_id: int, expires_at: str) -> None:
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    return _row(conn.execute(
        "SELECT * FROM sessions WHERE token = ? AND expires_at > datetime('now')",
        (token,),
    ).fetchone())


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def delete_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    conn.commit()
