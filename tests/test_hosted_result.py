"""Black-box hosted result identity and completeness contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-hosted-result.py"
SHA = "a" * 40


class HostedResultTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    self.log = (
      self.root / ".repoworkflow" / "validation" / "testResults-541.jsonl"
    )
    self.log.parent.mkdir(parents=True)
    self.select = self.root / ".ci" / "red-green.txt"
    self.select.parent.mkdir()

  def tearDown(self):
    self.tmp.cleanup()

  def invoke(self, stage="GREEN-testing", sha=SHA, branch="issue-541-test"):
    return subprocess.run(
      [sys.executable, str(SCRIPT), stage, sha, branch],
      cwd=self.root, text=True, capture_output=True, check=False,
    )

  def write(self, **fields):
    record = {
      "testSHA": SHA, "kind": "GREEN", "result": "succeeded",
      "reusable": True, "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "groups": [{"group": "issue-541-unit", "exit_code": 0}],
    }
    record.update(fields)
    self.log.write_text(json.dumps(record) + "\n")

  def test_matching_green_succeeds(self):
    self.select.write_text("issue-541-unit\n")
    self.write()
    result = self.invoke()
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_missing_or_malformed_record_fails(self):
    self.assertNotEqual(self.invoke().returncode, 0)
    self.log.write_text("{malformed")
    self.assertNotEqual(self.invoke().returncode, 0)

  def test_skip_failure_wrong_candidate_and_wrong_kind_fail(self):
    self.select.write_text("issue-541-unit\n")
    for field, value in (
      ("result", "SKIPPED"), ("result", "failed"),
      ("result", "incomplete"), ("testSHA", "b" * 40),
      ("kind", "temporary"), ("reusable", False),
      ("uncommittedChanges", ["changed.py"]),
      ("headChangedDuringTest", True),
      ("groups", []),
      ("groups", [{"group": "issue-541-unit", "exit_code": 1}]),
      ("groups", [{"group": "issue-541-other", "exit_code": 0}]),
    ):
      with self.subTest(field=field, value=value):
        self.write(**{field: value})
        self.assertNotEqual(self.invoke().returncode, 0)

  def test_missing_freshness_fields_fail_closed(self):
    self.select.write_text("issue-541-unit\n")
    for missing in ("uncommittedChanges", "headChangedDuringTest", "reusable"):
      with self.subTest(missing=missing):
        self.write()
        record = json.loads(self.log.read_text())
        del record[missing]
        self.log.write_text(json.dumps(record) + "\n")
        self.assertNotEqual(self.invoke().returncode, 0)

  def test_non_integer_group_exit_codes_fail_closed(self):
    self.select.write_text("issue-541-unit\n")
    for invalid in (False, 0.0, "0", None):
      with self.subTest(exit_code=invalid):
        self.write(groups=[{"group": "issue-541-unit", "exit_code": invalid}])
        self.assertNotEqual(self.invoke().returncode, 0)

  def test_latest_observation_controls_outcome(self):
    self.select.write_text("issue-541-unit\n")
    self.write()
    previous = self.log.read_text()
    self.write(result="SKIPPED")
    self.log.write_text(previous + self.log.read_text())
    self.assertNotEqual(self.invoke().returncode, 0)

  def test_invalid_stage_branch_sha_fail(self):
    self.select.write_text("issue-541-unit\n")
    self.write()
    for stage, sha, branch in (
      ("unknown", SHA, "issue-541-test"),
      ("GREEN-testing", "deadbeef", "issue-541-test"),
      ("GREEN-testing", SHA, "main"),
      ("GREEN-testing", SHA, "issue-542-other"),
    ):
      with self.subTest(stage=stage, sha=sha, branch=branch):
        self.assertNotEqual(
          self.invoke(stage, sha, branch).returncode, 0,
        )

  def test_regression_accepts_complete_result_without_groups(self):
    self.write(kind="regression", groups=[])
    self.assertEqual(
      self.invoke("regression-testing").returncode, 0,
    )


if __name__ == "__main__":
  unittest.main()
