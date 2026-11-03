"""#789: publication and readback against real bare Git repositories."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.remote_result import (
  RemoteResultError, publish_result, read_result,
)


@dataclass(frozen=True)
class Outcome:
  branch: str
  request_sha: str
  source_sha: str
  retry: int
  exit_code: int
  stdout: str
  stderr: str
  output: str


def git(root, *args):
  done = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, check=True,
  )
  return done.stdout.decode("utf-8").strip()


class ResultFixture(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    remote = self.root / "remote.git"
    git(self.root, "init", "--bare", str(remote))
    git(self.root, "init", "-b", "issue-789")
    git(self.root, "config", "user.name", "tester")
    git(self.root, "config", "user.email", "tester@example.invalid")
    git(self.root, "remote", "add", "origin", str(remote))
    (self.root / "README").write_text("hello\n", encoding="utf-8")
    git(self.root, "add", "README")
    git(self.root, "commit", "-m", "source")
    self.source = git(self.root, "rev-parse", "HEAD")
    self.branch = "CMD-1-issue-789"
    git(self.root, "push", "origin", "issue-789")
    git(self.root, "checkout", "-b", self.branch)
    self.marker(0)

  def marker(self, retry):
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/rwf").write_text(
      f"test RED --remote {retry}\n", encoding="utf-8",
    )
    git(self.root, "add", ".ci/rwf")
    git(self.root, "commit", "-m", "request", "-m",
        f"RWF-Source: {self.source}")
    self.request = git(self.root, "rev-parse", "HEAD")
    git(self.root, "push", "origin", self.branch)

  def outcome(self, status=0, output="ok λ\n"):
    return Outcome(self.branch, self.request, self.source, 0,
                   status, output, "", output)

  def test_success_durable_readback_and_source_unchanged(self):
    self.assertIsNone(read_result(self.root, self.branch))
    published = publish_result(self.root, self.outcome())
    self.assertEqual(read_result(self.root, self.branch), published)
    self.assertEqual(published.output, "ok λ\n")
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.request)
    self.assertEqual(git(self.root, "rev-parse", "issue-789"), self.source)

  def test_negative_exit_and_empty_output(self):
    publish_result(self.root, self.outcome(37, ""))
    result = read_result(self.root, self.branch)
    self.assertEqual((result.exit_code, result.output), (37, ""))

  def test_duplicate_result_rejected(self):
    publish_result(self.root, self.outcome())
    with self.assertRaises(RemoteResultError):
      publish_result(self.root, self.outcome())

  def test_stale_retry_pending_and_old_result_denied(self):
    old = self.outcome()
    publish_result(self.root, old)
    git(self.root, "fetch", "origin", self.branch)
    git(self.root, "reset", "--hard", "FETCH_HEAD")
    self.marker(1)
    self.assertIsNone(read_result(self.root, self.branch))
    with self.assertRaises(RemoteResultError):
      publish_result(self.root, old)

  def test_latest_retry_publishes_own_result(self):
    first = self.outcome()
    publish_result(self.root, first)
    git(self.root, "fetch", "origin", self.branch)
    git(self.root, "reset", "--hard", "FETCH_HEAD")
    self.marker(1)
    latest = replace(first, request_sha=self.request, retry=1,
                     exit_code=23, output="retry Δ\\n")
    published = publish_result(self.root, latest)
    self.assertEqual(read_result(self.root, self.branch), published)
    self.assertEqual((published.retry, published.exit_code), (1, 23))
    self.assertNotEqual(published.request_sha, first.request_sha)

  def test_forged_publication_rejected_by_readback(self):
    (self.root / ".repoworkflow").mkdir(exist_ok=True)
    (self.root / ".repoworkflow/result").write_text(
      "0\\nforged\\n", encoding="utf-8",
    )
    git(self.root, "add", ".repoworkflow/result")
    git(self.root, "commit", "-m", "forged without identity")
    git(self.root, "push", "origin", self.branch)
    with self.assertRaises(RemoteResultError):
      read_result(self.root, self.branch)

  def test_non_cmd_branch_denied(self):
    with self.assertRaises(RemoteResultError):
      publish_result(self.root, replace(
        self.outcome(), branch="issue-789",
      ))

  def test_unknown_cmd_denied(self):
    with self.assertRaises(RemoteResultError):
      read_result(self.root, "CMD-9-missing")

  def test_invalid_unicode_denied(self):
    with self.assertRaises(UnicodeEncodeError):
      publish_result(self.root, self.outcome(output="bad \ud800"))

  def test_competing_publishers_one_wins(self):
    with ThreadPoolExecutor(max_workers=2) as pool:
      tasks = [pool.submit(publish_result, self.root, self.outcome())
               for _ in range(2)]
      results = []
      for task in tasks:
        try:
          results.append(task.result())
        except RemoteResultError:
          results.append(None)
    self.assertEqual(sum(x is not None for x in results), 1)

  def test_concurrent_readers_observe_only_complete_result(self):
    with ThreadPoolExecutor(max_workers=4) as pool:
      initial = [pool.submit(read_result, self.root, self.branch)
                 for _ in range(4)]
      self.assertTrue(all(x.result() is None for x in initial))
      published = publish_result(self.root, self.outcome(13, "Δ\n"))
      subsequent = [pool.submit(read_result, self.root, self.branch)
                    for _ in range(4)]
      self.assertTrue(all(x.result() == published for x in subsequent))

  def test_interrupted_before_publication_is_pending(self):
    self.assertIsNone(read_result(self.root, self.branch))
    advertised = git(self.root, "ls-remote", "--heads", "origin",
                     f"refs/heads/{self.branch}")
    self.assertEqual(advertised.split()[0], self.request)

  def test_unauthorized_commit_is_not_result(self):
    (self.root / "extra").write_text("invalid\n", encoding="utf-8")
    git(self.root, "add", "extra")
    git(self.root, "commit", "-m", "invalid mutation")
    git(self.root, "push", "origin", self.branch)
    with self.assertRaises(RemoteResultError):
      publish_result(self.root, self.outcome())
    with self.assertRaises(RemoteResultError):
      read_result(self.root, self.branch)
