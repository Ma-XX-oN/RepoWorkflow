"""Specification-derived canonical GREEN cache replay acceptance.

Tests the actual #548 source when assembled; does not clone implementation
logic into the test suite or call a forged provider.
"""

import json
from pathlib import Path
import platform
import tempfile
import unittest


try:
  from repo_workflow.test_cache import reusable_local_group_passes
except ImportError:
  reusable_local_group_passes = None


class CanonicalCacheAcceptanceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if reusable_local_group_passes is None:
      raise unittest.SkipTest("PENDING: #548 cache implementation not in candidate")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.log = Path(self.temp.name) / "testResults-629.jsonl"
    self.sha = "a" * 40
    self.fingerprint = "b" * 64
    self.group = "issue-629-probe"
    self.record = {
      "kind": "GREEN",
      "testSHA": self.sha,
      "catalogueSHA256": self.fingerprint,
      "result": "succeeded",
      "reusable": True,
      "runner": "local",
      "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "platform": {
        "os": platform.system(),
        "architecture": platform.machine(),
        "runtime": platform.python_version(),
      },
      "groups": [{"group": self.group, "exit_code": 0, "reused": False}],
    }

  def append(self, record):
    with self.log.open("a", encoding="utf-8") as out:
      out.write(json.dumps(record) + "\n")

  def reusable(self, **kw):
    return reusable_local_group_passes(
      self.log, stage=kw.get("stage", "GREEN"),
      revision=kw.get("revision", self.sha),
      fingerprint=kw.get("fingerprint", self.fingerprint),
    )

  def test_identical_complete_local_pass_is_eligible(self):
    self.append(self.record)
    self.assertEqual(self.reusable(), {self.group})

  def test_missing_evidence_cannot_pass(self):
    self.assertEqual(self.reusable(), set())

  def test_changed_sha_or_catalogue_rejects_old_pass(self):
    self.append(self.record)
    self.assertEqual(self.reusable(revision="c" * 40), set())
    self.assertEqual(self.reusable(fingerprint="d" * 64), set())

  def test_failed_or_incomplete_latest_outcome_cancels_pass(self):
    for outcome in ("failed", "incomplete"):
      with self.subTest(outcome=outcome):
        self.log.unlink(missing_ok=True)
        self.append(self.record)
        self.append({**self.record, "result": outcome})
        self.assertEqual(self.reusable(), set())

  def test_after_failure_new_exact_pass_restores_eligibility(self):
    self.append(self.record)
    self.append({**self.record, "result": "failed"})
    self.append(self.record)
    self.assertEqual(self.reusable(), {self.group})

  def test_foreign_runner_and_environment_are_not_reusable(self):
    for update in (
      {"runner": "github-actions"},
      {"platform": {"os": "unknown", "architecture": "x", "runtime": "0"}},
      {"uncommittedChanges": ["source.py"]},
      {"headChangedDuringTest": True},
      {"reusable": False},
    ):
      with self.subTest(update=update):
        self.log.write_text("")
        self.append({**self.record, **update})
        self.assertEqual(self.reusable(), set())

  def test_noninteger_exit_code_and_duplicate_groups_rejected(self):
    for groups in (
      [{"group": self.group, "exit_code": True}],
      [{"group": self.group, "exit_code": "0"}],
      [self.record["groups"][0], self.record["groups"][0]],
      [],
    ):
      with self.subTest(groups=groups):
        self.log.write_text("")
        self.append({**self.record, "groups": groups})
        self.assertEqual(self.reusable(), set())

  def test_corrupt_or_nonobject_record_cannot_grant_pass(self):
    for data in ("{corrupt\n", "[]\n", "null\n"):
      with self.subTest(data=data):
        self.log.write_text(data)
        self.assertEqual(self.reusable(), set())


if __name__ == "__main__":
  unittest.main()
