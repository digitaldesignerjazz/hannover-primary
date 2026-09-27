#!/usr/bin/env python3
"""Unit tests for overlay merge, peer selection, and the health report."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import merge_config  # noqa: E402
import peers  # noqa: E402
import status_report  # noqa: E402


def private_key() -> str:
    return "ab" * 64


class MergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.overlay = json.loads((ROOT / "config" / "overlay.json").read_text(encoding="utf-8"))
        self.peers = peers.load_peer_file(ROOT / "config" / "peers.txt")
        self.base = {
            "PrivateKey": private_key(),
            "Peers": ["tcp://old.example:1"],
            "InterfacePeers": {},
            "Listen": ["tcp://[::]:1"],
            "AllowedPublicKeys": ["ff"],
            "GroupPassword": "",
            "IfName": "auto",
            "IfMTU": 1280,
            "NodeInfoPrivacy": True,
            "NodeInfo": None,
            "MulticastInterfaces": [],
        }

    def test_committed_overlay_and_peers(self) -> None:
        merge_config.check_overlay(self.overlay, ROOT / "config" / "overlay.json")
        self.assertGreaterEqual(len(self.peers), 1)
        self.assertTrue(all(item.startswith("tls://") for item in self.peers))
        self.assertLessEqual(len(self.peers), 4)

    def test_preserves_private_key_and_applies_overlay(self) -> None:
        merged = merge_config.merge(self.base, self.overlay, self.peers)
        self.assertEqual(merged["PrivateKey"], private_key())
        self.assertEqual(merged["NodeInfo"]["name"], "hannover-primary")
        self.assertEqual(merged["NodeInfo"]["location"], "Hannover/DE")
        self.assertEqual(merged["Peers"], self.peers)
        self.assertEqual(merged["IfName"], "ygg0")
        self.assertEqual(merged["Listen"], [])
        self.assertNotIn(private_key(), merge_config.summary(merged))

    def test_private_key_path_wins(self) -> None:
        self.base["PrivateKeyPath"] = "/etc/yggdrasil/private.key"
        merged = merge_config.merge(self.base, self.overlay, self.peers)
        self.assertEqual(merged["PrivateKeyPath"], "/etc/yggdrasil/private.key")
        self.assertNotIn("PrivateKey", merged)

    def test_overlay_rejects_secrets(self) -> None:
        bad = dict(self.overlay)
        bad["PrivateKey"] = private_key()
        with self.assertRaises(merge_config.ConfigError):
            merge_config.check_overlay(bad, Path("overlay.json"))

    def test_refuses_repo_and_symlink(self) -> None:
        with self.assertRaises(merge_config.ConfigError):
            merge_config.resolve_output(ROOT / "yggdrasil.conf", ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link.conf"
            link.symlink_to(ROOT / "yggdrasil.conf")
            with self.assertRaises(merge_config.ConfigError):
                merge_config.resolve_output(link, ROOT)
            dest = Path(tmp) / "yggdrasil.conf"
            merge_config.write_config(
                merge_config.merge(self.base, self.overlay, self.peers),
                dest,
            )
            saved = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(saved["PrivateKey"], private_key())
            self.assertNotIn(private_key(), (ROOT / "config" / "overlay.json").read_text(encoding="utf-8"))


class PeerTests(unittest.TestCase):
    def test_parser_and_selection_prefer_pinned_tls_nearby(self) -> None:
        text = (ROOT / "tests" / "fixtures" / "peers-sample.md").read_text(encoding="utf-8")
        germany = peers.parse_markdown(text, "de")
        netherlands = [
            peers.Candidate("nl", "tls://near.example:443?key=" + ("b" * 64)),
            peers.Candidate("fr", "tls://far.example:443"),
        ]
        chosen = peers.select_peers(germany + netherlands, limit=2)
        self.assertEqual(chosen[0].uri, "tls://beta.example:1338?key=" + ("a" * 64))
        self.assertEqual(chosen[1].country, "de")
        self.assertTrue(chosen[1].uri.startswith("tls://alpha.example"))

    def test_residential_blurb_ranks_after_datacenter(self) -> None:
        text = "\n".join(
            [
                "* Home link, residential",
                "  * `tls://home.example:443`",
                "* Frankfurt datacenter",
                "  * `tls://dc.example:443`",
            ]
        )
        chosen = peers.select_peers(peers.parse_markdown(text, "de"), limit=1)
        self.assertEqual(chosen[0].host, "dc.example")
        parsed = peers.parse_markdown(text, "de")
        self.assertTrue(any(item.residential for item in parsed))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.txt"
            path.write_text(peers.render_candidates(parsed), encoding="utf-8")
            again = peers.parse_candidates(path)
        self.assertEqual([item.residential for item in again], [item.residential for item in parsed])

    def test_invalid_peer_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "peers.txt"
            path.write_text("http://nope\n", encoding="utf-8")
            with self.assertRaises(peers.PeerError):
                peers.load_peer_file(path)


class StatusTests(unittest.TestCase):
    def test_down_when_ctl_fails(self) -> None:
        code, text = status_report.report("Fatal error: dial unix", "")
        self.assertEqual(code, 1)
        self.assertIn("down", text)

    def test_degraded_without_peers(self) -> None:
        self_doc = {
            "address": "200::1",
            "subnet": "300::/64",
            "key": "cd" * 32,
            "build_name": "yggdrasil",
            "build_version": "0.5.14",
        }
        code, text = status_report.report(
            json.dumps(self_doc),
            json.dumps({"peers": [{"remote": "tls://peer", "up": False, "address": "200::2"}]}),
        )
        self.assertEqual(code, 2)
        self.assertIn("200::1", text)
        self.assertIn("300::/64", text)
        self.assertIn("cd" * 32, text)

    def test_healthy_peer_rtt(self) -> None:
        self_doc = {"address": "200::1", "subnet": "300::/64", "key": "cd" * 32}
        peers_doc = {
            "peers": [
                {
                    "remote": "tls://peer.example:443",
                    "up": True,
                    "address": "200::2",
                    "latency": 12_000_000,
                }
            ]
        }
        code, text = status_report.report(json.dumps(self_doc), json.dumps(peers_doc))
        self.assertEqual(code, 0)
        self.assertIn("tls://peer.example:443", text)
        self.assertIn("12.00 ms", text)


class WindowsHelperTests(unittest.TestCase):
    def test_script_mentions_platform_overrides_and_secret_guard(self) -> None:
        text = (ROOT / "windows" / "Install-YggdrasilNode.ps1").read_text(encoding="utf-8")
        self.assertIn("tcp://localhost:9001", text)
        self.assertIn("Yggdrasil", text)
        self.assertIn("ProgramData", text)
        self.assertIn("overlay.json", text)
        self.assertIn("peers.txt", text)
        self.assertIn("Refusing to write node secrets", text)
        self.assertIn("yggdrasil-", text)


if __name__ == "__main__":
    unittest.main()
