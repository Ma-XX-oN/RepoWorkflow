"""Real-Git filename preservation in local test evidence."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.test_cli import _uncommitted_inputs


class WorkingTreePathTests(unittest.TestCase):
  def test_staged_rename_records_both_exact_paths(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      def git(*args):
        return subprocess.run(
          ["git", "-C", str(root), *args],
          check=True, capture_output=True, text=True,
        ).stdout.strip()

      git("init", "-qb", "issue-545-rename")
      git("config", "user.name", "Fixture")
      git("config", "user.email", "fixture@example.invalid")
      (root / "source_old.py").write_text("old source\n")
      git("add", "source_old.py")
      git("commit", "-qm", "initial")
      git("mv", "source_old.py", "source_new.py")
      log = root / ".repoworkflow/validation/testResults-545.jsonl"
      self.assertEqual(
        _uncommitted_inputs(root, log),
        ["source_new.py", "source_old.py"],
      )


if __name__ == "__main__":
  unittest.main()
