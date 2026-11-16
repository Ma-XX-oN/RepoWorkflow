"""Controller #699: manual declarations never enter automatic Self CI."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.self_ci import (
  SelfCiError, group_command, issue_verification_groups,
)


class ManualSelfCiTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / ".ci").mkdir()
    self.payload = {
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        "issue-699-regression": {
          "type": "regression",
          "name": "tests.test_self_ci_tiers",
        },
        "issue-699-manual--inspect": {
          "type": "manual",
          "instructions": "Inspect the integrated candidate.",
          "expected_result": "UI and candidate identity match.",
        },
        "integration-self-ci": {
          "type": "integration",
          "name": "tests.test_self_ci",
        },
      }],
    }

  def catalogue(self):
    (self.root / ".ci" / "tests.json").write_text(
      json.dumps(self.payload), encoding="utf-8",
    )

  def select(self):
    with patch("repo_workflow.self_ci.LifecycleStore") as lifecycle:
      lifecycle.return_value.read.return_value.lifecycle.high_risk_aliases = ()
      return issue_verification_groups(self.root, "699")

  def test_manual_case_and_integration_group_excluded_from_issue_verification(self):
    self.catalogue()
    self.assertEqual(
      self.select(), ("issue-699-regression",),
    )
    with self.assertRaisesRegex(SelfCiError, "native test name"):
      group_command(self.root, "issue-699-manual--inspect")

  def test_manual_only_never_becomes_an_auto_pass(self):
    del self.payload["tests"][0]["issue-699-regression"]
    self.catalogue()
    with self.assertRaisesRegex(SelfCiError, "no verification group"):
      self.select()

  def test_invalid_manual_metadata_is_not_ignored(self):
    self.payload["tests"][0]["issue-699-manual--inspect"].pop("type")
    self.catalogue()
    with self.assertRaisesRegex(SelfCiError, "manual test catalogue invalid"):
      self.select()


if __name__ == "__main__":
  unittest.main()
