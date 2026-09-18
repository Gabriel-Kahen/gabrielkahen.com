# Drawing receiver for gabepi

A write-only FastAPI service saves original vector strokes and generated Ender 3 G-code in one SQLite transaction. The API itself does **not** connect to a printer. The separate, explicitly armed `printer_worker.py` streams new validated vectors using the current pen calibration; see below. Original archive records and their placeholder G-code retain status `pending_calibration`. API receipts report the separate printer job status when available.

## Run on the Pi

Requires Python 3.11 or later. From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DRAW_DB_PATH=/mnt/fastssd/gabriel-draw/drawings.sqlite3
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8012 --workers 1 --no-proxy-headers
```

Use one worker: the submission rate limit is deliberately global and lives in memory. The default is 60 POST attempts per minute, independent of client-provided forwarding headers. With Tailscale Funnel the service may see one loopback client for all visitors; this does not change the global limit. HTTPS publication, systemd installation, and the site's API URL are covered by the repository's deployment files.

The deployed service stores the database at `/mnt/fastssd/gabriel-draw/drawings.sqlite3` on the Micron SSD with mode `0600`. Standalone development runs default to `~/.local/share/gabriel-draw/drawings.sqlite3`; set `DRAW_DB_PATH` or pass `--db` to the export command when working with the deployed database. The pre-migration SD database is retained as a backup and is no longer updated. No drawings or G-code are placed inside the public website. SQLite commits both representations together, including the printer configuration used for that drawing and an ISO UTC creation timestamp. Back up the database with SQLite's backup command/API or stop the service before copying it.

## API

`GET /health` returns `{"status":"ok","version":1}`. `POST /drawings` accepts `Content-Type: application/json`:

```json
{
  "version": 2,
  "submission_id": "6f59cd0a-314e-48f7-92db-f1d83e57aba8",
  "strokes": [
    [[20, 25], [22, 28], [25, 26]],
    [[80, 90]]
  ]
}
```

`/draw-api/health` and `/draw-api/drawings` are identical aliases so a reverse proxy can preserve or remove the `/draw-api` prefix. There are no public read, list, export, or deletion endpoints.

Version 2 coordinates are millimeters on a 200 × 200 mm square, with `(0, 0)` at the upper-left corner and `(200, 200)` at the lower-right. Version 1 is still accepted with its original portrait US Letter dimensions `(215.9, 279.4)`, mapping, and retry identity. The coordinate version is saved with each drawing; existing records and G-code remain unchanged. Each stroke is an ordered list of `[x, y]` points. A single point is a dot. The server rejects unknown fields, invalid UUIDs, duplicate JSON keys, numeric strings, booleans, nonfinite coordinates, out-of-area coordinates, empty strokes, over 200 strokes, over 20,000 total points, and bodies over 1 MiB, including streamed bodies. It recomputes the sum of distances between adjacent points *within each stroke*. The maximum is 1219.2 mm (48 inches), with 0.000001 mm floating-point tolerance. Pen-up travel does not count. Client-supplied G-code is never accepted.

A new drawing returns HTTP 201:

```json
{
  "id": "6f59cd0a-314e-48f7-92db-f1d83e57aba8",
  "submission_id": "6f59cd0a-314e-48f7-92db-f1d83e57aba8",
  "created_at": "2026-09-14T00:00:00Z",
  "length_mm": 7.211102550927978,
  "status": "pending_calibration"
}
```

The example length is illustrative. Retrying the same submission UUID and geometry returns the original receipt with HTTP 200; changing geometry under the same UUID returns 409. A client should retain its UUID until a submission succeeds or the drawing changes. Uploads have a 15-second body deadline. Errors use `{"error":"Message"}` with 408 for upload timeout, 413 for body size, 415 for unsupported media/encoding, 422 for validation, 429 for rate limit (with `Retry-After: 60`), and 503 for storage capacity/busy conditions.

CORS permits only `https://gabrielkahen.com` and `https://www.gabrielkahen.com` by default. POST requests with another Origin are rejected. This is a public submission service; CORS is a browser policy, not authentication.

## Limits and configuration

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `DRAW_DB_PATH` | `~/.local/share/gabriel-draw/drawings.sqlite3` | Local database file |
| `DRAW_MAX_STORAGE_BYTES` | `134217728` | 128 MiB cap on main SQLite file and stored payload accounting |
| `DRAW_MAX_DRAWINGS` | `10000` | Maximum records; existing identical retries still work |
| `DRAW_REQUESTS_PER_MINUTE` | `60` | Global POST attempt limit; resets when service restarts |
| `DRAW_NEW_PER_MINUTE` | `6` | New accepted drawings per rolling minute; persists across restarts |
| `DRAW_NEW_PER_HOUR` | `30` | New accepted drawings per rolling hour; persists across restarts |
| `DRAW_MAX_PENDING` | `3` | Maximum queued plus printing jobs in the current printer session, including while paused |
| `DRAW_EXTRA_ORIGINS` | empty | Explicit comma-separated development origins, e.g. `http://localhost:8080` |
| `DRAW_PRINTER_CONFIG` | empty | Path to a JSON object with fields from `printer.example.json` |

