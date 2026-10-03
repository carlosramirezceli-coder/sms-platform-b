import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "platform_b.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id           TEXT PRIMARY KEY,
            to_number    TEXT NOT NULL,
            body         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'queued',
            scheduled_at TEXT,
            sent_at      TEXT,
            error        TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS devices (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            token        TEXT NOT NULL UNIQUE,
            last_seen    TEXT,
            last_port    TEXT,
            last_signal  TEXT,
            last_network TEXT,
            active       INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            key        TEXT PRIMARY KEY,
            label      TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_status    ON messages(status);
        CREATE INDEX IF NOT EXISTS idx_messages_scheduled ON messages(scheduled_at);
    """)
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]
