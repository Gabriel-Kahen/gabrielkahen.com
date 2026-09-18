#!/usr/bin/env bash
set -euo pipefail

# Run from a checkout on your development machine. Only this app is replaced.
cd "$(dirname "$0")/.."
target=${1:-gabe@gabepi}
ssh "$target" 'mkdir -p /home/gabe/code/gabriel-draw /home/gabe/.local/share/gabriel-draw /home/gabe/.config'
rsync -a --exclude .venv --exclude __pycache__ --exclude '*.sqlite3*' draw-server/ "$target:/home/gabe/code/gabriel-draw/"
scp deploy/gabriel-draw.service "$target:/home/gabe/code/gabriel-draw/gabriel-draw.service"
scp deploy/gabriel-camera.service "$target:/home/gabe/code/gabriel-draw/gabriel-camera.service"
scp deploy/migrate_database.py "$target:/home/gabe/code/gabriel-draw/migrate_database.py"
ssh "$target" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /home/gabe/code/gabriel-draw
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo -n systemctl start mnt-fastssd.mount
mountpoint -q /mnt/fastssd
test "$(findmnt -n -o UUID --target /mnt/fastssd)" = ab4b373f-26c6-4631-b78a-76c72fa89db8
sudo -n install -d -o gabe -g gabe -m 700 /mnt/fastssd/gabriel-draw
if systemctl is-active --quiet gabriel-draw.service; then
  sudo -n systemctl stop gabriel-draw.service
fi
.venv/bin/python migrate_database.py
sudo -n install -m 644 gabriel-draw.service /etc/systemd/system/gabriel-draw.service
sudo -n install -m 644 gabriel-camera.service /etc/systemd/system/gabriel-camera.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable gabriel-draw.service
sudo -n systemctl enable gabriel-camera.service
sudo -n systemctl restart gabriel-draw.service
sudo -n systemctl restart gabriel-camera.service
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8012/health; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8012/health
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8766/health; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8766/health
tailscale serve status --json > "/home/gabe/.local/share/gabriel-draw/tailscale-before-$(date +%s).json"
sudo -n tailscale funnel --bg --yes --https=8443 --set-path=/draw-api http://127.0.0.1:8012
sudo -n tailscale funnel --bg --yes --https=8443 --set-path=/draw-camera http://127.0.0.1:8766
REMOTE
