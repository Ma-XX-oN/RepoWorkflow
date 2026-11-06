"""Issue #787 Git request transport tests using real local Git histories."""
from __future__ import annotations

from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import repo_workflow.remote_request as request_transport

from repo_workflow.remote_request import (
  RemoteRequestError, retry_request, submit_request, submit_unpolled,
)


def git(root, *args):
  result = subprocess.run(
    ["git", *args], cwd=root, text=True, capture_output=True,
    encoding="utf-8", errors="strict", check=False,
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

  def test_submission_preserves_staged_and_untracked_source_work(self):
    (self.source / "staged.txt").write_text("staged but not committed\n")
    (self.source / "untracked.txt").write_text("untracked\n")
    git(self.source, "add", "staged.txt")
    before_head = git(self.source, "rev-parse", "HEAD")
    before_status = git(self.source, "status", "--porcelain=v1")
    first = self.submit()
    self.assertEqual(1, first.number)
    self.assertEqual(before_head, git(self.source, "rev-parse", "HEAD"))
    self.assertEqual(before_status, git(self.source, "status", "--porcelain=v1"))

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

  def test_unpolled_output_identifies_cmd_on_new_and_reused_request(self):
    for _ in range(2):
      out = StringIO()
      with redirect_stdout(out):
        status = submit_unpolled(self.source, ["test", "RED", "--remote"])
      self.assertEqual(0, status)
      self.assertEqual("CMD#1 CMD-1-feature-test", out.getvalue().strip())

  def test_detached_or_cmd_source_branch_is_rejected(self):
    original = git(self.source, "rev-parse", "HEAD")
    git(self.source, "checkout", "--detach", original)
    with self.assertRaises(RemoteRequestError):
      self.submit()
    git(self.source, "checkout", "feature-test")
    first = self.submit()
    git(self.source, "fetch", "origin", first.branch)
    git(self.source, "checkout", "-b", first.branch, "FETCH_HEAD")
    with self.assertRaises(RemoteRequestError):
      self.submit()

  def test_invalid_argv_and_unauthorized_retry(self):
    for args in (
      ["test", "RED"], ["test", "RED", "--remote", "--poll"],
      ["test", "RED", "--remote", "1"],
      ["test", "a\0b", "--remote"],
    ):
      with self.subTest(args=args), self.assertRaises(RemoteRequestError):
        self.submit(args)
    self.assertEqual(
      1, submit_unpolled(self.source, ["test", "RED"]),
    )
    self.assertEqual(
      1, submit_unpolled(self.source, ["test", "RED", "--remote"], remote="-bad"),
    )
    first = self.submit()
    with self.assertRaises(RemoteRequestError):
      retry_request(
        self.source, first.branch, first.request_sha,
        ["test", "GREEN", "--remote"], permitted=True,
      )

  def test_invalid_utf8_in_remote_request_fails_closed(self):
    first = self.submit()
    clone = Path(self.temp.name) / "bad-utf8"
    git(Path(self.temp.name), "clone", "-b", first.branch,
        str(self.remote), str(clone))
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    (clone / ".ci" / "rwf").write_bytes(b"test RED --remote \xff\n")
    git(clone, "add", ".ci/rwf")
    git(clone, "commit", "-m", "invalid UTF-8 marker", "-m", f"RWF-Source: {first.source_sha}")
    git(clone, "push", "origin", "HEAD")
    with self.assertRaises(RemoteRequestError):
      self.submit()

  def test_marker_without_matching_source_identity_is_not_reused(self):
    clone = Path(self.temp.name) / "forged-marker"
    git(Path(self.temp.name), "clone", "-b", "feature-test",
        str(self.remote), str(clone))
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    git(clone, "checkout", "-b", "CMD-1-feature-test")
    marker = clone / ".ci" / "rwf"
    marker.parent.mkdir(parents=True)
    marker.write_text("test RED --remote 0\n")
    git(clone, "add", ".ci/rwf")
    git(clone, "commit", "-m", "missing source binding")
    git(clone, "push", "origin", "HEAD")
    new_request = self.submit()
    self.assertEqual(2, new_request.number)
    self.assertFalse(new_request.reused)

  def test_nonsequential_retry_marker_is_rejected(self):
    first = self.submit()
    clone = Path(self.temp.name) / "bad-retry"
    git(Path(self.temp.name), "clone", "-b", first.branch,
        str(self.remote), str(clone))
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    (clone / ".ci" / "rwf").write_text("test RED --remote 9\n")
    git(clone, "add", ".ci/rwf")
    git(clone, "commit", "-m", "skip retry lineage")
    git(clone, "push", "origin", "HEAD")
    tampered_tip = git(clone, "rev-parse", "HEAD")
    with self.assertRaises(RemoteRequestError):
      retry_request(self.source, first.branch, tampered_tip,
                    ["test", "RED", "--remote"], permitted=True)
    another = self.submit()
    self.assertEqual(2, another.number)

  def test_unauthorized_extra_file_history_is_not_reused(self):
    first = self.submit()
    clone = Path(self.temp.name) / "tamper"
    git(
      Path(self.temp.name), "clone", "-b", first.branch,
      str(self.remote), str(clone),
    )
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    (clone / "unrelated.txt").write_text("not allowed\n")
    git(clone, "add", "unrelated.txt")
    git(clone, "commit", "-m", "unexpected file")
    git(clone, "push", "origin", "HEAD")
    another = self.submit()
    self.assertEqual(2, another.number)
    self.assertFalse(another.reused)

  def test_utf8_argument_round_trip(self):
    args = ["test", "électricité ' ü \\ $HOME", "--remote"]
    result = self.submit(args)
    git(self.source, "fetch", "origin", result.branch)
    import shlex
    recorded = git(self.source, "show", "FETCH_HEAD:.ci/rwf")
    self.assertEqual([*args, "0"], shlex.split(recorded, posix=True))

  def test_global_allocation_observes_other_source_cmd_numbers(self):
    git(self.source, "push", "origin", "HEAD:refs/heads/CMD-41-other-source")
    submitted = self.submit()
    self.assertEqual(42, submitted.number)
    self.assertEqual("CMD-42-feature-test", submitted.branch)

  def test_source_branch_with_slash_preserves_full_branch_name(self):
    git(self.source, "branch", "-m", "feature/subtask")
    first = self.submit()
    self.assertEqual("CMD-1-feature/subtask", first.branch)
    self.assertTrue(self.submit().reused)

  def test_preexisting_hook_path_does_not_block_submission(self):
    (self.source / ".rwf-empty-hooks").write_text("consumer data\n")
    git(self.source, "add", ".rwf-empty-hooks")
    git(self.source, "commit", "-m", "source hook path")
    first = self.submit()
    self.assertEqual(1, first.number)
    self.assertEqual("consumer data", (self.source / ".rwf-empty-hooks").read_text().strip())

  def test_autocrlf_preserves_exact_argument_blob(self):
    git(self.source, "config", "core.autocrlf", "true")
    args = ["test", "alpha\nbeta ü", "--remote"]
    first = self.submit(args)
    git(self.source, "fetch", "origin", first.branch)
    raw = subprocess.run(
      ["git", "show", "FETCH_HEAD:.ci/rwf"], cwd=self.source,
      capture_output=True, check=True,
    ).stdout
    self.assertNotIn(b"\r\n", raw)
    import shlex
    self.assertEqual([*args, "0"], shlex.split(raw.decode("utf-8")))

  def test_utf8_argument_embedded_newline_round_trip(self):
    args = ["test", "alpha\nbeta ü", "--remote"]
    result = self.submit(args)
    git(self.source, "fetch", "origin", result.branch)
    import shlex
    raw = git(self.source, "show", "FETCH_HEAD:.ci/rwf")
    self.assertEqual([*args, "0"], shlex.split(raw, posix=True))
    self.assertNotIn("\r\n", raw)

  def test_source_preexisting_argument_file_preserves_source_identity(self):
    request = self.source / ".ci" / "rwf"
    request.parent.mkdir(parents=True)
    request.write_text("old source data\n")
    git(self.source, "add", ".ci/rwf")
    git(self.source, "commit", "-m", "source already has .ci/rwf")
    first = self.submit()
    retry = retry_request(
      self.source, first.branch, first.request_sha,
      ["test", "RED", "--remote"], permitted=True,
    )
    self.assertEqual(first.branch, retry.branch)
    self.assertEqual(first.source_sha, retry.source_sha)

  def test_completed_result_commit_is_reused(self):
    first = self.submit()
    clone = Path(self.temp.name) / "published"
    git(
      Path(self.temp.name), "clone", "-b", first.branch,
      str(self.remote), str(clone),
    )
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    result = clone / ".repoworkflow" / "result"
    result.parent.mkdir(parents=True)
    result.write_text("0\ncompleted\n")
    git(clone, "add", ".repoworkflow/result")
    git(clone, "commit", "-m", "provider published result")
    git(clone, "push", "origin", "HEAD")
    again = self.submit()
    self.assertEqual(first.number, again.number)
    self.assertTrue(again.reused)
    self.assertEqual(first.request_sha, again.request_sha)

  def test_retry_rejects_remote_tip_advance_during_commit(self):
    first = self.submit()
    original = request_transport._commit
    competing_tip = []

    def race(root, parent, text, *, source_sha):
      candidate = original(root, parent, text, source_sha=source_sha)
      clone = Path(self.temp.name) / "retry-competitor"
      git(Path(self.temp.name), "clone", "-b", first.branch,
          str(self.remote), str(clone))
      git(clone, "config", "user.email", "test@example.invalid")
      git(clone, "config", "user.name", "Fixture")
      result = clone / ".repoworkflow" / "result"
      result.parent.mkdir(parents=True)
      result.write_text("1\ncompeting result\n")
      git(clone, "add", ".repoworkflow/result")
      git(clone, "commit", "-m", "competing result")
      git(clone, "push", "origin", "HEAD")
      competing_tip.append(git(clone, "rev-parse", "HEAD"))
      return candidate

    with patch.object(request_transport, "_commit", side_effect=race):
      with self.assertRaises(RemoteRequestError):
        retry_request(self.source, first.branch, first.request_sha,
                      ["test", "RED", "--remote"], permitted=True)
    self.assertEqual(competing_tip[0], git(
      self.source, "ls-remote", "origin", "refs/heads/" + first.branch
    ).split()[0])

  def test_result_publication_and_retry_keep_request_revision_identity(self):
    first = self.submit()
    clone = Path(self.temp.name) / "attempt-result"
    git(Path(self.temp.name), "clone", "-b", first.branch,
        str(self.remote), str(clone))
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Fixture")
    result = clone / ".repoworkflow" / "result"
    result.parent.mkdir(parents=True)
    result.write_text("0\nfirst attempt\n")
    git(clone, "add", ".repoworkflow/result")
    git(clone, "commit", "-m", "result 0")
    git(clone, "push", "origin", "HEAD")
    first_result_tip = git(clone, "rev-parse", "HEAD")
    reused = self.submit()
    self.assertEqual(first.request_sha, reused.request_sha)
    second = retry_request(self.source, first.branch, first_result_tip,
                           ["test", "RED", "--remote"], permitted=True)
    self.assertEqual(first.number, second.number)
    self.assertNotEqual(first.request_sha, second.request_sha)
    newest = self.submit()
    self.assertEqual(second.request_sha, newest.request_sha)
    self.assertTrue(newest.reused)

  def test_source_tip_advance_during_allocation_fails_closed(self):
    original = request_transport._remote_refs
    advanced = False

    def advance(root, remote):
      nonlocal advanced
      refs = original(root, remote)
      if not advanced:
        advanced = True
        (self.source / "file.txt").write_text("raced commit\n")
        git(self.source, "commit", "-am", "move source during request")
      return refs

    with patch.object(request_transport, "_remote_refs", side_effect=advance):
      with self.assertRaises(RemoteRequestError):
        self.submit()
    self.assertEqual([], [
      branch for branch in git(self.source, "ls-remote", "--heads", "origin").splitlines()
      if "CMD-" in branch
    ])

  def test_source_tip_advance_during_request_preparation_fails_closed(self):
    original = request_transport._commit

    def advance(root, parent, text, *, source_sha):
      candidate = original(root, parent, text, source_sha=source_sha)
      (self.source / "file.txt").write_text("source changed after marker\n")
      git(self.source, "commit", "-am", "move source after marker")
      return candidate

    with patch.object(request_transport, "_commit", side_effect=advance):
      with self.assertRaisesRegex(RemoteRequestError, "source changed"):
        self.submit()
    self.assertFalse(any(
      "CMD-" in line for line in git(
        self.source, "ls-remote", "--heads", "origin"
      ).splitlines()
    ))

  def test_concurrent_distinct_requests_allocate_distinct_numbers(self):
    clones = []
    for index in range(2):
      clone = Path(self.temp.name) / f"distinct{index}"
      git(
        Path(self.temp.name), "clone", "-b", "feature-test",
        str(self.remote), str(clone),
      )
      clones.append(clone)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker(index):
      try:
        barrier.wait()
        results.append(self.submit(
          ["test", ("RED" if index == 0 else "GREEN"), "--remote"],
          root=clones[index],
        ))
      except Exception as exc:
        errors.append(exc)

    jobs = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for job in jobs:
      job.start()
    for job in jobs:
      job.join()
    self.assertEqual([], errors)
    self.assertEqual([1, 2], sorted(result.number for result in results))

  def test_two_threads_same_checkout_do_not_share_fetch_head(self):
    # Distinct argv per round force real concurrent worktree registration.
    for iteration in range(12):
      barrier = threading.Barrier(2)
      results = []
      errors = []
      argv = ["test", f"RED-{iteration}", "--remote"]

      def worker():
        try:
          barrier.wait()
          results.append(self.submit(argv))
        except Exception as exc:
          errors.append(exc)

      tasks = [threading.Thread(target=worker) for _ in range(2)]
      for task in tasks:
        task.start()
      for task in tasks:
        task.join()
      self.assertEqual([], errors, f"concurrency round {iteration}")
      number = iteration + 1
      self.assertEqual([number, number], sorted(x.number for x in results))

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
