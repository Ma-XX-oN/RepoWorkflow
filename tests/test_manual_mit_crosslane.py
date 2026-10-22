"""Independent actual-A+B+C MIT CLI subprocess smoke tests (test-only assembly).

Local real engine in disposable git checkout, NOT authenticated GitHub MIT provider.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from repo_workflow.manual_test_cli import after_automatic_integration
from repo_workflow.manual_test_result import (
  ManualResultError, require_manual_completion,
)


SOURCE = Path(__file__).resolve().parents[1]


class ManualMitCrosslaneTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    base = Path(self.temporary.name)
    self.engine = base / "engine"
    self.engine.mkdir()
    for name in ("repo_workflow.py", "rwf"):
      shutil.copy2(SOURCE / name, self.engine / name)
    shutil.copytree(SOURCE / "repo_workflow", self.engine / "repo_workflow",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "scripts", self.engine / "scripts")
    self.consumer = base / "consumer"
    self.consumer.mkdir()
    self.git("init", "-b", "issue-703-negative-crosslane")
    self.git("config", "user.name", "MIT Certifier")
    self.git("config", "user.email", "certifier@example.invalid")
    (self.consumer / ".ci").mkdir()
    data = json.loads((SOURCE / ".ci" / "tests.json").read_text())
    harness = data["tests"][0]["test-harness"]
    for name in ("BRAVO", "ALPHA"):
      data["tests"].append({
        "test-harness": harness,
        "issue-703-manual--" + name: {
          "type": "manual",
          "instructions": "Perform independent " + name + " verification",
          "expected_result": name + " condition is observed",
        },
      })
    (self.consumer / ".ci" / "tests.json").write_text(json.dumps(data))
    (self.consumer / "README.md").write_text("initial tested source\n")
    self.git("add", ".")
    self.git("commit", "-m", "initial exact MIT candidate")
    self.sha = self.git("rev-parse", "HEAD")
    self.log = self.consumer / ".repoworkflow/validation/testResults-703.jsonl"
    self.selection = self.consumer / ".repoworkflow/manual/active-703.json"
    self.pending = self.consumer / ".repoworkflow/manual/pending-703.json"

  def tearDown(self):
    self.temporary.cleanup()

  def git(self, *args):
    result = subprocess.run(
      ["git", "-C", str(self.consumer), *args],
      capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()

  def cli(self, *args):
    env = {**os.environ,
           "RWF_WRITER_ID": "certifier-703",
           "RWF_SESSION_ID": "independent-local-probe"}
    return subprocess.run(
      ["sh", str(self.engine / "rwf"), "--root", str(self.consumer), *args],
      capture_output=True, text=True, env=env,
    )

  def events(self):
    if not self.log.exists():
      return []
    return [json.loads(row) for row in self.log.read_text().splitlines()]

  def test_real_cli_selects_first_then_next_after_only_one_pass(self):
    first = self.cli("test", "integration", "--manual")
    self.assertEqual(first.returncode, 0, first.stderr)
    self.assertIn("issue-703-manual--ALPHA", first.stdout)
    self.assertTrue(self.selection.exists())
    passed = self.cli("test", "succeeded")
    self.assertEqual(passed.returncode, 0, passed.stderr)
    self.assertFalse(self.selection.exists())
    records = self.events()
    self.assertEqual(len(records), 1)
    self.assertEqual(records[0]["manualCase"], "issue-703-manual--ALPHA")
    self.assertEqual(records[0]["result"], "succeeded")
    self.assertEqual(records[0]["testSHA"], self.sha)
    with self.assertRaises(ManualResultError):
      require_manual_completion(self.consumer, 703, self.sha)
    next_case = self.cli("test", "integration", "--manual")
    self.assertEqual(next_case.returncode, 0, next_case.stderr)
    self.assertIn("issue-703-manual--BRAVO", next_case.stdout)

  def test_real_cli_missing_and_foreign_selection_do_not_mutate(self):
    for command in (
      ("test", "succeeded"),
      ("test", "failed"),
      ("test", "integration", "issue-704-manual--ALPHA"),
    ):
      with self.subTest(command=command):
        response = self.cli(*command)
        self.assertNotEqual(response.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.selection.exists())
        self.assertFalse(self.pending.exists())

  def test_real_cli_source_change_rejects_old_selection(self):
    selected = self.cli("test", "integration", "--manual")
    self.assertEqual(selected.returncode, 0, selected.stderr)
    (self.consumer / "README.md").write_text("changed tested source\n")
    self.git("add", "README.md")
    self.git("commit", "-m", "new source candidate")
    result = self.cli("test", "succeeded")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(self.log.exists())

  def test_cli_readback_rejects_pending_unknown(self):
    result = self.cli("test", "integration", "--manual")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.pending.write_text(json.dumps({
      "schema": 1, "phase": "handoff",
      "event": {"manualCase": "issue-703-manual--ALPHA",
                "testSHA": self.sha, "result": "succeeded"},
    }))
    with self.assertRaisesRegex(ManualResultError, "UNKNOWN"):
      after_automatic_integration(self.consumer)

  def test_first_pass_then_second_fail_blocks_further_selection(self):
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    self.assertEqual(self.cli("test", "succeeded").returncode, 0)
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    failed = self.cli("test", "failed")
    self.assertNotEqual(failed.returncode, 0)
    records = self.events()
    self.assertEqual([x["result"] for x in records], ["succeeded", "failed"])
    self.assertTrue(all(x["testSHA"] == self.sha for x in records))
    self.assertTrue(self.pending.exists())
    with self.assertRaises(ManualResultError):
      require_manual_completion(self.consumer, 703, self.sha)
    retry = self.cli("test", "integration", "--manual")
    self.assertNotEqual(retry.returncode, 0)
    self.assertEqual(len(self.events()), 2)


if __name__ == "__main__":
  unittest.main()
