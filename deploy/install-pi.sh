#!/usr/bin/env bash
set -euo pipefail

# Run from a checkout on your development machine. Only this app is replaced.
cd "$(dirname "$0")/.."
target=${1:-gabe@gabepi}
ssh "$target" 'mkdir -p /home/gabe/code/gabriel-draw /home/gabe/.local/share/gabriel-draw /home/gabe/.config'
rsync -a --exclude .venv --exclude __pycache__ --exclude '*.sqlite3*' draw-server/ "$target:/home/gabe/code/gabriel-draw/"
scp deploy/gabriel-draw.service "$target:/home/gabe/code/gabriel-draw/gabriel-draw.service"
ssh "$target" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /home/gabe/code/gabriel-draw
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod 700 /home/gabe/.local/share/gabriel-draw
sudo -n install -m 644 gabriel-draw.service /etc/systemd/system/gabriel-draw.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable gabriel-draw.service
sudo -n systemctl restart gabriel-draw.service
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8012/health; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8012/health
tailscale serve status --json > "/home/gabe/.local/share/gabriel-draw/tailscale-before-$(date +%s).json"
sudo -n tailscale funnel --bg --yes --https=8443 --set-path=/draw-api http://127.0.0.1:8012
REMOTE
