from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.workspace_store import WorkspaceClaimError, WorkspaceStore
from repo_workflow.workspace_worktree import WorktreeBackend, WorktreeError


def git(root: Path, *args: str) -> str:
  return subprocess.run(
    ["git", *args], cwd=root, check=True, capture_output=True, text=True
  ).stdout.strip()


def race_claim(root: str, worker: str, gate, output) -> None:
  store = WorkspaceStore(Path(root))
  gate.wait()
  try:
    claim = store.update_claim(
      "RWF-143", 0, "claimed", worker, f"{worker}-session"
    )
    output.put(("won", worker, claim["revision"]))
  except WorkspaceClaimError as exc:
    output.put(("lost", worker, str(exc)))


class WorkspaceIntegrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.base = Path(self.temp.name)
    self.root = self.base / "repo"
    self.root.mkdir()
    git(self.root, "init")
    git(self.root, "config", "user.email", "rwf@example.test")
    git(self.root, "config", "user.name", "RWF Test")
    (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
    git(self.root, "add", "seed.txt")
    git(self.root, "commit", "-m", "seed")
    self.base_ref = git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
    self.base_sha = git(self.root, "rev-parse", "HEAD")
    self.backend = WorktreeBackend(self.root)
    self.store = WorkspaceStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def provision(self, issue: int):
    workspace = f"RWF-{issue}"
    branch = f"issue-{issue}-integration"
    path = self.base / workspace
    self.backend.provision(
      workspace, self.base_ref, self.base_sha, branch, path
    )
    self.store.create(
      workspace,
      issue=issue,
      work_identity=f"issue-{issue}",
      branch=branch,
      worktree_path=path,
    )
    return workspace, branch, path

  def test_two_workspaces_are_isolated_and_local_state_is_not_committed(self):
    first, first_branch, first_path = self.provision(143)
    second, second_branch, second_path = self.provision(144)

    (first_path / "first.txt").write_text("first\n", encoding="utf-8")
    git(first_path, "add", "first.txt")
    git(first_path, "commit", "-m", "first workspace")
    (second_path / "second.txt").write_text("second\n", encoding="utf-8")
    git(second_path, "add", "second.txt")
    git(second_path, "commit", "-m", "second workspace")

    self.assertNotEqual(git(first_path, "rev-parse", "HEAD"), self.base_sha)
    self.assertNotEqual(git(second_path, "rev-parse", "HEAD"), self.base_sha)
    self.assertFalse((first_path / "second.txt").exists())
    self.assertFalse((second_path / "first.txt").exists())
    self.assertEqual(git(self.root, "status", "--porcelain"), "")
    self.assertFalse((self.root / ".repoworkflow").exists())
    self.assertEqual(
      [v["workspace_id"] for v in self.store.list_workspaces()],
      [first, second],
    )

  def test_concurrent_same_revision_claim_has_exactly_one_winner(self):
    self.provision(143)
    context = multiprocessing.get_context("spawn")
    gate = context.Barrier(2)
    output = context.Queue()
    workers = [
      context.Process(
        target=race_claim,
        args=(str(self.root), worker, gate, output),
      )
      for worker in ("agent-a", "agent-b")
    ]
    for worker in workers:
      worker.start()
    for worker in workers:
      worker.join(10)
      self.assertFalse(worker.is_alive())
      self.assertEqual(worker.exitcode, 0)

    results = [output.get(timeout=2), output.get(timeout=2)]
    winners = [item for item in results if item[0] == "won"]
    losers = [item for item in results if item[0] == "lost"]
    self.assertEqual(len(winners), 1, results)
    self.assertEqual(len(losers), 1, results)
    self.assertEqual(winners[0][2], 1)
    self.assertIn("stale claim revision", losers[0][2])
    claim = self.store.read_claim("RWF-143")
    self.assertEqual(claim["revision"], 1)
    self.assertEqual(claim["worker_id"], winners[0][1])

  def test_dirty_retirement_is_refused_then_clean_retirement_succeeds(self):
    workspace, branch, path = self.provision(143)
    (path / "dirty.txt").write_text("protect me\n", encoding="utf-8")

    with self.assertRaisesRegex(WorktreeError, "protected local work"):
      self.backend.retire(workspace, path, branch)
    self.assertTrue(path.exists())

    (path / "dirty.txt").unlink()
    self.backend.retire(workspace, path, branch)
    self.assertFalse(path.exists())
    self.assertEqual(
      git(self.root, "rev-parse", f"refs/heads/{branch}"),
      self.base_sha,
    )


if __name__ == "__main__":
  unittest.main()
