"""
sql_loader.py - Reads .sql files from the sql/ directory.

Supports named queries within a file using -- @query_name markers.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Dict, List

from scripts.paths import SQL_DIR

logger = logging.getLogger(__name__)


def load_sql_file(filename: str) -> str:
    """Read entire SQL file as string."""
    path = SQL_DIR / filename
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_named_queries(filename: str) -> Dict[str, str]:
    """Parse a SQL file into named queries separated by '-- @name' markers."""
    text = load_sql_file(filename)
    queries: Dict[str, str] = {}
    current_name: str | None = None
    current_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-- @"):
            if current_name:
                queries[current_name] = "\n".join(current_lines).strip()
            current_name = stripped[4:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_name:
        queries[current_name] = "\n".join(current_lines).strip()
    return queries


def execute_sql_file(conn: sqlite3.Connection, filename: str, ignore_errors: bool = True) -> None:
    """Execute all statements in a SQL file against a connection."""
    text = load_sql_file(filename)
    for stmt in text.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        # Skip blocks that are ONLY comments (no real SQL)
        has_sql = any(
            line.strip() and not line.strip().startswith("--")
            for line in stmt.splitlines()
        )
        if not has_sql:
            continue
        try:
            conn.execute(stmt)
        except Exception as exc:
            if not ignore_errors:
                raise
            logger.debug("SQL statement skipped (ignore_errors=True): %s", exc)
    conn.commit()
