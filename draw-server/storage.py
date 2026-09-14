"""Atomic local storage with UUID retries and bounded database growth."""

from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from drawing import generate_gcode


class ConflictingSubmission(Exception):
    pass


class StorageFull(Exception):
    pass


class Store:
    def __init__(self, path, max_bytes, max_drawings):
        self.path = Path(path).expanduser()
        self.max_bytes = max_bytes
        self.max_drawings = max_drawings

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            connection.execute(f"PRAGMA max_page_count={self.max_bytes // page_size}")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS drawings (
                submission_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                length_mm REAL NOT NULL,
                gcode TEXT NOT NULL,
                printer_config_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status = 'pending_calibration')
            )""")
        self.path.chmod(0o600)

    def save(self, submission_id, strokes, length, canonical, config):
        gcode = generate_gcode(strokes, config, json.loads(canonical)["version"])
        settings = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
        created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT * FROM drawings WHERE submission_id = ?", (submission_id,)).fetchone()
                if existing:
                    if existing["vector_json"] != canonical:
                        raise ConflictingSubmission
                    return self.receipt(existing), False
                count, used = db.execute("""SELECT COUNT(*), COALESCE(SUM(
                    LENGTH(vector_json) + LENGTH(gcode) + LENGTH(printer_config_json) + 256), 0)
                    FROM drawings""").fetchone()
                if count >= self.max_drawings or used + len(canonical) + len(gcode) + len(settings) + 256 > self.max_bytes:
                    raise StorageFull
                db.execute("INSERT INTO drawings VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (submission_id, created, canonical, length, gcode, settings, "pending_calibration"))
                row = db.execute("SELECT * FROM drawings WHERE submission_id = ?", (submission_id,)).fetchone()
                return self.receipt(row), True
        except sqlite3.OperationalError as error:
            if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_FULL, sqlite3.SQLITE_BUSY):
                raise StorageFull from error
            raise

    @staticmethod
    def receipt(row):
        return {"id": row["submission_id"], **{key: row[key] for key in ("submission_id", "created_at", "length_mm", "status")}}
