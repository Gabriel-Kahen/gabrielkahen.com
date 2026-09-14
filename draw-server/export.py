"""Read one saved drawing locally. This command never connects to a printer."""

import argparse
import os
from pathlib import Path
import sqlite3
import sys
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission_id", type=UUID)
    parser.add_argument("--db", default=os.getenv("DRAW_DB_PATH", str(Path.home() / ".local/share/gabriel-draw/drawings.sqlite3")))
    parser.add_argument("--output", type=Path, help="Write G-code here; defaults to stdout.")
    parser.add_argument("--format", choices=("gcode", "json"), default="gcode")
    args = parser.parse_args()
    db_path = Path(args.db).expanduser().resolve()
    try:
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute("SELECT gcode, vector_json FROM drawings WHERE submission_id = ?", (str(args.submission_id),)).fetchone()
    except sqlite3.Error as error:
        parser.exit(1, f"Cannot read drawing database: {error}\n")
    if row is None:
        parser.exit(1, "Drawing not found.\n")
    content = row[0 if args.format == "gcode" else 1]
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
