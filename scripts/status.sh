#!/usr/bin/env bash
# Show address, subnet, public key, and connected peers.
# Exit 0 healthy, 1 node down, 2 node up but no peer connected.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

ygg_require_cmd python3

CONF="${YGG_CONF:-$YGG_CONF_DEFAULT}"
endpoint="$YGG_ADMIN_DEFAULT"
if [[ -f "$CONF" || -f "$YGG_OVERLAY" ]]; then
  endpoint=$(python3 - "$CONF" "$YGG_OVERLAY" "$YGG_ADMIN_DEFAULT" <<'PY'
import json
import re
import sys

conf_path, overlay_path, fallback = sys.argv[1], sys.argv[2], sys.argv[3]


def read_admin(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("AdminListen"), str) and data["AdminListen"]:
        return data["AdminListen"]
    match = re.search(
        r'(?m)^\s*"?AdminListen"?\s*:\s*"?([^"\s,}]+)',
        text,
    )
    if match:
        return match.group(1)
    return None


print(read_admin(conf_path) or read_admin(overlay_path) or fallback)
PY
  )
fi

sock=""
case "$endpoint" in
  unix://*)
    sock=${endpoint#unix://}
    ;;
esac

if [[ -n "$sock" && -S "$sock" && ! -r "$sock" && "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemd_state=$(systemctl is-active "$YGG_SERVICE" 2>/dev/null || true)
  echo "systemd: ${systemd_state:-unbekannt}"
fi

CTL=${YGGDRASILCTL:-yggdrasilctl}
if ! command -v "$CTL" >/dev/null 2>&1; then
  echo "Status: down"
  echo "yggdrasilctl nicht gefunden."
  exit 1
fi

self_file=$(mktemp)
peers_file=$(mktemp)
cleanup() {
  # Invoked via trap; shellcheck cannot see that call.
  # shellcheck disable=SC2317
  rm -f "$self_file" "$peers_file"
}
trap cleanup EXIT

# yggdrasilctl returns exit 0 even when the admin socket is unreachable and
# writes that failure to stdout. The report parser treats non-JSON as down.
"$CTL" -json -endpoint="$endpoint" getSelf >"$self_file" 2>/dev/null || true
"$CTL" -json -endpoint="$endpoint" getPeers >"$peers_file" 2>/dev/null || true

set +e
python3 "$YGG_STATUS_PY" --self "$self_file" --peers "$peers_file"
code=$?
set -e
exit "$code"
