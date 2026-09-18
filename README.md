# gabrielkahen.com

The site is published from `main` by GitHub Pages. The drawing page lives at
[`gabrielkahen.com/draw/`](https://gabrielkahen.com/draw/).

## Drawing project

`draw/` is a standalone, dependency-free drawing interface. It records ordered
polylines in millimeters on a 215 × 175 mm rectangle, using an approximate
0.4 mm ballpoint line. Pen-down distance is limited to 1219.2 mm (48 inches); lifted
travel does not count. Undo restores the last stroke's allowance.

`draw-server/` validates submissions, generates stroke-following Ender 3 G-code,
and saves both representations in SQLite on `gabe@gabepi`. An explicitly armed
worker streams new submissions to the printer. See [the server guide](draw-server/README.md) for
calibration, settings, API details, and exporting saved jobs.

New version 3 drawings map 1:1 to the manually measured 215 × 175 mm area:
screen `(0, 0)` at machine `X−148 Y−15`, and screen `(215, 175)` at
`X67 Y−190`. Stroke order is preserved and screen Y is flipped into machine Y.
The physical pen determines line width;
the preview approximates a BIC ballpoint.

The drawing page also shows a live, upright 760 × 650 view cropped around the
paper. The Pi encodes the camera once and serves the newest in-memory JPEG at
five frames per second per browser; frames are not recorded or written to disk.

Version 1 Letter and version 2 square submissions retain their original dimensions,
and saved server records are never rewritten. New rectangular drawings use a
separate version 3 draft key.

## Deploy

From this checkout, run `bash deploy/install-pi.sh`. It installs the backend at
`/home/gabe/code/gabriel-draw`, with a persistent database at
`/mnt/fastssd/gabriel-draw/drawings.sqlite3` on the Micron SSD, and enables the
`gabriel-draw` system service. Configuration overrides belong in
`/home/gabe/.config/gabriel-draw.env` on the Pi.

Deployment requires the SSD labeled `fastssd` (UUID
`ab4b373f-26c6-4631-b78a-76c72fa89db8`) mounted at `/mnt/fastssd`. The first
SSD deployment copies and verifies the original SD-card database, preserving
the original as a backup. Later deployments retain the SSD database. The service
depends on the mount and stops if it disappears, so uploads cannot silently fall
back to the SD card. After reconnecting the drive, start `mnt-fastssd.mount` and
then `gabriel-draw.service`.

The existing Tailscale Funnel routes `/draw-api` on
`https://gabepi.tail0cb95e.ts.net:8443` to loopback port 8012. It preserves the
other existing routes. The page's API URL is in `draw/config.js`. HTTPS uploads
are public; no Tailscale account is required for visitors. If the Pi is offline,
the page preserves the drawing so visitors can retry later.

On devices in the Pi's own Tailscale network, MagicDNS resolves the API hostname
to the Pi's private address. Chrome may ask for local-network access; allow it
for this site to submit through that private route. Visitors outside the tailnet
use the public Funnel address. Headless live tests need that permission or a
temporary resolver mapping to the hostname's current public DNS address.

Deploy the backend before publishing version 3 static changes, so older clients
and the new rectangular client can submit. Push the static changes
to `main` to publish GitHub Pages. Backend source,
deployment files, and tests are excluded from the Pages build.

For local UI work, run `python3 -m http.server 8765` from this directory and open
`http://localhost:8765/draw/`. Local API uploads require explicitly adding that
origin through `DRAW_EXTRA_ORIGINS`; production accepts only the site origins.

## Checks

Run `npm ci && npm test` for geometry tests. With the local static server running,
`npm run test:browser` checks drawing, touch input, undo, paper and ink bounds,
draft recovery, and submission retries in headless Chrome. Set `CHROME_PATH` if
Chrome is installed somewhere other than `/usr/bin/google-chrome-stable`.
Browser tests mock uploads and write screenshots to `test-results/`.

For backend checks, install `draw-server/requirements-dev.txt` in a Python virtual
environment, change into `draw-server`, and run `python -m pytest -q`.