SQLite uses its default rollback journal; leave additional free disk space for its temporary journal (up to approximately another database-sized file), filesystem overhead, and operating-system logs. The application never grows the main database beyond its configured SQLite page cap. It does not delete accepted drawings to make space; the owner must export/archive them and remove records locally. Logical record-size checks and a record count cap supplement the physical cap.

## Pen plotting and calibration

Version 2's 200 × 200 mm square maps 1:1 into the Ender 3's configured 220 × 220 mm machine coordinate area, with a 10 mm margin on every side: X `10..210`, Y `10..210` mm. Screen `(0, 0)` maps to machine `(10, 210)` and screen `(200, 200)` maps to `(210, 10)`. Y is flipped from the screen's downward axis to the printer's upward axis. Smaller configured beds or a smaller configured drawing height uniformly reduce the scale to preserve margins and proportions. The 48-inch source limit equals the default plotted path limit.

Legacy version 1 retains its Letter mapping: uniform scale `200/279.4 ≈ 0.7158196`, X `32.7273..187.2727`, Y `10..210` mm under the default configuration, and approximately 34.36 plotted inches at full source budget. No database migration is needed. Export returns the exact G-code already stored for a drawing, without regenerating it using new defaults.

The generator traces each submitted point in its original order and processes strokes in their original order. It does not rasterize, fill, optimize/reorder, or slice the image. XY travels between strokes happen with the pen lifted. Z changes only for pen placement and lifting; each drawn XY move contains no Z or extrusion command. Dots pause for 100 ms. Output is rounded to four decimal places in millimeters.

Defaults assume the pen tip sits at the nozzle position, contact Z is `0` mm, and lifted Z is `3` mm. These are **uncalibrated placeholders**. Before executing any exported file:

1. Home the printer with the pen removed. Mount the pen afterward so homing cannot drive it into the bed.
2. Secure flat paper and calibrate the pen's absolute contact/lift heights, bed placement, and available travel. Configure those values before submitting production drawings. Existing records preserve their original configuration and G-code.
3. Verify mesh leveling is off and firmware supports the generated Marlin commands. The file includes `M420 S0` so leveling does not add Z motion during XY strokes. A machine whose firmware does not support that command must have leveling disabled by its supported controls before plotting.
4. Preview the path and do a raised-pen test before a contact run. Use a compliant pen mount and conservative feeds suitable for the actual hardware.

The file turns heaters and fan off (`M104 S0`, `M140 S0`, `M107`), uses millimeters/absolute moves (`G21`, `G90`), starts with a lift, and leaves the pen lifted with motors enabled. It contains no homing, origin reset, extrusion, or heating instruction. The operator remains responsible for calibration and explicitly executing the file.

## Local export and tests

