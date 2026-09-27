#!/usr/bin/env bash
# Build /etc/yggdrasil/yggdrasil.conf from a key generated on this machine
# plus the committed overlay and peer list.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
  cat <<'EOF'
usage: configure.sh [--conf PATH] [--bin PATH] [--no-service]

Generate or update the on-machine Yggdrasil config. The private key is taken
from the existing config, or created with `yggdrasil -genconf` when none
exists. The key is never written into the git repository.
EOF
}

CONF="$YGG_CONF_DEFAULT"
BIN="${YGGDRASIL_BIN:-yggdrasil}"
NO_SERVICE=0
original_args=("$@")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --conf)
      CONF=${2:-}
      shift 2
      ;;
    --bin)
      BIN=${2:-}
      shift 2
      ;;
    --no-service)
      NO_SERVICE=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      ygg_die "Unbekanntes Argument: $1"
      ;;
  esac
done

if [[ "$NO_SERVICE" -eq 0 && "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "${original_args[@]}"
fi

ygg_assert_outside_repo "$CONF"
ygg_require_cmd python3

if [[ "$BIN" != /* ]]; then
  if ! command -v "$BIN" >/dev/null 2>&1; then
    ygg_die "yggdrasil nicht gefunden. Zuerst sudo ./scripts/install.sh ausführen."
  fi
  BIN=$(command -v "$BIN")
elif [[ ! -x "$BIN" ]]; then
  ygg_die "yggdrasil-Binary nicht ausführbar: ${BIN}"
fi

umask 077
base=$(mktemp)
merged=$(mktemp)
cleanup() {
  rm -f "$base" "$merged"
}
trap cleanup EXIT

if [[ -s "$CONF" ]]; then
  "$BIN" -normaliseconf -json -useconffile "$CONF" >"$base"
else
  "$BIN" -genconf -json >"$base"
fi
chmod 600 "$base" "$merged"

python3 "$YGG_MERGE_PY" \
  --base "$base" \
  --overlay "$YGG_OVERLAY" \
  --peers "$YGG_PEERS" \
  --output "$merged" \
  --repo-root "$YGG_ROOT"

changed=0
if [[ -f "$CONF" ]] && cmp -s "$merged" "$CONF"; then
  echo "Keine Änderung an ${CONF}."
else
  dest_dir=$(dirname "$CONF")
  mkdir -p "$dest_dir"
  if [[ -f "$CONF" && "$(id -u)" -eq 0 ]]; then
    backup="/var/backups/yggdrasil.conf.$(date +%Y%m%d%H%M%S)"
    mkdir -p /var/backups
    cp -a "$CONF" "$backup"
    chmod 640 "$backup"
    echo "Vorherige Konfiguration gesichert: ${backup}"
  fi
  if [[ "$(id -u)" -eq 0 ]] && getent group yggdrasil >/dev/null 2>&1; then
    chown root:yggdrasil "$dest_dir"
    chmod 750 "$dest_dir"
    install -o root -g yggdrasil -m 0640 "$merged" "$CONF"
  else
    install -m 0600 "$merged" "$CONF"
  fi
  echo "Konfiguration aktualisiert: ${CONF}"
  changed=1
fi

if [[ "$NO_SERVICE" -eq 0 ]]; then
  systemctl enable "$YGG_SERVICE"
  if [[ "$changed" -eq 1 ]] || ! systemctl is-active --quiet "$YGG_SERVICE"; then
    systemctl restart "$YGG_SERVICE"
    echo "Dienst ${YGG_SERVICE} neu gestartet."
  else
    echo "Dienst ${YGG_SERVICE} läuft bereits mit dieser Konfiguration."
  fi
fi
