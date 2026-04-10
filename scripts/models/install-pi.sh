#!/bin/sh

set -eu

PI_REPO_ROOT="${PI_REPO_ROOT:-$HOME/code/gabrielkahen.com}"
PI_WORKSPACE_ROOT="${PI_WORKSPACE_ROOT:-$HOME/.ai-site-playgrounds}"
CRON_LOG="${CRON_LOG:-$PI_WORKSPACE_ROOT/cron.log}"
ENV_FILE="${AI_SITE_ENV_FILE:-$HOME/.config/ai-site-models.env}"
PATH_LINE='PATH=$HOME/.opencode/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin'

mkdir -p "$HOME/code"
mkdir -p "$PI_WORKSPACE_ROOT"
mkdir -p "$HOME/.config"

if [ ! -d "$PI_REPO_ROOT/.git" ]; then
  git clone "https://github.com/Gabriel-Kahen/gabrielkahen.com.git" "$PI_REPO_ROOT"
else
  git -C "$PI_REPO_ROOT" pull --ff-only origin main
fi

if ! command -v opencode >/dev/null 2>&1; then
  curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path
fi

node "$PI_REPO_ROOT/scripts/models/sync-models.mjs"

if [ ! -f "$HOME/.config/ai-site-models.env.example" ]; then
  cp "$PI_REPO_ROOT/scripts/models/ai-site-models.env.example" "$HOME/.config/ai-site-models.env.example"
fi

mkdir -p "$PI_WORKSPACE_ROOT"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'scripts/models/run-models.mjs' | grep -v '^PATH=\$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin$' > "$TMP_CRON" || true
sed -i '/^PATH=\$HOME\/\.opencode\/bin:\$HOME\/\.local\/bin:\/usr\/local\/bin:\/usr\/bin:\/bin$/d' "$TMP_CRON" 2>/dev/null || true
printf '%s\n' "$PATH_LINE" >> "$TMP_CRON"
printf '7 */3 * * * if [ -f "%s" ]; then . "%s"; fi; AI_SITE_WORKSPACE_ROOT="%s" node "%s/scripts/models/run-models.mjs" >> "%s" 2>&1\n' "$ENV_FILE" "$ENV_FILE" "$PI_WORKSPACE_ROOT" "$PI_REPO_ROOT" "$CRON_LOG" >> "$TMP_CRON"
printf '37 */6 * * * if [ -f "%s" ]; then . "%s"; fi; AI_SITE_WORKSPACE_ROOT="%s" node "%s/scripts/models/run-models.mjs" --maintenance >> "%s" 2>&1\n' "$ENV_FILE" "$ENV_FILE" "$PI_WORKSPACE_ROOT" "$PI_REPO_ROOT" "$CRON_LOG" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

printf 'Pi install complete.\n'
printf 'Repository: %s\n' "$PI_REPO_ROOT"
printf 'Workspace: %s\n' "$PI_WORKSPACE_ROOT"
printf 'Cron log: %s\n' "$CRON_LOG"
printf 'Environment file: %s\n' "$ENV_FILE"
printf 'OpenCode GitHub Copilot auth and Git push credentials still need to be configured if they are not already present.\n'
