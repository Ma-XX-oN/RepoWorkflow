"""Black-box cache eligibility invariants independent of CLI internals."""
import json
from pathlib import Path
import platform
import tempfile
import unittest

from repo_workflow.test_cache import reusable_local_group_passes


SHA = "a" * 40
FINGERPRINT = "b" * 64


class TestCacheEvidenceTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.path = Path(self.tmp.name) / "testResults-545.jsonl"
    self.base = {
      "kind": "GREEN", "testSHA": SHA,
      "catalogueSHA256": FINGERPRINT,
      "result": "succeeded", "reusable": True,
      "runner": "local",
      "uncommittedChanges": [], "headChangedDuringTest": False,
      "platform": {
        "os": platform.system(), "architecture": platform.machine(),
          "runtime": platform.python_version(),
      },
      "groups": [{"group": "issue-545-green", "exit_code": 0}],
    }

  def write(self, *records):
    self.path.write_text(
      "".join(json.dumps(x) + "\n" for x in records),
      encoding="utf-8",
    )

  def reusable(self):
    return reusable_local_group_passes(
      self.path, stage="GREEN", revision=SHA, fingerprint=FINGERPRINT,
    )

  def test_clean_exact_local_group_is_reusable(self):
    self.write(self.base)
    self.assertEqual(self.reusable(), {"issue-545-green"})

  def test_absent_and_invalid_file_fail_closed(self):
    self.assertEqual(self.reusable(), set())
    self.path.write_text("not JSON")
    self.assertEqual(self.reusable(), set())

  def test_dirty_mutated_and_unverified_hosted_results_are_not_reused(self):
    for change in (
      {"uncommittedChanges": ["file.py"]},
      {"headChangedDuringTest": True},
      {"uncommittedChanges": None},
      {"headChangedDuringTest": None},
      {"runner": "github-actions", "providerRunId": 123},
      {"runner": "unknown"},
      {"reusable": False},
      {"result": "failed"},
      {"result": "SKIPPED"},
    ):
      with self.subTest(change=change):
        self.write({**self.base, **change})
        self.assertEqual(self.reusable(), set())

  def test_different_candidate_catalogue_platform_or_stage_not_reused(self):
    for change in (
      {"testSHA": "c" * 40},
      {"catalogueSHA256": "d" * 64},
      {"kind": "RED"},
      {"platform": {"os": "not-the-current-platform"}},
      {"platform": {**self.base["platform"], "architecture": "wrong-arch"}},
    ):
      with self.subTest(change=change):
        self.write({**self.base, **change})
        self.assertEqual(self.reusable(), set())

  def test_hosted_pass_requires_real_provider_verification_callback(self):
    hosted = {
      **self.base, "runner": "github-actions",
      "providerRunId": 123, "providerStage": "GREEN-testing",
    }
    self.write(hosted)
    self.assertEqual(self.reusable(), set())
    from repo_workflow.test_cache import reusable_local_group_passes
    def check(accepted):
      return reusable_local_group_passes(
        self.path, stage="GREEN", revision=SHA, fingerprint=FINGERPRINT,
        verify_hosted=lambda record: (
          accepted and record.get("providerRunId") == 123
        ),
      )
    self.assertEqual(check(False), set())
    self.assertEqual(check(True), {"issue-545-green"})
    self.write({**hosted, "platform": {"os": "incompatible"}})
    self.assertEqual(check(True), set())

  def test_later_failure_supersedes_old_pass(self):
    self.write(self.base, {**self.base, "result": "failed"})
    self.assertEqual(self.reusable(), set())
    self.write(self.base, {**self.base, "result": "failed"}, self.base)
    self.assertEqual(self.reusable(), {"issue-545-green"})

  def test_empty_matching_observation_invalidates_earlier_pass(self):
    self.write(self.base, {
      **self.base, "result": "failed", "groups": [],
    })
    self.assertEqual(self.reusable(), set())

  def test_two_groups_later_partial_failure(self):
    groups = [
      {"group": "issue-545-one", "exit_code": 0},
      {"group": "issue-545-two", "exit_code": 0},
    ]
    self.write(
      {**self.base, "groups": groups},
      {**self.base, "result": "failed", "groups": [ {
        "group": "issue-545-two", "exit_code": 1,
      } ]},
    )
    self.assertEqual(self.reusable(), {"issue-545-one"})


if __name__ == "__main__":
  unittest.main()
