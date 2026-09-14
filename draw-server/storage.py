"""Atomic local storage with UUID retries and bounded database growth."""

from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from drawing import generate_gcode


class ConflictingSubmission(Exception):
    pass


class StorageFull(Exception):
    pass


class AdmissionLimited(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = max(1, math.ceil(retry_after))


class Store:
    def __init__(self, path, max_bytes, max_drawings, new_per_minute=6, new_per_hour=30, max_pending=3):
        self.path = Path(path).expanduser()
        self.max_bytes = max_bytes
        self.max_drawings = max_drawings
        self.new_per_minute = new_per_minute
        self.new_per_hour = new_per_hour
        self.max_pending = max_pending

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
            db.execute("CREATE INDEX IF NOT EXISTS drawings_created_at ON drawings(created_at)")
        self.path.chmod(0o600)

    def admit(self, db, now):
        # Runs under the same write transaction as insertion: workers and restarts
        # share a quota; forwarded headers and UUID changes do not reset it.
        for window, limit in ((60, self.new_per_minute), (3600, self.new_per_hour)):
            cutoff = datetime.fromtimestamp(now-window, timezone.utc).isoformat().replace("+00:00", "Z")
            recent = db.execute("SELECT created_at FROM drawings WHERE created_at>? ORDER BY created_at DESC LIMIT ?",
                                (cutoff, limit)).fetchall()
            if len(recent) >= limit:
                oldest = datetime.fromisoformat(recent[-1][0].replace("Z", "+00:00")).timestamp()
                raise AdmissionLimited("Drawing submission limit reached. Please try again later.", oldest+window-now)
        # Archive-only installations have no printer session or active backlog.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('plot_session','plot_jobs')")}
        if len(tables) == 2:
            pending = db.execute("""SELECT COUNT(*) FROM drawings d
                JOIN plot_session s ON s.id=1 AND d.rowid>s.cutoff
                LEFT JOIN plot_jobs j ON j.submission_id=d.submission_id
                WHERE j.submission_id IS NULL OR j.status='printing'""").fetchone()[0]
            if pending >= self.max_pending:
                raise AdmissionLimited("The printer queue is full. Please try again after a drawing finishes.", 15)

    def save(self, submission_id, strokes, length, canonical, config):
        settings = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT * FROM drawings WHERE submission_id = ?", (submission_id,)).fetchone()
                if existing:
                    if existing["vector_json"] != canonical:
                        raise ConflictingSubmission
                    return self.receipt(existing), False
                now = datetime.now(timezone.utc)
                self.admit(db, now.timestamp())
                created = now.isoformat().replace("+00:00", "Z")
                gcode = generate_gcode(strokes, config, json.loads(canonical)["version"])
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
