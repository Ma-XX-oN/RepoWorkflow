"""Independent local stage cardinality and canonical-log acceptance tests.

Run against the real rwf launcher in disposable Git repositories. The tests
remain PENDING until the unified #545 source is in the assembled candidate.
No hosted job or protected target is mutated by these tests.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ("repo_workflow.py" if sys.platform == "win32" else "rwf")
CLI_COMMAND = ([sys.executable, str(CLI)] if sys.platform == "win32"
               else [str(CLI)])


class LocalStageCardinalityTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not CLI.is_file():
      raise unittest.SkipTest("PENDING #545: public launcher missing")
    help_result = subprocess.run(
      [*CLI_COMMAND, "test", "--help"], cwd=ROOT,
      capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=30, check=False,
    )
    if help_result.returncode or "temporary" not in help_result.stdout:
      raise unittest.SkipTest("PENDING #545: unified stages not in candidate")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name) / "work"
    self.root.mkdir()
    self.git("init", "-b", "issue-629-stage-fixture")
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "README").write_text("source\n")
    self.git("add", "README")
    self.git("commit", "-m", "source")
    self.candidate = self.git("rev-parse", "HEAD")

  def git(self, *args):
    return subprocess.run(
      ["git", "-C", str(self.root), *args],
      capture_output=True, text=True, encoding="utf-8", errors="strict", check=True, timeout=30,
    ).stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [*CLI_COMMAND, "--root", str(self.root), *args],
      cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=60, check=False,
    )

  def catalogue(self, names, *, temporary=False):
    tests = {
      "test-harnesses": {
        "unittest": {
          "command": "python", "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        **{name: {"type": "regression", "name": "smoke_case"}
           for name in names},
      }],
      "aliases": {},
    }
    (self.root / "smoke_case.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(True)\n"
    )
    name = ".ci/temp-tests.json" if temporary else ".ci/tests.json"
    file = self.root / name
    file.parent.mkdir(exist_ok=True)
    file.write_text(json.dumps(tests))
    self.git("add", name, "smoke_case.py")
    self.git("commit", "-m", "catalogue")
    return file

  def log(self):
    path = self.root / ".repoworkflow/validation/testResults-629.jsonl"
    if not path.exists():
      return []
    return [json.loads(line) for line in path.read_text().splitlines()]

  def test_empty_temporary_catalogue_fails_without_pass(self):
    self.catalogue([], temporary=True)
    result = self.cli("test", "temporary")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(any(row.get("result") == "succeeded" for row in self.log()))

  def test_one_temporary_group_runs_and_records_exact_source(self):
    self.catalogue(["issue-629-temp-one"], temporary=True)
    candidate = self.git("rev-parse", "HEAD")
    result = self.cli("test", "temporary")
    self.assertEqual(result.returncode, 0, result.stderr)
    record = self.log()[-1]
    self.assertEqual(record["testSHA"], candidate)
    self.assertEqual(record["kind"], "temporary")
    self.assertEqual(record["result"], "succeeded")
    self.assertEqual(
      [group["group"] for group in record["groups"]],
      ["issue-629-temp-one"],
    )

  def test_many_temporary_groups_execute_each_once(self):
    groups = ["issue-629-temp-a", "issue-629-temp-b"]
    self.catalogue(groups, temporary=True)
    result = self.cli("test", "temporary")
    self.assertEqual(result.returncode, 0, result.stderr)
    actual = [x["group"] for x in self.log()[-1]["groups"]]
    self.assertCountEqual(actual, groups)
    self.assertEqual(len(actual), 2)

  def test_invalid_temporary_manifest_rejects_execution(self):
    file = self.catalogue(["issue-629-temp-a"], temporary=True)
    file.write_text("{ invalid JSON")
    result = self.cli("test", "temporary")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(any(row.get("result") == "succeeded" for row in self.log()))

  def test_missing_local_results_refuses_synthetic_pass(self):
    result = self.cli("test", "results")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(result.stdout.strip().startswith('{"result": "succeeded"'))

  def test_one_real_local_record_returned_exactly(self):
    record = {
      "kind": "GREEN", "result": "succeeded", "runner": "local",
      "testSHA": self.candidate,
    }
    log = self.root / ".repoworkflow/validation/testResults-629.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(record) + "\n")
    result = self.cli("test", "results")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout), record)

  def test_malformed_following_record_cannot_return_partial_pass(self):
    record = {
      "kind": "GREEN", "result": "succeeded", "runner": "local",
      "testSHA": self.candidate,
    }
    log = self.root / ".repoworkflow/validation/testResults-629.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(record) + "\n{truncated")
    result = self.cli("test", "results")
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(result.stdout, "")

  def test_missing_green_selection_records_skipped_not_pass(self):
    self.catalogue(["issue-629-only"])
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    row = self.log()[-1]
    self.assertEqual(row["result"], "SKIPPED")
    self.assertEqual(row["groups"], [])
    self.assertNotEqual(row["result"], "succeeded")

  def test_one_of_many_green_groups_selected_only(self):
    groups = ["issue-629-a", "issue-629-b"]
    self.catalogue(groups)
    # A missing expected-RED declaration cannot produce RED PASS, but selection
    # itself is committed before that validation result.
    selected = self.cli("test", "RED", groups[1])
    self.assertNotEqual(selected.returncode, 0)
    self.assertEqual(
      (self.root / ".ci/red-green.txt").read_text(), groups[1] + "\n")
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    row = self.log()[-1]
    self.assertEqual(row["result"], "succeeded")
    self.assertEqual([g["group"] for g in row["groups"]], [groups[1]])

  def test_invalid_green_selection_fails_without_pass(self):
    self.catalogue(["issue-629-valid"])
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-629-valid\nissue-629-other\n")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "invalid multiple selection")
    result = self.cli("test", "GREEN")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(any(row.get("result") == "succeeded" for row in self.log()))

  def test_integration_refuses_unremoved_temporary_sandbox(self):
    self.catalogue(["issue-629-temp-a"], temporary=True)
    owned = self.root / ".ci/temp-tests/629"
    owned.mkdir(parents=True)
    (owned / "old-build.tmp").write_text("artifact")
    result = self.cli("test", "integration")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn(".ci/temp-tests/629", result.stdout + result.stderr)
    self.assertFalse(any(row.get("kind") == "integration"
                         and row.get("result") == "succeeded"
                         for row in self.log()))

  def test_missing_unconfigured_integration_adapter_cannot_pass(self):
    result = self.cli("test", "integration")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(any(row.get("kind") == "integration"
                         and row.get("result") == "succeeded"
                         for row in self.log()))


if __name__ == "__main__":
  unittest.main()
