"""Tiny SQLite store so analyses and suites survive restarts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Analysis, Suite, to_dict


class History:
    def __init__(self, path: str = ".qa_copilot/history.db"):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, story TEXT, analysis TEXT, suite TEXT)""")
        self._conn.commit()

    def save(self, story: str, analysis: Analysis | None, suite: Suite | None) -> int:
        title = (story.strip().splitlines() or ["Untitled"])[0][:80]
        cur = self._conn.execute(
            "INSERT INTO runs(title, story, analysis, suite) VALUES (?,?,?,?)",
            (title, story, json.dumps(to_dict(analysis)) if analysis else None,
             json.dumps(to_dict(suite)) if suite else None))
        self._conn.commit()
        return int(cur.lastrowid)

    def list(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, created, title FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "created": r[1], "title": r[2]} for r in rows]

    def load(self, run_id: int) -> tuple[str, Analysis | None, Suite | None]:
        row = self._conn.execute(
            "SELECT story, analysis, suite FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return (row[0], Analysis.from_dict(json.loads(row[1])) if row[1] else None,
                Suite.from_dict(json.loads(row[2])) if row[2] else None)
