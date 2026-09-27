#!/usr/bin/env bash
# Remove the Yggdrasil package and the official apt source.
# The node config (and therefore the private key / IPv6 address) is kept
# unless --remove-config is passed.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

REMOVE_CONFIG=0
if [[ "${1:-}" == "--remove-config" ]]; then
  REMOVE_CONFIG=1
elif [[ $# -gt 0 ]]; then
  ygg_die "usage: uninstall.sh [--remove-config]"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now "$YGG_SERVICE" || true
fi

if dpkg -s yggdrasil >/dev/null 2>&1; then
  apt-get remove -y yggdrasil
fi

rm -f /etc/apt/sources.list.d/yggdrasil.list /etc/apt/preferences.d/yggdrasil /usr/local/apt-keys/yggdrasil-keyring.gpg
apt-get update

if [[ "$REMOVE_CONFIG" -eq 1 ]]; then
  rm -rf /etc/yggdrasil
  rm -f /var/backups/yggdrasil.conf.*
  echo "Konfiguration und Sicherungskopien gelöscht. Die IPv6-Adresse dieses Knotens ist damit verloren."
else
  echo "Paket entfernt. ${YGG_CONF_DEFAULT} bleibt erhalten (privater Schlüssel)."
  echo "Zum Löschen der Identität: sudo ${SCRIPT_DIR}/uninstall.sh --remove-config"
fi