```sh
python3 export.py 6f59cd0a-314e-48f7-92db-f1d83e57aba8 \
  --db /mnt/fastssd/gabriel-draw/drawings.sqlite3 \
  --output /home/gabe/drawing.gcode
python3 export.py 6f59cd0a-314e-48f7-92db-f1d83e57aba8 --format json
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Export opens the database read-only, selects by UUID, and writes only the requested local file (or stdout). Tests cover square boundary mapping at 1:1 scale, legacy Letter mapping and retry compatibility, traversal, Y inversion, uniform scaling, pen lifts, dots, calibration configuration bounds, length and schema validation, atomic storage, retry conflicts, CORS, body limits, byte/count caps, rate limits, and local export.


## Live printer worker (current temporary calibration)

`printer_worker.py` consumes new database rows, regenerating bounded movements from
validated vectors. **It never executes the archived placeholder G-code.** The
website still accepts the full 200 mm square; the worker scales it uniformly to
the verified 140 mm square X−173..−33, Y−180..−40, centered X−103 Y−110. Legacy Letter
vectors are also uniformly fit. Contact Z is −4.00 mm, lifted Z0, drawing feed
720 mm/min (12 mm/s), travel1200 (20 mm/s), Z30 (0.5 mm/s). Before motor-step quantization, the worker removes pointer jitter with 0.06 mm
RDP tolerance and rounds gentle turns using quadratic curves with at most 0.5 mm
trim per side (limited to a quarter of either adjacent segment). Curve sampling
uses 0.2 mm control-polygon steps. Turns of 60 degrees or more stay sharp; open
endpoints, exact loop closure and stroke order are preserved. Smoothing stays
inside the input convex hull, cannot increase path length, and final coordinates
are checked against calibrated bounds. Archived vectors and the browser sketch
remain original; this processing applies to the physical printer path. Quantized
duplicate points are removed. Continuous local serial delivery waits for
completion per stroke, not per segment. The pen lifts between strokes and parks
at X−3 Y−10 Z0 to present the bed to the front camera. The expanded
travel envelope is permitted only at lifted Z0; writing bounds remain unchanged. Temporary M204 P100 T100 / M205 X1 Y1 use the tested gentle profile.

The worker exclusively opens the USB serial device, verifies starting motor counts
(−240,−800,0), matching logical coordinates, endstops and M92 80/80/400. It disables
idle stepper release with M84 S0 to retain this temporary calibration. It must be
stopped before manual serial calibration. No homing, origin reset, EEPROM write,
extrusion, or heating is performed. On clean stop, it finishes the current stroke,
lifts, and restores acceleration/jerk and software endstops. On a transport or
position fault it disarms and closes without attempting uncertain recovery moves.
Inspect/recalibrate before restarting; firmware counts cannot detect manual motion.

`plot_session` records an atomic MAX(rowid) cutoff at arming. **Every existing
submission is excluded**, including old retries. New jobs are claimed durably in
`plot_jobs` before movement and processed FIFO, once each. Failed/interrupted jobs
are never automatically retried. On any new arming, all then-existing submissions
are again excluded. Queue states are queued/printing/done/failed/interrupted or
printer_offline in POST receipts; immutable archive records are unchanged. Multiple
submissions use the same physical paper; the system cannot replace paper itself.

Installation after deploying this directory to `/home/gabe/code/gabriel-draw`:

```sh
.venv/bin/pip install -r requirements-printer.txt
sudo install -m 644 gabriel-plotter.service /etc/systemd/system/gabriel-plotter.service
sudo systemctl daemon-reload
# Only after checking the live calibration and park position:
sudo systemctl start gabriel-plotter
journalctl -u gabriel-plotter -n 20 --no-pager
# Stop before changing setup, paper placement, or manual printer control:
sudo systemctl stop gabriel-plotter
```

Copy the service from `deploy/gabriel-plotter.service`. It deliberately has no boot
enablement or automatic restart: this is a temporary calibrated session. A restart
is a new arming operation with a fresh cutoff. Logs rotate at 10 MiB with two
backups alongside the database. The API remains available if the worker stops.
The API service needs restarting after deploying its receipt-status integration.

Tests include real HTTP submission → SQLite queue → mocked serial movements,
old UUID retries, durable claiming, FIFO, restart exclusion, offline receipts,
geometry rejection, both coordinate versions, lifts, dots, parking, continuous
strokes, and failure before calibration verification.


### Submission latency

After the SQLite commit, the API sends a nonblocking Unix datagram to
`plotter-wakeup.sock` beside the database. The worker wakes immediately and claims
the durable job. Notifications contain no drawing or G-code, can be coalesced,
and are only a hint: a 250 ms fallback finds jobs even if notification fails.
Idle position checks run every five seconds and still run before every drawing.
The browser preconnects to the receiver origin to begin DNS/TLS work early.

`benchmark_dispatch.py --root /mnt/fastssd/gabriel-draw` creates a disposable
SQLite database and loopback HTTP API on port18012; it never opens serial or
submits to the production API. On gabepi, 2026-09-14, HTTP request start through
commit, claim and validated path: old1s polling median718.016ms (10 samples),
notification median12.105ms/max13.414ms (20 samples). These numbers exclude public
internet/TLS, actual serial verification, pen travel and descent. Physical feed
rates and all bounds remain unchanged. Raw serial command timestamps remain in
the rotating printer log for the actual user test.


### Submission abuse limits

New submissions are admitted under the same SQLite write transaction as insertion.
An index on creation time supports persistent rolling quotas:6 new drawings/minute
and30/hour globally. Concurrent requests cannot race past these limits or the
3-job printer backlog cap. The backlog includes queued and currently printing
jobs even when the worker is paused; completed/failed/interrupted jobs and archives
before the session cutoff do not occupy slots. Archive-only installations without
a printer session enforce the acceptance quotas but have no printer backlog cap.

Identical UUID retries return the original receipt before admission checks, do not
regenerate G-code, and do not occupy another slot. New requests rejected by quotas
also skip G-code generation. All attempts still share the existing60/minute early
in-memory limit,1MiB body cap,15-second upload deadline, input complexity and path
length checks, storage caps, and24-connection deployment concurrency cap. Limits
are global: Funnel hides visitor addresses, and untrusted forwarding headers are
not used as identity. CORS alone is not authentication.

Admission rejections return429 with Retry-After (seconds until quota capacity, or
15seconds for a full queue). Retry-After is exposed to the allowed browser origins.
The browser displays the server's specific error while retaining the drawing.
Security tests use isolated temporary databases; none enqueue production jobs.
