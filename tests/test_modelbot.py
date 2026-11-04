import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from modelbot import HUB, Hub, read_config, sync_lock

REPO = "org/model"
SHA = "a" * 40


class HubTests(unittest.TestCase):
    def test_tree_is_pinned_and_paginated(self):
        hub = Hub()
        hub.get = Mock(side_effect=[
            ({"private": False, "gated": False, "sha": SHA,
              "cardData": {"license": "mit"}}, ""),
            ([{"type": "file", "path": "config.json", "oid": "b" * 40, "size": 1}],
             f'<{HUB}/api/models/{REPO}/tree/{SHA}?cursor=2>; rel="next"'),
            ([{"type": "file", "path": "model.safetensors", "oid": "c" * 40,
               "size": 2, "lfs": {"oid": "d" * 64}}], ""),
        ])
        snapshot = hub.snapshot(REPO, "release/stable")
        urls = [call.args[0] for call in hub.get.call_args_list]
        self.assertTrue(urls[0].endswith("/release%2Fstable"))
        self.assertTrue(all(f"/tree/{SHA}?" in url for url in urls[1:]))
        self.assertEqual(snapshot["license"], "mit")
        self.assertEqual(snapshot["files"]["config.json"]["digest"], "git-sha1:" + "b" * 40)
        self.assertEqual(snapshot["files"]["model.safetensors"]["digest"], "sha256:" + "d" * 64)

    def test_gated_model_is_rejected_before_reading_tree(self):
        hub = Hub()
        hub.get = Mock(return_value=({"private": False, "gated": "manual", "sha": SHA}, ""))
        with self.assertRaisesRegex(ValueError, "ungated"):
            hub.snapshot(REPO, "main")
        hub.get.assert_called_once()

    def test_foreign_pagination_origin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected"):
            Hub().get("https://huggingface.co.example/api/models")


class LockTests(unittest.TestCase):
    def test_sync_preserves_pinned_revisions_and_writes_deterministic_json(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "model.lock"
            hub = Mock()
            hub.snapshot.return_value = {
                "ref": "main", "revision": SHA, "license": None, "files": {},
            }
            sync_lock(lock, {REPO: "main"}, hub)
            first = lock.read_bytes()
            sync_lock(lock, {REPO: "main"}, hub)
            hub.snapshot.assert_called_once_with(REPO, "main")
            self.assertEqual(first, lock.read_bytes())
            self.assertEqual(json.loads(first)["models"][REPO]["revision"], SHA)

    def test_rejects_path_traversal_in_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "modelbot.toml"
            config.write_text('[models]\n"../model" = "main"\n')
            with self.assertRaisesRegex(ValueError, "invalid model"):
                read_config(config)
