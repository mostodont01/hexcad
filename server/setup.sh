#!/usr/bin/env bash
# Install / update the HexCAD build store for the current user (no root needed):
#   setup.sh          install uv + HexCAD, start `hexcad serve` (port 8770, store in ~/hexcad-store) and add a
#                     crontab @reboot line so it comes back after a restart
#   setup.sh none     only install (the caller runs the server, e.g. a systemd unit from the tablet installer)
# Run on the server itself, or from the laptop with install-server.sh <ssh-host>.
set -euo pipefail
MODE=${1:-cron}
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
# zip archive instead of git+https: works on boxes without git
uv tool install --force --python 3.12 "hexcad @ https://github.com/mostodont01/hexcad/archive/refs/heads/main.zip"
mkdir -p ~/hexcad-store
[ "$MODE" = none ] && exit 0
CMD="$HOME/.local/bin/hexcad serve --dir $HOME/hexcad-store >> $HOME/hexcad-store/serve.log 2>&1"
# (|| true: an empty crontab makes grep exit 1, which pipefail would turn into an abort)
( crontab -l 2>/dev/null | grep -v 'hexcad serve' || true ; echo "@reboot $CMD" ) | crontab -
pkill -f 'hexcad serve' || true
nohup bash -c "$CMD" >/dev/null 2>&1 &
for _ in $(seq 20); do curl -fsS http://127.0.0.1:8770/keys >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:8770/keys >/dev/null && echo "HexCAD build store running on $(hostname -I | awk '{print $1}'):8770"
