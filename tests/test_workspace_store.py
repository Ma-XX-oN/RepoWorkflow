import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.workspace_store import (
  WorkspaceClaimError,
  WorkspaceStore,
)


def run_git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", *args],
    cwd=root,
    text=True,
    capture_output=True,
    check=True,
  )
  return result.stdout.strip()


class WorkspaceStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    run_git(self.root, "init")
    run_git(self.root, "config", "user.email", "rwf@example.test")
    run_git(self.root, "config", "user.name", "RWF Test")
    (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
    run_git(self.root, "add", "seed.txt")
    run_git(self.root, "commit", "-m", "seed")
    self.store = WorkspaceStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_create_workspace_starts_available_at_revision_zero(self):
    self.store.create(
      "RWF-89",
      issue=89,
      work_identity="repo-version contract",
    )

    claim = self.store.read_claim("RWF-89")
    workspace = self.store.read_workspace("RWF-89")
    self.assertEqual(claim["status"], "available")
    self.assertEqual(claim["revision"], 0)
    self.assertIsNone(claim["worker_id"])
    self.assertEqual(workspace["issue"], 89)

  def test_claim_uses_expected_revision_and_increments_once(self):
    self.store.create("RWF-89", issue=89, work_identity="version")
    claimed = self.store.update_claim(
      "RWF-89",
      expected_revision=0,
      status="claimed",
      worker_id="agent-a",
      session_id="chat-1",
    )

    self.assertEqual(claimed["revision"], 1)
    self.assertEqual(claimed["worker_id"], "agent-a")

    with self.assertRaisesRegex(WorkspaceClaimError, "stale claim revision"):
      self.store.update_claim(
        "RWF-89",
        expected_revision=0,
        status="claimed",
        worker_id="agent-b",
        session_id="chat-2",
      )

    current = self.store.read_claim("RWF-89")
    self.assertEqual(current, claimed)

  def test_same_worker_can_roll_session_and_revision_forward(self):
    self.store.create("RWF-89", issue=89, work_identity="version")
    claimed = self.store.update_claim(
      "RWF-89", 0, "claimed", "agent-a", "chat-1"
    )
    resumed = self.store.update_claim(
      "RWF-89",
      claimed["revision"],
      "claimed",
      "agent-a",
      "chat-2",
    )

    self.assertEqual(resumed["revision"], 2)
    self.assertEqual(resumed["worker_id"], "agent-a")
    self.assertEqual(resumed["session_id"], "chat-2")

  def test_other_worker_cannot_roll_claim_session(self):
    self.store.create("RWF-89", issue=89, work_identity="version")
    claimed = self.store.update_claim(
      "RWF-89", 0, "claimed", "agent-a", "chat-1"
    )

    with self.assertRaisesRegex(WorkspaceClaimError, "owned by agent-a"):
      self.store.update_claim(
        "RWF-89",
        claimed["revision"],
        "claimed",
        "agent-b",
        "chat-2",
      )

    self.assertEqual(self.store.read_claim("RWF-89"), claimed)

  def test_non_owner_cannot_release_claimed_workspace(self):
    self.store.create("RWF-89", issue=89, work_identity="version")
    self.store.update_claim(
      "RWF-89",
      expected_revision=0,
      status="claimed",
      worker_id="agent-a",
      session_id="chat-1",
    )

    with self.assertRaisesRegex(WorkspaceClaimError, "owned by agent-a"):
      self.store.update_claim(
        "RWF-89",
        expected_revision=1,
        status="available",
        worker_id="agent-b",
        session_id="chat-2",
      )

    self.assertEqual(self.store.read_claim("RWF-89")["revision"], 1)

  def test_owner_can_block_resume_and_release(self):
    self.store.create("RWF-89", issue=89, work_identity="version")
    one = self.store.update_claim(
      "RWF-89", 0, "claimed", "agent-a", "chat-1"
    )
    two = self.store.update_claim(
      "RWF-89", one["revision"], "blocked", "agent-a", "chat-1"
    )
    three = self.store.update_claim(
      "RWF-89", two["revision"], "claimed", "agent-a", "chat-2"
    )
    four = self.store.update_claim(
      "RWF-89", three["revision"], "available", "agent-a", "chat-2"
    )

    self.assertEqual(
      [one["revision"], two["revision"], three["revision"], four["revision"]],
      [1, 2, 3, 4],
    )
    self.assertEqual(four["status"], "available")
    self.assertIsNone(four["worker_id"])
    self.assertIsNone(four["session_id"])

  def test_illegal_transition_leaves_prior_claim_unchanged(self):
    self.store.create("RWF-89", issue=89, work_identity="version")

    with self.assertRaisesRegex(WorkspaceClaimError, "illegal claim transition"):
      self.store.update_claim(
        "RWF-89",
        expected_revision=0,
        status="blocked",
        worker_id="agent-a",
        session_id="chat-1",
      )

    self.assertEqual(self.store.read_claim("RWF-89")["revision"], 0)

  def test_workspace_state_is_under_git_common_dir_not_worktree(self):
    self.store.create("RWF-89", issue=89, work_identity="version")

    common = Path(run_git(self.root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
      common = (self.root / common).resolve()
    expected = common / "repoworkflow" / "workspaces" / "RWF-89"
    self.assertEqual(self.store.workspace_dir("RWF-89"), expected)
    self.assertTrue((expected / "claim.json").is_file())
    self.assertEqual(run_git(self.root, "status", "--porcelain"), "")

  def test_duplicate_workspace_creation_is_rejected_without_mutation(self):
    self.store.create("RWF-89", issue=89, work_identity="first")
    before = json.dumps(
      self.store.read_workspace("RWF-89"),
      sort_keys=True,
    )

    with self.assertRaisesRegex(WorkspaceClaimError, "already exists"):
      self.store.create("RWF-89", issue=89, work_identity="second")

    after = json.dumps(
      self.store.read_workspace("RWF-89"),
      sort_keys=True,
    )
    self.assertEqual(after, before)


if __name__ == "__main__":
  unittest.main()
