# gabrielkahen.com

The site is published from `main` by GitHub Pages. The drawing page lives at
[`gabrielkahen.com/draw/`](https://gabrielkahen.com/draw/).

## Drawing project

`draw/` is a standalone, dependency-free drawing interface. It records ordered
polylines in millimeters on a 215.9 × 279.4 mm US Letter sheet, using an approximate
0.4 mm ballpoint line. Pen-down distance is limited to 609.6 mm (24 inches); lifted
travel does not count. Undo restores the last stroke's allowance.

`draw-server/` validates submissions, generates stroke-following Ender 3 G-code,
and saves both representations in SQLite on `gabe@gabepi`. No printer execution
is connected to submissions. See [the server guide](draw-server/README.md) for
calibration, settings, API details, and exporting saved jobs.

The default plot is 154.545 × 200 mm, centered within a 220 × 220 mm machine
coordinate area. It scales the entire Letter frame uniformly, preserves stroke
order and direction, and flips screen Y into machine Y. The 24-inch allowance
is measured before this scaling. The physical pen determines the printed line
width; the screen preview approximates a BIC ballpoint on the original sheet.

## Deploy

From this checkout, run `bash deploy/install-pi.sh`. It installs the backend at
`/home/gabe/code/gabriel-draw`, with a persistent database at
`/home/gabe/.local/share/gabriel-draw/drawings.sqlite3`, and enables the
`gabriel-draw` system service. Configuration overrides belong in
`/home/gabe/.config/gabriel-draw.env` on the Pi.

The existing Tailscale Funnel routes `/draw-api` on
`https://gabepi.tail0cb95e.ts.net:8443` to loopback port 8012. It preserves the
other existing routes. The page's API URL is in `draw/config.js`. HTTPS uploads
are public; no Tailscale account is required for visitors. If the Pi is offline,
the page preserves the drawing so visitors can retry later.

Push the static changes to `main` to publish GitHub Pages. Backend source,
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
