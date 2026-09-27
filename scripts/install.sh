#!/usr/bin/env bash
# Idempotent install of Yggdrasil from the official Debian/Ubuntu repository.
# Steps follow https://yggdrasil-network.github.io/installation-linux-deb.html
# (repository key 1840CDAC6011C5EA, published 2025-11-11) over HTTPS.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

KEY_URL="https://neilalexander.s3.dualstack.eu-west-2.amazonaws.com/deb/key.txt"
KEY_FPR="1C5162E133015D81A811239D1840CDAC6011C5EA"
KEYRING="/usr/local/apt-keys/yggdrasil-keyring.gpg"
LIST_FILE="/etc/apt/sources.list.d/yggdrasil.list"
PIN_FILE="/etc/apt/preferences.d/yggdrasil"
SOURCE_LINE="deb [signed-by=${KEYRING}] https://neilalexander.s3.dualstack.eu-west-2.amazonaws.com/deb/ debian yggdrasil"

ygg_require_debian() {
  if [[ ! -r /etc/os-release ]]; then
    ygg_die "Keine /etc/os-release gefunden. Dieses Skript erwartet Debian oder Ubuntu."
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}" in
    debian | ubuntu | linuxmint | pop | elementary | neon | raspbian) return 0 ;;
  esac
  case "${ID_LIKE:-}" in
    *debian*) return 0 ;;
  esac
  ygg_die "Dieses Installationsskript unterstützt Debian, Ubuntu und Derivate mit systemd."
}

ygg_note_wsl() {
  if [[ -r /proc/version ]] && grep -qi microsoft /proc/version; then
    echo "WSL erkannt. systemd und /dev/net/tun werden geprüft."
    if [[ ! -e /dev/net/tun ]]; then
      echo "Hinweis: /dev/net/tun fehlt. Der Dienst braucht TUN (in aktuellem WSL2 normalerweise vorhanden)." >&2
    fi
  fi
}

ygg_install_key() {
  local workdir actual current=""
  install -d -m 0755 /usr/local/apt-keys
  if [[ -f "$KEYRING" ]]; then
    current=$(gpg --batch --show-keys --with-colons "$KEYRING" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}' || true)
  fi
  if [[ "$current" == "$KEY_FPR" ]]; then
    echo "Repository-Schlüssel ist bereits aktuell."
    return 0
  fi
  workdir=$(mktemp -d)
  chmod 700 "$workdir"
  # Same fetch the official instructions run via `gpg --fetch-keys`, isolated
  # in a temporary GNUPGHOME so the operator keyring stays untouched.
  if ! GNUPGHOME="$workdir" gpg --batch --yes --fetch-keys "$KEY_URL"; then
    rm -rf "$workdir"
    ygg_die "Repository-Schlüssel konnte nicht geladen werden: ${KEY_URL}"
  fi
  actual=$(GNUPGHOME="$workdir" gpg --batch --with-colons --list-keys | awk -F: '$1=="fpr"{print $10; exit}')
  if [[ "$actual" != "$KEY_FPR" ]]; then
    rm -rf "$workdir"
    ygg_die "Unerwarteter Repository-Schlüssel: ${actual:-leer} (erwartet ${KEY_FPR})"
  fi
  GNUPGHOME="$workdir" gpg --batch --export "$KEY_FPR" >"${workdir}/keyring.gpg"
  install -m 0644 "${workdir}/keyring.gpg" "$KEYRING"
  rm -rf "$workdir"
  echo "Repository-Schlüssel installiert (${KEY_FPR})."
}

ygg_require_debian
ygg_note_wsl

if ! command -v systemctl >/dev/null 2>&1; then
  ygg_die "systemd fehlt. Unter WSL in /etc/wsl.conf [boot] systemd=true setzen und danach 'wsl --shutdown' ausführen."
fi
init_comm=$(ps -p 1 -o comm= | tr -d ' ')
if [[ "$init_comm" != "systemd" ]]; then
  ygg_die "PID 1 ist '${init_comm}', nicht systemd. Unter WSL zuerst systemd aktivieren und 'wsl --shutdown' ausführen."
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg dirmngr python3
if apt-cache show apt-transport-https 2>/dev/null | grep -q '^Package:'; then
  apt-get install -y apt-transport-https
fi

ygg_install_key

if [[ "$(cat "$LIST_FILE" 2>/dev/null || true)" != "$SOURCE_LINE" ]]; then
  printf '%s\n' "$SOURCE_LINE" >"$LIST_FILE"
  chmod 644 "$LIST_FILE"
  echo "APT-Quelle geschrieben: ${LIST_FILE}"
fi

cat >"$PIN_FILE" <<'EOF'
Package: yggdrasil
Pin: origin neilalexander.s3.dualstack.eu-west-2.amazonaws.com
Pin-Priority: 990
EOF
chmod 644 "$PIN_FILE"

apt-get update
apt-get install -y yggdrasil

if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
  usermod -aG yggdrasil "$SUDO_USER" || true
  echo "Benutzer ${SUDO_USER} ist in der Gruppe yggdrasil (neue Anmeldung nötig, sonst sudo)."
fi

"${SCRIPT_DIR}/configure.sh"
echo "Installation abgeschlossen. Status: sudo ${SCRIPT_DIR}/status.sh"
