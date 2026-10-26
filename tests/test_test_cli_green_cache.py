"""GREEN evidence cache-contract tests extracted without loss of assertions.

Shares only the original temporary Git fixture helpers. Separate discovery
retains all six negative/positive evidence cache cases.
"""
import json
import unittest

from tests import test_test_cli as fixture


class TestCliGreenCache(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def test_green_reuses_unchanged_pass_without_running_again(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 0, second.stderr)
    self.assertIn("Reusing valid PASS evidence", second.stdout)
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    self.assertEqual(len(records), 3)
    self.assertFalse(records[-2]["groups"][0]["reused"])
    self.assertTrue(records[-1]["groups"][0]["reused"])

  def test_green_does_not_reuse_pass_after_uncommitted_test_change(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    before = self.git("rev-parse", "HEAD")
    (self.root / "smoke_case.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(False)\n"
    )
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 1, second.stderr)
    self.assertNotIn("Reusing valid PASS evidence", second.stdout)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual(records[-1]["result"], "failed")
    self.assertFalse(records[-1]["groups"][0]["reused"])
    self.assertFalse(records[-1]["reusable"])
    self.assertIn("smoke_case.py", records[-1]["uncommittedChanges"])

  def test_passing_dirty_local_evidence_is_recorded_but_never_reused(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    source = self.root / "smoke_case.py"
    original = source.read_text()
    source.write_text(original + "# uncommitted local change\n")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    first_record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(first_record["result"], "succeeded")
    self.assertFalse(first_record["reusable"])
    self.assertIn("smoke_case.py", first_record["uncommittedChanges"])
    source.write_text(original)
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 0, second.stderr)
    self.assertNotIn("Reusing valid PASS evidence", second.stdout)
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    self.assertEqual(records[-1]["uncommittedChanges"], [])
    self.assertTrue(records[-1]["reusable"])
    third = self.cli("test", "GREEN")
    self.assertEqual(third.returncode, 0, third.stderr)
    self.assertIn("Reusing valid PASS evidence", third.stdout)

  def test_green_changed_catalogue_or_candidate_reexecutes(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    manifest = self.root / ".ci/tests.json"
    manifest.write_text(manifest.read_text() + " ")
    changed = self.cli("test", "GREEN")
    self.assertEqual(changed.returncode, 0, changed.stderr)
    self.assertNotIn("Reusing valid PASS evidence", changed.stdout)
    manifest.write_text(manifest.read_text().rstrip())
    (self.root / "README").write_text("changed source\n")
    self.git("add", "README")
    self.git("commit", "-m", "change candidate")
    changed_sha = self.cli("test", "GREEN")
    self.assertEqual(changed_sha.returncode, 0, changed_sha.stderr)
    self.assertNotIn("Reusing valid PASS evidence", changed_sha.stdout)

  def test_green_rejects_foreign_runner_and_platform_cache(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    baseline = json.loads(audit.read_text().splitlines()[-1])
    for field, value in (
      ("runner", "unverified-external"),
      ("platform", {"os": "wrong-os", "runtime": "0.0"}),
    ):
      with self.subTest(field=field):
        record = dict(baseline)
        record[field] = value
        audit.write_text(json.dumps(record) + "\n")
        run = self.cli("test", "GREEN")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Reusing valid PASS evidence", run.stdout)
        actual = json.loads(audit.read_text().splitlines()[-1])
        self.assertFalse(actual["groups"][0]["reused"])

  def test_green_reexecutes_after_failed_or_corrupted_cache(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    valid = json.loads(audit.read_text().splitlines()[-1])
    valid["result"] = "failed"
    audit.write_text(json.dumps(valid) + "\n")
    failed = self.cli("test", "GREEN")
    self.assertEqual(failed.returncode, 0, failed.stderr)
    self.assertNotIn("Reusing valid PASS evidence", failed.stdout)
    audit.write_text("{not JSON}\n")
    corrupt = self.cli("test", "GREEN")
    self.assertEqual(corrupt.returncode, 0, corrupt.stderr)
    self.assertNotIn("Reusing valid PASS evidence", corrupt.stdout)

if __name__ == "__main__":
  unittest.main()
