#!/usr/bin/env python3
"""Read, refresh, and select public Yggdrasil peers.

Peer URIs are public. This module never writes a node private key.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

UPSTREAM = "https://raw.githubusercontent.com/yggdrasil-network/public-peers/master/"
PUBLIC_PEERS = "https://github.com/yggdrasil-network/public-peers"

# Germany first, then nearby EU. Codes match the upstream filenames.
NEARBY = (
    ("de", "europe/germany.md"),
    ("nl", "europe/netherlands.md"),
    ("at", "europe/austria.md"),
    ("cz", "europe/czechia.md"),
    ("lu", "europe/luxembourg.md"),
    ("pl", "europe/poland.md"),
    ("ch", "europe/switzerland.md"),
    ("fr", "europe/france.md"),
)

COUNTRY_RANK = {code: index for index, (code, _path) in enumerate(NEARBY)}
SCHEME_RANK = {"tls": 0, "quic": 1, "tcp": 2, "wss": 3, "ws": 4}
URI_RE = re.compile(r"`((?:tcp|tls|quic|ws|wss|socks|sockstls)://[^`\s]+)`")
PEER_URI = re.compile(r"^(tcp|tls|quic|ws|wss|socks|sockstls|unix)://\S+$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")


class PeerError(Exception):
    """The peer list cannot be parsed or selected."""


@dataclass(frozen=True)
class Candidate:
    country: str
    uri: str
    residential: bool = False

    @property
    def scheme(self) -> str:
        return self.uri.split("://", 1)[0]

    @property
    def pinned(self) -> bool:
        return "key=" in self.uri.split("?", 1)[-1] if "?" in self.uri else False

    @property
    def host(self) -> str:
        rest = self.uri.split("://", 1)[1]
        rest = rest.split("?", 1)[0]
        if rest.startswith("["):
            end = rest.find("]")
            return rest[1:end] if end > 1 else rest
        return rest.split("/", 1)[0].rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        rest = self.uri.split("://", 1)[1].split("?", 1)[0]
        if rest.startswith("["):
            end = rest.find("]")
            tail = rest[end + 1 :] if end >= 0 else ""
        else:
            tail = rest.split("/", 1)[0]
            if ":" not in tail:
                return 0
            tail = ":" + tail.rsplit(":", 1)[1]
        number = tail[1:] if tail.startswith(":") else ""
        number = number.split("/", 1)[0]
        return int(number) if number.isdigit() else 0

    @property
    def hostname(self) -> bool:
        host = self.host
        if ":" in host:
            return False
        parts = host.split(".")
        if len(parts) == 4 and all(part.isdigit() for part in parts):
            return False
        return bool(HOST_RE.match(host))

    def sort_key(self) -> tuple:
        return (
            COUNTRY_RANK.get(self.country, 99),
            SCHEME_RANK.get(self.scheme, 9),
            1 if self.residential else 0,
            0 if self.pinned else 1,
            0 if self.hostname else 1,
            0 if self.port == 443 else 1,
            self.host,
            self.uri,
        )


def parse_markdown(text: str, country: str) -> list[Candidate]:
    found: list[Candidate] = []
    seen: set[str] = set()
    blurb = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        uris = [match.strip() for match in URI_RE.findall(stripped)]
        if uris:
            residential = "residential" in blurb.lower()
            for uri in uris:
                if uri in seen or not PEER_URI.match(uri):
                    continue
                seen.add(uri)
                found.append(Candidate(country=country, uri=uri, residential=residential))
            continue
        if stripped.startswith("*") or stripped.startswith("#"):
            blurb = stripped
    return found


def load_peer_file(path: Path) -> list[str]:
    peers: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not PEER_URI.match(line):
            raise PeerError(f"{path}:{lineno}: invalid peer URI: {line}")
        if line not in peers:
            peers.append(line)
    return peers


def parse_candidates(path: Path) -> list[Candidate]:
    found: list[Candidate] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[1] in {"0", "1"} and PEER_URI.match(parts[2]):
            found.append(
                Candidate(country=parts[0], uri=parts[2], residential=parts[1] == "1")
            )
            continue
        if len(parts) == 2 and PEER_URI.match(parts[1]):
            found.append(Candidate(country=parts[0], uri=parts[1]))
            continue
        raise PeerError(f"{path}:{lineno}: expected '<country> <0|1> <uri>'")
    return found


def render_candidates(items: list[Candidate]) -> str:
    lines = [
        "# Public peer candidates. Not a node secret.",
        f"# Source: {PUBLIC_PEERS}",
        "# Format: <country> <residential 0|1> <uri>",
        "",
    ]
    for item in items:
        flag = "1" if item.residential else "0"
        lines.append(f"{item.country} {flag} {item.uri}")
    lines.append("")
    return "\n".join(lines)


def select_peers(items: list[Candidate], limit: int = 3) -> list[Candidate]:
    if limit < 1:
        raise PeerError("limit must be at least 1")
    ordered = sorted(items, key=lambda item: item.sort_key())
    chosen: list[Candidate] = []
    hosts: set[str] = set()
    for item in ordered:
        host_key = item.host.lower()
        if host_key in hosts:
            continue
        hosts.add(host_key)
        chosen.append(item)
        if len(chosen) >= limit:
            break
    if not chosen:
        raise PeerError("no peers matched the selection policy")
    return chosen


def render_peer_file(chosen: list[Candidate]) -> str:
    lines = [
        "# Active peers for hannover-primary.",
        "# One URI per line. Lines starting with # are comments.",
        f"# Source: {PUBLIC_PEERS}",
        "# Policy: TLS, Germany then nearby EU, skip residential blurbs, prefer ?key= and port 443.",
        "# Refresh: ./scripts/peers.sh refresh && ./scripts/peers.sh select --write",
        "# Apply:   sudo ./scripts/configure.sh",
        "",
    ]
    for item in chosen:
        lines.append(f"# {item.country} {item.scheme}")
        lines.append(item.uri)
        lines.append("")
    return "\n".join(lines)


def fetch_text(url: str, timeout: float = 30.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "hannover-primary-peers"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def refresh(dest: Path) -> list[Candidate]:
    items: list[Candidate] = []
    for country, rel in NEARBY:
        text = fetch_text(UPSTREAM + rel)
        items.extend(parse_markdown(text, country))
    if not items:
        raise PeerError("upstream peer lists did not contain any URIs")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_candidates(items), encoding="utf-8")
    return items


def repo_root_from(start: Path) -> Path:
    return start.resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("list", "check", "refresh", "select"),
    )
    parser.add_argument("--peers", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--repo-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = (args.repo_root or repo_root_from(Path(__file__))).resolve()
    peers_path = args.peers or (root / "config" / "peers.txt")
    candidates_path = args.candidates or (root / "config" / "peers.candidates.txt")
    try:
        if args.action == "list":
            for uri in load_peer_file(peers_path):
                print(uri)
            return 0
        if args.action == "check":
            uris = load_peer_file(peers_path)
            if not uris:
                raise PeerError(f"{peers_path} has no active peer URIs")
            print(f"{len(uris)} peers in {peers_path}")
            return 0
        if args.action == "refresh":
            items = refresh(candidates_path)
            print(f"{len(items)} candidates written to {candidates_path}")
            return 0
        if not candidates_path.is_file():
            raise PeerError(f"missing {candidates_path}; run: ./scripts/peers.sh refresh")
        chosen = select_peers(parse_candidates(candidates_path), limit=args.limit)
        if args.write:
            if root in peers_path.resolve().parents or peers_path.resolve() == root:
                peers_path.write_text(render_peer_file(chosen), encoding="utf-8")
            else:
                raise PeerError(f"refusing to write peers outside the repository: {peers_path}")
            print(f"wrote {len(chosen)} peers to {peers_path}")
        for item in chosen:
            print(f"{item.country} {item.uri}")
        return 0
    except PeerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
