#!/usr/bin/env bash
# Fail if a private key or generated node config is present in the tree.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

cd "$YGG_ROOT"
fail=0

while IFS= read -r -d '' file; do
  base=$(basename "$file")
  case "$base" in
    *.pem | *.key | yggdrasil.conf | id_yggdrasil*)
      echo "secret file: ${file}" >&2
      fail=1
      ;;
  esac
done < <(find . -path ./.git -prune -o -path ./config/peers.candidates.txt -prune -o -type f -print0)

if grep -RInE --exclude-dir=.git --exclude=peers.candidates.txt \
  -e 'BEGIN [A-Z0-9 ]*PRIVATE KEY' \
  -e 'PrivateKey"?[[:space:]]*:[[:space:]]*"[0-9a-fA-F]{32,}"' \
  .; then
  echo "PrivateKey material found in the tree" >&2
  fail=1
fi

if grep -RInE --exclude-dir=.git --exclude=peers.candidates.txt -e '[0-9a-fA-F]{128}' .; then
  echo "128-character hex private key found in the tree" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "Keine Knotengeheimnisse im Arbeitsbaum."
