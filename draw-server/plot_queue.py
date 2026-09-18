"""Local, durable printer queue, independent of immutable drawing receipts."""
from contextlib import contextmanager
import sqlite3
import time


class Queue:
    def __init__(self, path):
        self.path = str(path)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def arm(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS plot_session (id INTEGER PRIMARY KEY CHECK(id=1), cutoff INTEGER, active INTEGER, heartbeat REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS plot_jobs (submission_id TEXT PRIMARY KEY, source_rowid INTEGER UNIQUE, status TEXT, error TEXT)')
            db.execute("UPDATE plot_jobs SET status='interrupted', error='Previous session ended' WHERE status='printing'")
            cutoff = db.execute('SELECT COALESCE(MAX(rowid),0) FROM drawings').fetchone()[0]
            db.execute('INSERT OR REPLACE INTO plot_session VALUES (1,?,1,?)', (cutoff,time.time()))
            return cutoff

    def heartbeat(self, active=True):
        with self.connect() as db:
            db.execute('UPDATE plot_session SET active=?,heartbeat=? WHERE id=1', (int(active),time.time()))

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT d.rowid AS source_rowid,d.submission_id,d.vector_json FROM drawings d
                JOIN plot_session s ON s.id=1 AND s.active=1 AND d.rowid>s.cutoff
                LEFT JOIN plot_jobs j ON j.submission_id=d.submission_id
                WHERE j.submission_id IS NULL ORDER BY d.rowid LIMIT 1''').fetchone()
            if row:
                db.execute("INSERT INTO plot_jobs VALUES (?,?,'printing',NULL)", (row['submission_id'],row['source_rowid']))
                return dict(row)

    def finish(self, identifier, status, error=None):
        if status not in ('done','failed','interrupted'):
            raise ValueError('Invalid final state')
        with self.connect() as db:
            db.execute('UPDATE plot_jobs SET status=?,error=? WHERE submission_id=?', (status,error,identifier))

    def receipt_status(self, identifier):
        try:
            with self.connect() as db:
                job = db.execute('SELECT status FROM plot_jobs WHERE submission_id=?',(identifier,)).fetchone()
                if job:
                    return job[0]
                row = db.execute('''SELECT d.rowid>s.cutoff,s.active,s.heartbeat FROM drawings d
                    JOIN plot_session s ON s.id=1 WHERE d.submission_id=?''',(identifier,)).fetchone()
                if row and row[0]:
                    return 'queued' if row[1] and time.time()-row[2]<30 else 'printer_offline'
        except sqlite3.OperationalError:
            pass  # Receiver also operates without a printer worker installed.
        return None

    def snapshot(self, capacity):
        """Return public aggregate state without exposing jobs or printer details."""
        try:
            with self.connect() as db:
                session = db.execute(
                    'SELECT cutoff,active,heartbeat FROM plot_session WHERE id=1'
                ).fetchone()
                if not session:
                    raise sqlite3.OperationalError
                online = bool(session['active']) and time.time() - session['heartbeat'] < 30
                queued = db.execute('''SELECT COUNT(*) FROM drawings d
                    LEFT JOIN plot_jobs j ON j.submission_id=d.submission_id
                    WHERE d.rowid>? AND j.submission_id IS NULL''', (session['cutoff'],)).fetchone()[0]
                drawing = db.execute("""SELECT COUNT(*) FROM plot_jobs
                    WHERE source_rowid>? AND status='printing'""", (session['cutoff'],)).fetchone()[0]
        except sqlite3.OperationalError:
            online = False
            queued = drawing = 0
        pending = queued + drawing
        state = 'offline' if not online else 'full' if pending >= capacity else 'drawing' if drawing else 'ready'
        return {
            'state': state,
            'accepting_drawings': online and pending < capacity,
            'drawing': bool(drawing),
            'queued': queued,
            'capacity': capacity,
        }
