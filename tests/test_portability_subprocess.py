"""Strict subprocess and raw Git status regression tests."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from repo_workflow.test_results_reader import TestCommandError
from repo_workflow.test_worktree import tracked_input_changes
from repo_workflow.test_integration_engine import _probe


class PortabilitySubprocessTests(unittest.TestCase):
  def test_status_rejects_malformed_utf8_path(self):
    with patch("repo_workflow.test_worktree.git_bytes",
               return_value=SimpleNamespace(stdout=b"?? bad-\xff.txt\0")):
      with self.assertRaisesRegex(TestCommandError, "cannot inspect"):
        tracked_input_changes(Path("."), Path(".repoworkflow/evidence.jsonl"))

  def test_status_tracks_both_rename_paths(self):
    with patch("repo_workflow.test_worktree.git_bytes",
               return_value=SimpleNamespace(stdout=b"R  new.txt\0old.txt\0")):
      self.assertEqual(
        tracked_input_changes(Path("."), Path(".repoworkflow/evidence.jsonl")),
        ["new.txt", "old.txt"],
      )

  def test_status_rejects_unterminated_wire_record(self):
    with patch("repo_workflow.test_worktree.git_bytes",
               return_value=SimpleNamespace(stdout=b"?? truncated.txt")):
      with self.assertRaisesRegex(TestCommandError, "unterminated"):
        tracked_input_changes(Path("."), Path(".repoworkflow/evidence.jsonl"))

  def test_invalid_probe_output_is_not_a_pass(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      scripts = root / "scripts"
      scripts.mkdir()
      (scripts / "bad.py").write_text(
        "import sys\nsys.stdout.buffer.write(b'bad-\\xff')\n",
        encoding="utf-8",
      )
      diagnostic = io.StringIO()
      with contextlib.redirect_stderr(diagnostic):
        self.assertEqual(_probe(root, "bad.py"), 2)
      self.assertIn("cannot execute or decode", diagnostic.getvalue())


if __name__ == "__main__":
  unittest.main()
