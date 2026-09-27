#!/usr/bin/env bash
# Shared paths and guards. Source this file; do not execute it.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "error: source scripts/lib/common.sh; do not execute it" >&2
  exit 1
fi

_ygg_lib_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
YGG_ROOT=$(cd "${_ygg_lib_dir}/../.." && pwd)
YGG_OVERLAY="${YGG_ROOT}/config/overlay.json"
YGG_PEERS="${YGG_ROOT}/config/peers.txt"
YGG_CANDIDATES="${YGG_ROOT}/config/peers.candidates.txt"
YGG_CONF_DEFAULT="/etc/yggdrasil/yggdrasil.conf"
YGG_ADMIN_DEFAULT="unix:///var/run/yggdrasil/yggdrasil.sock"
YGG_SERVICE="yggdrasil"
YGG_MERGE_PY="${YGG_ROOT}/scripts/lib/merge_config.py"
YGG_PEERS_PY="${YGG_ROOT}/scripts/lib/peers.py"
YGG_STATUS_PY="${YGG_ROOT}/scripts/lib/status_report.py"
export YGG_ROOT YGG_OVERLAY YGG_PEERS YGG_CANDIDATES YGG_CONF_DEFAULT
export YGG_ADMIN_DEFAULT YGG_SERVICE YGG_MERGE_PY YGG_PEERS_PY YGG_STATUS_PY

ygg_die() {
  echo "error: $*" >&2
  exit 1
}

ygg_require_cmd() {
  local cmd
  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      ygg_die "Befehl fehlt: ${cmd}"
    fi
  done
}

# Refuse destinations that resolve inside the git checkout. Node configs
# contain the private key and must stay on the machine, not in the repo.
ygg_assert_outside_repo() {
  local target=$1
  local root final parent
  root=$(realpath "$YGG_ROOT")
  if [[ "$target" != /* ]]; then
    ygg_die "Konfigurationspfad muss absolut sein: ${target}"
  fi
  if [[ -e "$target" ]]; then
    final=$(realpath "$target")
  else
    parent=$(dirname "$target")
    if [[ -d "$parent" ]]; then
      final="$(realpath "$parent")/$(basename "$target")"
    else
      final=$target
    fi
  fi
  case "$final" in
    "$root" | "$root"/*)
      ygg_die "Schreiben von Knotengeheimnissen ins Repository verweigert: ${final}"
      ;;
  esac
}
