"""Local Git acceptance fixture for offline concurrent published PRELIM refs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.prelim_queue import (
  PrelimQueueError, discover_ready_prelims, verify_immutable_prelims,
)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


def git(where, *args):
  result = subprocess.run(
    ["git", "-C", str(where), *args],
    text=True, capture_output=True, check=True,
  )
  return result.stdout.strip()


class OfflineGitPrelimTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.remote = root / "remote.git"
    subprocess.run(
      ["git", "init", "--bare", str(self.remote)],
      capture_output=True, check=True,
    )
    self.a = root / "a"
    self.b = root / "b"
    subprocess.run(
      ["git", "init", "-b", "main", str(self.a)],
      capture_output=True, check=True,
    )
    git(self.a, "config", "user.email", "test@example.invalid")
    git(self.a, "config", "user.name", "RWF Local Fixture")
    (self.a / "README").write_text("base\n")
    git(self.a, "add", "README")
    git(self.a, "commit", "-m", "base")
    git(self.a, "remote", "add", "origin", str(self.remote))
    git(self.a, "push", "-u", "origin", "main")
    subprocess.run(
      ["git", "clone", "--branch", "main",
       str(self.remote), str(self.b)],
      capture_output=True, check=True,
    )
    git(self.b, "config", "user.email", "test@example.invalid")
    git(self.b, "config", "user.name", "RWF Local Fixture")

  def published(self):
    refs = {}
    for line in git(self.a, "ls-remote", "--heads", "origin").splitlines():
      sha, ref = line.split()
      refs[ref] = sha
    return refs

  def test_two_offline_developers_can_submit_without_shared_queue(self):
    for repo, issue, guid in [(self.a, 123, A), (self.b, 456, B)]:
      (repo / f"issue-{issue}").write_text(f"issue-{issue}\n")
      git(repo, "add", f"issue-{issue}")
      git(repo, "commit", "-m", f"issue-{issue}")
      name = f"PRELIM-issue-{issue}/main-{guid}"
      git(repo, "branch", name)
      git(repo, "push", "origin", name)
    ready = discover_ready_prelims(self.published())
    self.assertEqual(len(ready), 2)
    self.assertEqual({x.destination for x in ready}, {"main"})
    self.assertEqual(
      {x.umbrella for x in ready}, {"issue-123", "issue-456"},
    )

  def test_unprotected_remote_update_is_detected_not_prevented(self):
    name = f"PRELIM-issue-123/main-{A}"
    git(self.a, "branch", name)
    git(self.a, "push", "origin", name)
    recorded = {
      x.ref: x.sha for x in discover_ready_prelims(self.published())
    }
    git(self.a, "checkout", name)
    (self.a / "later").write_text("changed after publication\n")
    git(self.a, "add", "later")
    git(self.a, "commit", "-m", "later update")
    git(self.a, "push", "origin", name)
    with self.assertRaisesRegex(PrelimQueueError, "changed"):
      verify_immutable_prelims(recorded, self.published())


if __name__ == "__main__":
  unittest.main()
