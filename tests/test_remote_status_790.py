"""#790: status selection, pending, completion and provider failure tests."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.remote_result import PublishedResult
from repo_workflow.remote_status import (
  PENDING_EXIT, CommandStatus, RemoteStatusError,
  parse_intervals, remote_status, resolve_command, command_status,
)


def git(root, *args):
  completed = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, check=True,
  )
  return completed.stdout.decode("utf-8", "strict").strip()


class StatusTest(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    git(self.root, "init", "--bare", str(self.root / "remote.git"))
    git(self.root, "init", "-b", "issue-790")
    git(self.root, "config", "user.name", "tester")
    git(self.root, "config", "user.email", "tester@example.invalid")
    git(self.root, "remote", "add", "origin", str(self.root / "remote.git"))
    (self.root / "README").write_text("ok\n", encoding="utf-8")
    git(self.root, "add", "README")
    git(self.root, "commit", "-m", "source")

  def add_cmd(self, number):
    branch = f"CMD-{number}-issue-790"
    git(self.root, "checkout", "-b", branch, "issue-790")
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/rwf").write_text(
      "test RED --remote 0\n", encoding="utf-8",
    )
    git(self.root, "add", ".ci/rwf")
    git(self.root, "commit", "-m", "request",
        "-m", f"RWF-Source: {git(self.root, 'rev-parse', 'issue-790')}")
    git(self.root, "push", "origin", branch)
    git(self.root, "checkout", "issue-790")
    return branch

  def test_default_explicit_and_negative_selection(self):
    self.add_cmd(2)
    self.add_cmd(7)
    self.assertEqual(resolve_command(self.root).number, 7)
    self.assertEqual(resolve_command(self.root, -1).number, 7)
    self.assertEqual(resolve_command(self.root, -2).number, 2)
    self.assertEqual(resolve_command(self.root, 2).number, 2)
    for value in (0, 1, 8, -3):
      with self.subTest(value=value), self.assertRaises(RemoteStatusError):
        resolve_command(self.root, value)

  def test_unobserved_is_pending_never_retry(self):
    self.add_cmd(1)
    with patch("repo_workflow.remote_status.ci_invocation_status",
               return_value={"state": "not-observed", "run_id": None}):
      with patch("repo_workflow.remote_status.read_result", return_value=None):
        with patch("repo_workflow.remote_status._marker",
                   return_value=("a" * 40, 0)):
          with patch("repo_workflow.remote_status._tip_unchanged"):
            self.assertEqual(command_status(
              self.root, info_config={"infoCommand": ["fake"]},
            ).state, "not-observed")

  def test_completed_code_and_output_preserved(self):
    result = PublishedResult("CMD-1-issue-790", "a" * 40,
                             0, 75, "λ failed\n", "b" * 40)
    status = CommandStatus(1, result.branch, result.request_sha,
                           0, "completed", result, None)
    with patch("repo_workflow.remote_status.command_status",
               return_value=status):
      self.assertEqual(remote_status(self.root), 75)

  def test_poll_repeats_last_interval_and_never_submits(self):
    pending = CommandStatus(1, "CMD-1-issue-790", "a" * 40,
                            0, "running", None, 123)
    done = replace(pending, state="completed",
                   result=PublishedResult(
                     pending.branch, pending.request_sha, 0,
                     9, "failed\n", "b" * 40,
                   ))
    sleeps = []
    with patch("repo_workflow.remote_status.command_status",
               side_effect=[pending, pending, pending, done]):
      self.assertEqual(remote_status(
        self.root, intervals=(0.0, 0.1), sleep=sleeps.append,
      ), 9)
    self.assertEqual(sleeps, [0.0, 0.1, 0.1])

  def test_poll_intervals_reject_malformed(self):
    self.assertEqual(parse_intervals([]), (15.0,))
    self.assertIsNone(parse_intervals(None))
    for values in (["-1"], ["nan"], ["inf"], ["1e3"],
                   ["86401"], ["+1"], ["1", "bad"]):
      with self.subTest(values=values), self.assertRaises(RemoteStatusError):
        parse_intervals(values)

  def test_provider_errors_fail_closed(self):
    self.add_cmd(1)
    with patch("repo_workflow.remote_status.read_result", return_value=None):
      with patch("repo_workflow.remote_status._marker",
                 return_value=("a" * 40, 0)):
        with patch("repo_workflow.remote_status.ci_invocation_status",
                   side_effect=Exception("provider unavailable")):
          with self.assertRaises(Exception):
            command_status(
              self.root, info_config={"infoCommand": ["fake"]},
            )


if __name__ == "__main__":
  unittest.main()
