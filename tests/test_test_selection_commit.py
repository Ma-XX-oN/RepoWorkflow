"""Require a committed single RED/GREEN selection for execution."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "repo_workflow.py"


class SelectionCommitContract(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.git("init", "-qb", "issue-545-selection")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    tests = self.root / ".ci/tests.json"
    tests.parent.mkdir()
    tests.write_text(json.dumps({
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        "issue-545-one": {"type": "regression", "name": "smoke"},
        "issue-545-two": {"type": "regression", "name": "smoke"},
      }],
    }))
    (self.root / "smoke.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_ok(self): self.assertTrue(True)\n"
    )
    self.git("add", ".ci/tests.json", "smoke.py")
    self.git("commit", "-qm", "registered tests")
    self.selection = self.root / ".ci/red-green.txt"

  def git(self, *args):
    return subprocess.run(
      ["git", "-C", str(self.root), *args],
      check=True, capture_output=True, text=True,
    ).stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(self.root), "test", *args],
      text=True, capture_output=True, check=False,
    )

  def test_green_refuses_untracked_selection_file(self):
    self.selection.write_text("issue-545-one\n")
    result = self.cli("GREEN")
    self.assertEqual(result.returncode, 2)
    self.assertIn("committed", result.stderr)
    self.assertFalse(
      (self.root / ".repoworkflow/validation/testResults-545.jsonl").exists()
    )

  def test_green_refuses_modified_tracked_selection(self):
    self.selection.write_text("issue-545-one\n")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-qm", "selected first")
    self.selection.write_text("issue-545-two\n")
    result = self.cli("GREEN")
    self.assertEqual(result.returncode, 2)
    self.assertIn("committed", result.stderr)
    self.assertFalse(
      (self.root / ".repoworkflow/validation/testResults-545.jsonl").exists()
    )

  def test_red_explicit_same_untracked_selection_commits(self):
    self.selection.write_text("issue-545-one\n")
    self.cli("RED", "issue-545-one")
    self.assertEqual(
      self.git("show", "HEAD:.ci/red-green.txt"), "issue-545-one"
    )
    self.assertEqual(
      self.git("status", "--porcelain", "--", ".ci/red-green.txt"), ""
    )


if __name__ == "__main__":
  unittest.main()
