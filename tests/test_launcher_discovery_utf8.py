"""Portable strict Git discovery decoding and executable launcher identity."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.git import GitError
from repo_workflow.launcher_discovery import (
  LauncherDiscoveryError,
  _run_git,
  discover_repository_launcher,
)


class LauncherDiscoveryUtf8Tests(unittest.TestCase):
  def test_valid_utf8_output_from_git(self):
    raw = "/tmp/É 空 repo\n".encode("utf-8")
    result = subprocess.CompletedProcess(["git"], 0, raw, b"")
    with patch("repo_workflow.launcher_discovery.git_bytes",
               return_value=result) as runner:
      self.assertEqual(_run_git(Path("."), "rev-parse", "--show-toplevel").stdout,
                       "/tmp/É 空 repo\n")
    runner.assert_called_once_with(Path("."), "rev-parse",
                                   "--show-toplevel", check=False)

  def test_invalid_utf8_output_fails_closed(self):
    for stdout, stderr in ((b"bad-\xff", b""), (b"", b"bad-\xff")):
      with self.subTest(stdout=stdout):
        result = subprocess.CompletedProcess(["git"], 0, stdout, stderr)
        with patch("repo_workflow.launcher_discovery.git_bytes",
                   return_value=result):
          with self.assertRaisesRegex(LauncherDiscoveryError, "invalid Git launcher"):
            _run_git(Path("."), "rev-parse", "--show-toplevel")

  def test_git_execution_error_fails_closed(self):
    with patch("repo_workflow.launcher_discovery.git_bytes",
               side_effect=GitError("no Git")):
      with self.assertRaisesRegex(LauncherDiscoveryError, "invalid Git launcher"):
        _run_git(Path("."), "rev-parse", "--show-toplevel")

  def test_real_git_unicode_repository_root(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "É 空 workspace"
      root.mkdir()
      subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root,
                     check=True, capture_output=True)
      (root / "rwf").write_text("#!/bin/sh\n", encoding="utf-8")
      (root / "repo_workflow.py").write_text("# CLI\n", encoding="utf-8")
      resolved = discover_repository_launcher(root)
      self.assertTrue(resolved.repository_root.samefile(root))
      self.assertEqual(resolved.launcher, resolved.repository_root / "rwf")
      self.assertFalse(resolved.requires_python)


if __name__ == "__main__":
  unittest.main()
