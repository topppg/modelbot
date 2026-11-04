import unittest
from pathlib import Path
from unittest.mock import patch

from publish import publish


class PublishTests(unittest.TestCase):
    @patch("publish.run")
    @patch("publish.pulls", return_value=[{"state": "closed"}])
    def test_closed_candidate_is_not_reopened(self, pulls, run):
        publish("owner/project", "main", "modelbot/key/update", "org/model", Path("."), "success")
        pulls.assert_called_once_with(
            "owner/project", "-f", "state=all", "-f", "head=owner:modelbot/key/update", "-f", "base=main",
        )
        run.assert_not_called()

    @patch("publish.push")
    @patch("publish.run", side_effect=["original", "new refs/heads/main"])
    @patch("publish.pulls", return_value=[])
    def test_stale_plan_cannot_push(self, pulls, run, push):
        with self.assertRaisesRegex(ValueError, "default branch moved"):
            publish("owner/project", "main", "modelbot/key/update", "org/model", Path("."), "success")
        push.assert_not_called()
