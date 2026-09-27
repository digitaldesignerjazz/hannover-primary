#!/usr/bin/env python3
"""Merge the non-secret overlay and peer list into a node config.

The private key always comes from the on-machine base config. This tool
refuses to write the result inside the git repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

HEX_KEY = re.compile(r"^[0-9a-fA-F]{128}$")
PEER_URI = re.compile(
    r"^(tcp|tls|quic|ws|wss|socks|sockstls|unix)://\S+$"
)

# Fields the committed overlay is allowed to set. Identity material is absent
# on purpose: a PrivateKey in the overlay is a hard error.
OVERLAY_KEYS = {
    "Listen",
    "AdminListen",
    "IfName",
    "IfMTU",
    "NodeInfoPrivacy",
    "NodeInfo",
    "AllowedPublicKeys",
    "MulticastInterfaces",
}

FORBIDDEN_OVERLAY_KEYS = {
    "PrivateKey",
    "PrivateKeyPath",
    "GroupPassword",
    "Peers",
    "Certificate",
}


class ConfigError(Exception):
    """The merge cannot be applied safely."""


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def load_peers(path: Path) -> list[str]:
    if not path.is_file():
        raise ConfigError(f"peer list not found: {path}")
    peers: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not PEER_URI.match(line):
            raise ConfigError(f"{path}:{lineno}: invalid peer URI: {line}")
        if line not in seen:
            seen.add(line)
            peers.append(line)
    if not peers:
        raise ConfigError(f"{path} has no active peer URIs")
    return peers


def check_overlay(overlay: dict, path: Path) -> None:
    forbidden = FORBIDDEN_OVERLAY_KEYS.intersection(overlay)
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise ConfigError(
            f"{path} must not contain {names}. "
            "Private keys are generated on the node. Peers belong in config/peers.txt."
        )
    unknown = set(overlay) - OVERLAY_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{path} has unsupported keys: {names}")
    missing = {"AdminListen", "IfName", "NodeInfo", "Listen"} - set(overlay)
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigError(f"{path} is missing {names}")
    nodeinfo = overlay["NodeInfo"]
    if not isinstance(nodeinfo, dict):
        raise ConfigError(f"{path} NodeInfo must be an object")
    if nodeinfo.get("name") != "hannover-primary":
        raise ConfigError(f"{path} NodeInfo.name must be hannover-primary")
    if nodeinfo.get("location") != "Hannover/DE":
        raise ConfigError(f"{path} NodeInfo.location must be Hannover/DE")
    if not isinstance(overlay["Listen"], list):
        raise ConfigError(f"{path} Listen must be a list")
    admin = overlay["AdminListen"]
    if not isinstance(admin, str) or "://" not in admin:
        raise ConfigError(f"{path} AdminListen must be a URI")


def resolve_output(path: Path, repo_root: Path) -> Path:
    raw = path.expanduser()
    if not raw.is_absolute():
        raise ConfigError(f"refusing relative config path: {path}")
    root = repo_root.resolve()
    parent = raw.parent
    if parent.is_symlink() or raw.is_symlink():
        final = raw.resolve()
    else:
        final = parent.resolve() / raw.name
    if final == root or root in final.parents:
        raise ConfigError(
            f"refusing to write node secrets inside the repository: {final}"
        )
    return final


def _identity(base: dict) -> dict:
    path = base.get("PrivateKeyPath") or ""
    key = base.get("PrivateKey") or ""
    if isinstance(path, str) and path.strip():
        return {"PrivateKeyPath": path}
    if isinstance(key, str) and HEX_KEY.match(key):
        return {"PrivateKey": key.lower()}
    raise ConfigError(
        "base config has no usable PrivateKey or PrivateKeyPath; "
        "generate it on the node with yggdrasil -genconf"
    )


def merge(base: dict, overlay: dict, peers: list[str]) -> dict:
    merged = dict(base)
    merged.pop("PrivateKey", None)
    merged.pop("PrivateKeyPath", None)
    merged.update(overlay)
    merged["Peers"] = list(peers)
    merged.update(_identity(base))
    return merged


def summary(merged: dict) -> str:
    nodeinfo = merged.get("NodeInfo") or {}
    listen = merged.get("Listen") or []
    listen_text = "(keine — nur ausgehende Peerings)" if not listen else ", ".join(listen)
    lines = [
        f"NodeInfo: {nodeinfo.get('name')} ({nodeinfo.get('location')})",
        f"Peers: {len(merged.get('Peers') or [])}",
        f"AdminListen: {merged.get('AdminListen')}",
        f"IfName: {merged.get('IfName')}",
        f"Listen: {listen_text}",
    ]
    text = "\n".join(lines)
    blob = json.dumps(merged)
    private = merged.get("PrivateKey")
    if private and private in text:
        raise ConfigError("summary leaked the private key")
    if private and private in blob and private in text:
        raise ConfigError("summary leaked the private key")
    return text


def write_config(merged: dict, dest: Path) -> None:
    payload = json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=dest.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        os.write(fd, payload.encode("utf-8"))
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, dest)
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path.exists():
            tmp_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="JSON from genconf or normaliseconf")
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--peers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--admin-listen",
        help="Platform override for AdminListen (Windows uses tcp://localhost:9001)",
    )
    parser.add_argument(
        "--if-name",
        help="Platform override for IfName (Windows uses Yggdrasil)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dest = resolve_output(args.output, args.repo_root)
        overlay = load_json(args.overlay)
        check_overlay(overlay, args.overlay)
        if args.admin_listen:
            overlay["AdminListen"] = args.admin_listen
        if args.if_name:
            overlay["IfName"] = args.if_name
        base = load_json(args.base)
        peers = load_peers(args.peers)
        merged = merge(base, overlay, peers)
        write_config(merged, dest)
        print(summary(merged))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
