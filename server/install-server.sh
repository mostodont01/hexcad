#!/usr/bin/env bash
# Install / update the HexCAD build store on a Linux box over SSH (no root needed):
#   server/install-server.sh tab01            (ssh host alias)
# Runs server/setup.sh there (uv + HexCAD, `hexcad serve` on port 8770 with a crontab @reboot line).
# Then point clients at it:  ~/.config/hexcad/config.json  {"server": "http://<host-ip>:8770"}
# Tablets installed with the tablet installer (github.com/mostodont01/tablets) get it as the "hexcad" role instead.
set -euo pipefail
HOST=${1:?usage: install-server.sh <ssh-host>}
ssh "$HOST" bash -s < "$(dirname "$0")/setup.sh"
