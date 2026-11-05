"""#791 assembled CLI boundary: hosted outcome must reach #789 publisher."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class AssembledPublisherWiringTests(unittest.TestCase):
  def test_numbered_hosted_cli_publishes_exact_completed_outcome(self):
    specification = importlib.util.spec_from_file_location(
      "rwf_issue791_entry", ROOT / "repo_workflow.py",
    )
    assert specification is not None and specification.loader is not None
    entry = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(entry)
    outcome = types.SimpleNamespace(exit_code=9, request_sha="request",
                                    source_sha="source", retry=0)
    published = []

    def invoke(root, argv, executor, *, publish=None):
      self.assertEqual(argv, ["test", "RED", "--remote", "0"])
      self.assertIsNotNone(publish, "hosted result publisher not connected")
      publish(outcome)
      return outcome

    with (
      patch.object(entry, "_public_route",
                   return_value=("public", ROOT, ["test", "RED", "--remote", "0"], False)),
      patch.object(entry, "invoke_numbered", side_effect=invoke),
      patch.object(entry, "publish_result",
                   side_effect=lambda root, value: published.append((root, value))),
      patch.object(entry, "emit_outcome"),
    ):
      status = entry.main(["test", "RED", "--remote", "0"])
    self.assertEqual(status, 9)
    self.assertEqual(published, [(ROOT, outcome)])


if __name__ == "__main__":
  unittest.main()
