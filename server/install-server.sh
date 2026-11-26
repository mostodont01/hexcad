#!/usr/bin/env bash
# Install / update the HexCAD build store on a Linux box over SSH (no root needed):
#   server/install-server.sh tab01            (ssh host alias)
# It installs uv + HexCAD for the ssh user, starts `hexcad serve` (port 8770, store in ~/hexcad-store) and adds a
# crontab @reboot line so it comes back after a restart. Then point clients at it:
#   ~/.config/hexcad/config.json  {"server": "http://<host-ip>:8770"}
set -euo pipefail
HOST=${1:?usage: install-server.sh <ssh-host>}
ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install --force --python 3.12 "git+https://github.com/mostodont01/hexcad"
mkdir -p ~/hexcad-store
CMD="$HOME/.local/bin/hexcad serve --dir $HOME/hexcad-store >> $HOME/hexcad-store/serve.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'hexcad serve' ; echo "@reboot $CMD" ) | crontab -
pkill -f 'hexcad serve' || true
nohup bash -c "$CMD" >/dev/null 2>&1 &
sleep 3
curl -fsS http://127.0.0.1:8770/keys >/dev/null && echo "HexCAD build store running on $(hostname -I | awk '{print $1}'):8770"
REMOTE
