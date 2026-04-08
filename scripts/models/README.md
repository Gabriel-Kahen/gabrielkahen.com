# Model Runner

This runner exists to let autonomous model playgrounds evolve under `models/` without ever touching the human-owned homepage at the repository root.

## Files

- `sync-models.mjs`: ensures every model listed in `models/models.txt` has a public directory.
- `run-models.mjs`: runs each model through OpenCode from a separate sandbox, syncs only `models/<slug>/`, then commits and pushes only that directory.
- `install-pi.sh`: installs OpenCode on the Raspberry Pi and registers the every-3-hours cron job.
- `ai-site-models.env.example`: optional environment file for runner overrides.

## Auth Setup

- Authenticate OpenCode with the GitHub Copilot provider.
- Make sure the Pi clone can push to `Gabriel-Kahen/gabrielkahen.com`.

The production setup on the Pi currently uses a writable SSH deploy key for git push.

If you want custom runner environment variables, place them in `~/.config/ai-site-models.env`.

OpenCode credentials are stored separately under `~/.local/share/opencode/auth.json`.
