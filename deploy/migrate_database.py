"""Copy the original SD database to the SSD once, retaining the source backup."""

from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile


def migrate(source, destination):
    if destination.exists() or not source.exists():
        return
    handle, temporary = tempfile.mkstemp(prefix=".migration-", dir=destination.parent)
    os.close(handle)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as old:
            with closing(sqlite3.connect(temporary)) as new:
                old.backup(new)
                if new.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Migrated database failed its integrity check.")
                query = "SELECT * FROM drawings ORDER BY submission_id"
                if old.execute(query).fetchall() != new.execute(query).fetchall():
                    raise RuntimeError("Migrated drawing records differ from the source.")
        os.chmod(temporary, 0o600)
        os.rename(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    migrate(Path("/home/gabe/.local/share/gabriel-draw/drawings.sqlite3"),
            Path("/mnt/fastssd/gabriel-draw/drawings.sqlite3"))
