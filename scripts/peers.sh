#!/usr/bin/env bash
# List, check, refresh, or select public peers.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

ygg_require_cmd python3

usage() {
  cat <<'EOF'
usage:
  peers.sh list
  peers.sh check
  peers.sh refresh
  peers.sh select [--write] [--limit N]

refresh downloads Germany and nearby EU peers into config/peers.candidates.txt.
select prints the preferred subset. --write replaces config/peers.txt.
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

action=$1
shift
case "$action" in
  list | check | refresh | select) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    ygg_die "Unbekannte Aktion: ${action}"
    ;;
esac

exec python3 "$YGG_PEERS_PY" "$action" \
  --peers "$YGG_PEERS" \
  --candidates "$YGG_CANDIDATES" \
  --repo-root "$YGG_ROOT" \
  "$@"
