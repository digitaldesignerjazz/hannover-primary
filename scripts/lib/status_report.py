#!/usr/bin/env python3
"""Format yggdrasilctl getSelf/getPeers JSON into a health report.

Exit status:
  0  node is up and at least one peer is connected
  1  node is down, or getSelf did not return a usable identity
  2  node is up but no peer is connected
"""

from __future__ import annotations

import argparse
import json
import sys


def _loads(text: str, label: str) -> dict | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def format_rtt(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return f"{float(value) / 1_000_000:.2f} ms"


def report(self_text: str, peers_text: str) -> tuple[int, str]:
    self_doc = _loads(self_text, "getSelf")
    if not self_doc or not self_doc.get("address") or not self_doc.get("subnet") or not self_doc.get("key"):
        detail = " ".join(self_text.strip().split())
        if len(detail) > 300:
            detail = detail[:300] + "..."
        extra = f"\n{detail}" if detail else ""
        return 1, "Status: down\nDer Knoten antwortet nicht auf dem Admin-Socket." + extra

    lines = [
        "Status: aktiv",
        f"IPv6-Adresse: {self_doc['address']}",
        f"IPv6-Subnetz: {self_doc['subnet']}",
        f"Öffentlicher Schlüssel: {self_doc['key']}",
    ]
    build = " ".join(
        part
        for part in (str(self_doc.get("build_name") or ""), str(self_doc.get("build_version") or ""))
        if part
    )
    if build:
        lines.append(f"Build: {build}")

    peers_doc = _loads(peers_text, "getPeers")
    if peers_doc is None or not isinstance(peers_doc.get("peers"), list):
        lines[0] = "Status: aktiv, Peer-Liste nicht lesbar"
        lines.append("getPeers lieferte kein JSON. Exit 2.")
        return 2, "\n".join(lines)

    connected = [peer for peer in peers_doc["peers"] if isinstance(peer, dict) and peer.get("up")]
    lines.append(f"Verbundene Peers ({len(connected)}):")
    if not connected:
        lines[0] = "Status: aktiv, aber kein Peer verbunden"
        lines.append("  (keine)")
        return 2, "\n".join(lines)

    for peer in connected:
        uri = str(peer.get("remote") or peer.get("key") or "?")
        address = str(peer.get("address") or "")
        rtt = format_rtt(peer.get("latency"))
        bits = [uri]
        if address:
            bits.append(address)
        if rtt:
            bits.append(rtt)
        lines.append("  - " + "  ".join(bits))
    return 0, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self", dest="self_path", required=True)
    parser.add_argument("--peers", dest="peers_path", required=True)
    args = parser.parse_args(argv)
    code, text = report(
        open(args.self_path, encoding="utf-8").read(),
        open(args.peers_path, encoding="utf-8").read(),
    )
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
