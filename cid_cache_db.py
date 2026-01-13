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
import threading
from typing import Optional, Tuple

DB_PATH = "cid_tokens.db"

# Thread-local storage for database connections (connection pooling)
_local = threading.local()


def get_db_connection(db_path: str = DB_PATH):
    """Get a thread-local database connection with optimized settings."""
    if not hasattr(_local, 'connection') or _local.connection is None:
        conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
        # Enable WAL mode for better read concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = sqlite3.Row  # Return dict-like rows
        _local.connection = conn
    return _local.connection


def init_db(db_path: str = DB_PATH) -> None:
    """Create the cid_tokens table if it doesn't exist."""
    conn = sqlite3.connect(db_path, timeout=10.0)
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
    # Enable WAL mode for better concurrency
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA cache_size=-64000")
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
    """
    Return (content, token_level, token_number) for a CID or None.
    Uses thread-local connection for better performance.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT content, token_level, token_number FROM cid_tokens WHERE cid = ?",
        (cid,),
    )
    row = cur.fetchone()
    if row:
        return (row[0], row[1], row[2])
    return None


def get_content_by_cids_batch(
    cids: list,
    db_path: str = DB_PATH,
    chunk_size: int = 1000,
) -> dict:
    """
    Batch lookup for multiple CIDs. Returns a dictionary mapping CID -> (content, token_level, token_number).
    
    Args:
        cids: List of CID strings to lookup
        db_path: Path to database
        chunk_size: Process in chunks to avoid SQL parameter limits (SQLite supports up to 999 params)
    
    Returns:
        Dictionary: {cid: (content, token_level, token_number), ...}
        Only includes CIDs that were found in the database.
    """
    if not cids:
        return {}
    
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    results = {}
    
    # Process in chunks to avoid SQL parameter limits
    # SQLite supports up to 999 parameters, so we use 1000 as chunk size
    for i in range(0, len(cids), chunk_size):
        chunk = cids[i:i + chunk_size]
        placeholders = ','.join(['?'] * len(chunk))
        
        query = f"""
            SELECT cid, content, token_level, token_number 
            FROM cid_tokens 
            WHERE cid IN ({placeholders})
        """
        
        cur.execute(query, chunk)
        rows = cur.fetchall()
        
        # Build result dictionary
        for row in rows:
            cid = row[0]
            results[cid] = (row[1], row[2], row[3])  # (content, token_level, token_number)
    
    return results

