"""CID→token content cache using SQLite.

Schema:
  - table cid_tokens(
      cid TEXT PRIMARY KEY,
      content TEXT NOT NULL,
      token_level INTEGER,
      token_number INTEGER
    )
"""

import sqlite3
from typing import Optional, Tuple

DB_PATH = "cid_tokens.db"


def init_db(db_path: str = DB_PATH) -> None:
    """Create the cid_tokens table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cid_tokens (
            cid TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            token_level INTEGER,
            token_number INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_level_number
        ON cid_tokens(token_level, token_number)
        """
    )
    conn.commit()
    conn.close()


def upsert_token(
    cid: str,
    content: str,
    token_level: Optional[int] = None,
    token_number: Optional[int] = None,
    db_path: str = DB_PATH,
) -> None:
    """Insert or update a CID→content row."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cid_tokens (cid, content, token_level, token_number)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cid) DO UPDATE SET
            content=excluded.content,
            token_level=excluded.token_level,
            token_number=excluded.token_number
        """,
        (cid, content, token_level, token_number),
    )
    conn.commit()
    conn.close()


def get_content_by_cid(
    cid: str,
    db_path: str = DB_PATH,
) -> Optional[Tuple[str, Optional[int], Optional[int]]]:
    """Return (content, token_level, token_number) for a CID or None."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT content, token_level, token_number FROM cid_tokens WHERE cid = ?",
        (cid,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None

