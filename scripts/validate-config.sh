#!/usr/bin/env bash
# Validate the committed overlay against the official Yggdrasil 0.5.14 binary.
# The generated private key stays in a temporary directory outside the repo.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

YGG_VERSION="0.5.14"
YGG_DEB_SHA256="72745496b09baa1c3f5a6741e1257a704cfdb9d00cdf3ddbef025987b239699d"
YGG_DEB_URL="https://github.com/yggdrasil-network/yggdrasil-go/releases/download/v${YGG_VERSION}/yggdrasil-${YGG_VERSION}-amd64.deb"

ygg_require_cmd python3 curl
cd "$YGG_ROOT"

work=$(mktemp -d)
cleanup() {
  rm -rf "$work"
}
trap cleanup EXIT
chmod 700 "$work"

deb="${YGG_DEB:-$work/yggdrasil.deb}"
if [[ ! -f "$deb" ]]; then
  curl -fsSL "$YGG_DEB_URL" -o "$deb"
fi
echo "${YGG_DEB_SHA256}  ${deb}" | sha256sum -c -

mkdir -p "$work/root"
dpkg-deb -x "$deb" "$work/root"
bin="$work/root/usr/bin/yggdrasil"
"$bin" -version

"$bin" -genconf -json >"$work/base.json"
chmod 600 "$work/base.json"
mkdir -p "$work/node"
cp "$work/base.json" "$work/node/yggdrasil.conf"
chmod 600 "$work/node/yggdrasil.conf"

log="$work/configure.out"
"${SCRIPT_DIR}/configure.sh" --no-service --bin "$bin" --conf "$work/node/yggdrasil.conf" >"$log"
if grep -q -f <(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["PrivateKey"])' "$work/base.json") "$log"; then
  ygg_die "configure.sh hat den privaten Schlüssel auf stdout geschrieben"
fi

python3 - "$work/base.json" "$work/node/yggdrasil.conf" "$YGG_PEERS" <<'PY'
import json
import pathlib
import sys

base = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
merged = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
peers = [
    line.strip()
    for line in pathlib.Path(sys.argv[3]).read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
]
assert merged["PrivateKey"] == base["PrivateKey"].lower()
assert merged["NodeInfo"]["name"] == "hannover-primary"
assert merged["NodeInfo"]["location"] == "Hannover/DE"
assert merged["AdminListen"] == "unix:///var/run/yggdrasil/yggdrasil.sock"
assert merged["IfName"] == "ygg0"
assert merged["Listen"] == []
assert merged["Peers"] == peers
assert "PrivateKey" not in json.loads(
    pathlib.Path("config/overlay.json").read_text(encoding="utf-8")
)
PY

cp "$work/node/yggdrasil.conf" "$work/node/first.json"
"${SCRIPT_DIR}/configure.sh" --no-service --bin "$bin" --conf "$work/node/yggdrasil.conf" >"$work/second.out"
cmp -s "$work/node/first.json" "$work/node/yggdrasil.conf"
grep -q "Keine Änderung" "$work/second.out"

pubkey=$("$bin" -useconffile "$work/node/yggdrasil.conf" -publickey)
address=$("$bin" -useconffile "$work/node/yggdrasil.conf" -address)
subnet=$("$bin" -useconffile "$work/node/yggdrasil.conf" -subnet)
python3 - "$pubkey" "$address" "$subnet" <<'PY'
import re
import sys

pubkey, address, subnet = sys.argv[1:]
if not re.fullmatch(r"[0-9a-f]{64}", pubkey.strip()):
    raise SystemExit(f"unexpected public key: {pubkey!r}")
if not re.fullmatch(r"[0-9a-f:]+", address.strip()):
    raise SystemExit(f"unexpected address: {address!r}")
if not subnet.strip().endswith("/64"):
    raise SystemExit(f"unexpected subnet: {subnet!r}")
PY

if "${SCRIPT_DIR}/configure.sh" --no-service --bin "$bin" --conf "${YGG_ROOT}/yggdrasil.conf" >"$work/refused.out" 2>"$work/refused.err"; then
  ygg_die "configure.sh hat einen Pfad im Repository akzeptiert"
fi
if [[ -e "${YGG_ROOT}/yggdrasil.conf" ]]; then
  ygg_die "configure.sh hat eine Konfiguration im Repository angelegt"
fi
grep -q "verweigert" "$work/refused.err"

echo "Konfigurationsvorlage ist mit Yggdrasil ${YGG_VERSION} gültig."
