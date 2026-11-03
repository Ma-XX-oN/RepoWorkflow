"""Issue #787 Git request transport tests using real local Git histories."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from repo_workflow.remote_request import (
  RemoteRequestError, retry_request, submit_request, submit_unpolled,
)


def git(root, *args):
  result = subprocess.run(
    ["git", *args], cwd=root, text=True, capture_output=True, check=False,
  )
  if result.returncode:
    raise AssertionError(result.stderr)
  return result.stdout.strip()


class CMDSubmissionTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    base = Path(self.temp.name)
    self.remote = base / "remote.git"
    self.source = base / "source"
    git(base, "init", "--bare", str(self.remote))
    git(base, "init", "-b", "feature-test", str(self.source))
    git(self.source, "config", "user.email", "test@example.invalid")
    git(self.source, "config", "user.name", "Fixture")
    (self.source / "file.txt").write_text("source\n")
    git(self.source, "add", "file.txt")
    git(self.source, "commit", "-m", "source")
    git(self.source, "remote", "add", "origin", str(self.remote))
    git(self.source, "push", "origin", "HEAD")

  def submit(self, argv=None, root=None):
    return submit_request(
      root or self.source, argv or ["test", "RED", "--remote"],
    )

  def test_source_fork_marker_and_idempotency(self):
    original = git(self.source, "rev-parse", "HEAD")
    first = self.submit()
    self.assertEqual(1, first.number)
    self.assertFalse(first.reused)
    again = self.submit()
    self.assertTrue(again.reused)
    self.assertEqual(first.request_sha, again.request_sha)
    self.assertEqual(original, git(self.source, "rev-parse", "HEAD"))
    git(self.source, "fetch", "origin", first.branch)
    self.assertEqual(original, git(self.source, "rev-parse", "FETCH_HEAD^"))
    self.assertEqual(
      ".ci/rwf", git(
        self.source, "diff-tree", "--no-commit-id",
        "--name-only", "-r", "FETCH_HEAD",
      ),
    )
    self.assertEqual(
      "test RED --remote 0", git(self.source, "show", "FETCH_HEAD:.ci/rwf"),
    )
    different = self.submit(["test", "GREEN", "--remote"])
    self.assertEqual(2, different.number)
    (self.source / "file.txt").write_text("changed\n")
    git(self.source, "commit", "-am", "changed")
    changed_source = self.submit()
    self.assertEqual(3, changed_source.number)
    self.assertEqual(
      git(self.source, "rev-parse", "HEAD"), changed_source.source_sha,
    )

  def test_retry_lineage_and_stale_tip(self):
    first = self.submit()
    args = ["test", "RED", "--remote"]
    with self.assertRaises(RemoteRequestError):
      retry_request(
        self.source, first.branch, first.request_sha, args, permitted=False,
      )
    second = retry_request(
      self.source, first.branch, first.request_sha, args, permitted=True,
    )
    self.assertEqual(first.branch, second.branch)
    self.assertEqual(1, second.number)
    git(self.source, "fetch", "origin", first.branch)
    self.assertEqual(
      "test RED --remote 1", git(self.source, "show", "FETCH_HEAD:.ci/rwf"),
    )
    self.assertEqual(
      first.request_sha, git(self.source, "rev-parse", "FETCH_HEAD^"),
    )
    with self.assertRaises(RemoteRequestError):
      retry_request(
        self.source, first.branch, first.request_sha, args, permitted=True,
      )
    self.assertTrue(self.submit().reused)

  def test_invalid_argv_and_unauthorized_retry(self):
    for args in (
      ["test", "RED"], ["test", "RED", "--remote", "--poll"],
      ["test", "a\0b", "--remote"],
    ):
      with self.subTest(args=args), self.assertRaises(RemoteRequestError):
        self.submit(args)
    self.assertEqual(
      1, submit_unpolled(self.source, ["test", "RED"]),
    )
    first = self.submit()
    with self.assertRaises(RemoteRequestError):
      retry_request(
        self.source, first.branch, first.request_sha,
        ["test", "GREEN", "--remote"], permitted=True,
      )

  def test_concurrent_allocation_reuses_same_number(self):
    paths = []
    for index in range(2):
      clone = Path(self.temp.name) / f"clone{index}"
      git(
        Path(self.temp.name), "clone", "-b", "feature-test",
        str(self.remote), str(clone),
      )
      paths.append(clone)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker(root):
      try:
        barrier.wait()
        results.append(self.submit(root=root))
      except Exception as exc:
        errors.append(exc)

    workers = [threading.Thread(target=worker, args=(p,)) for p in paths]
    for worker_thread in workers:
      worker_thread.start()
    for worker_thread in workers:
      worker_thread.join()
    self.assertEqual([], errors)
    self.assertEqual([1, 1], sorted(x.number for x in results))
    self.assertEqual(1, sum(not x.reused for x in results))


if __name__ == "__main__":
  unittest.main()
