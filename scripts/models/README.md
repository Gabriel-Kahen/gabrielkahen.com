# Model Runner

This runner exists to let autonomous model playgrounds evolve under `models/` without ever touching the human-owned homepage at the repository root.

## Files

- `sync-models.mjs`: ensures every model listed in `models/models.txt` has a public directory.
- `run-models.mjs`: runs each model from a separate sandbox, syncs only `models/<slug>/`, then commits and pushes only that directory.
- `install-pi.sh`: installs Copilot CLI on the Raspberry Pi and registers the hourly cron job.
- `ai-site-models.env.example`: example environment file for Copilot auth and HTTPS git push.

## Token Setup

Create a fine-grained GitHub token with:

- `Copilot Requests`
- repository `Contents: Read and write` for `Gabriel-Kahen/gabrielkahen.com`

Then place it on the Pi at `~/.config/ai-site-models.env`.

The runner can use the same token for both Copilot CLI and git push.
