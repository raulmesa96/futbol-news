"""Historial de publicaciones en SQLite: la memoria que evita repetir noticias.

Guardamos tres claves por noticia porque cada una atrapa un tipo de repetición
distinto: `guid` y `link` pillan la misma pieza releída del mismo feed, y
`title_key` pilla la misma noticia contada por otro medio (ver `dedup.py`).
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import config

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS posted (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    guid       TEXT NOT NULL,
    link       TEXT NOT NULL,
    title      TEXT NOT NULL,
    title_key  TEXT NOT NULL,
    posted_at  TEXT NOT NULL,
    message_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_posted_guid ON posted(guid);
CREATE INDEX IF NOT EXISTS idx_posted_link ON posted(link);
CREATE INDEX IF NOT EXISTS idx_posted_at ON posted(posted_at);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _window_start() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.DEDUP_WINDOW_DAYS)
    return cutoff.isoformat()


def seen(conn: sqlite3.Connection, guid: str, link: str) -> bool:
    """¿Publicamos ya exactamente esta pieza? (mismo guid o mismo enlace)"""
    row = conn.execute(
        "SELECT 1 FROM posted WHERE guid = ? OR link = ? LIMIT 1", (guid, link)
    ).fetchone()
    return row is not None


def recent_title_keys(conn: sqlite3.Connection) -> list[str]:
    """Huellas de titulares dentro de la ventana de deduplicación."""
    rows = conn.execute(
        "SELECT title_key FROM posted WHERE posted_at >= ?", (_window_start(),)
    ).fetchall()
    return [r["title_key"] for r in rows]


def record(
    conn: sqlite3.Connection,
    *,
    source: str,
    guid: str,
    link: str,
    title: str,
    title_key: str,
    message_id: int | None,
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO posted
           (source, guid, link, title, title_key, posted_at, message_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            source,
            guid,
            link,
            title,
            title_key,
            datetime.now(timezone.utc).isoformat(),
            message_id,
        ),
    )
    conn.commit()


def prune(conn: sqlite3.Connection) -> int:
    """Borra el historial fuera de la ventana. Devuelve cuántas filas cayeron."""
    cur = conn.execute("DELETE FROM posted WHERE posted_at < ?", (_window_start(),))
    conn.commit()
    return cur.rowcount


def stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT source, COUNT(*) AS n, MAX(posted_at) AS ultima
           FROM posted GROUP BY source ORDER BY n DESC"""
    ).fetchall()
