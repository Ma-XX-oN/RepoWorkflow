"""Local Git create-only READY PRELIM provider acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.prelim_ready import (
  ReadyPublicationError, create_ready_ref_git,
)


GUID = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/PRELIM-issue-123/main-{GUID}"


def git(root, *args):
  p = subprocess.run(["git", "-C", str(root), *args],
    check=True, capture_output=True, text=True)
  return p.stdout.strip()


class PrelimReadyGitTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.remote = root / "remote.git"
    self.clone = root / "work"
    subprocess.run(["git", "init", "--bare", str(self.remote)],
      capture_output=True, check=True)
    subprocess.run(["git", "init", "-b", "main", str(self.clone)],
      capture_output=True, check=True)
    git(self.clone, "config", "user.name", "RWF Test")
    git(self.clone, "config", "user.email", "fixture@example.invalid")
    (self.clone / "file.txt").write_text("A\n")
    git(self.clone, "add", "file.txt")
    git(self.clone, "commit", "-m", "A")
    self.a = git(self.clone, "rev-parse", "HEAD")
    git(self.clone, "remote", "add", "origin", str(self.remote))
    git(self.clone, "push", "origin", "main")
    (self.clone / "file.txt").write_text("B\n")
    git(self.clone, "commit", "-am", "B")
    self.b = git(self.clone, "rev-parse", "HEAD")

  def remote_ref(self):
    out = git(self.clone, "ls-remote", "origin", REF)
    return out.split()[0] if out else None

  def test_initial_create_only_publication(self):
    self.assertTrue(create_ready_ref_git(
      self.clone, "origin", REF, self.a, "req-1"))
    self.assertEqual(self.remote_ref(), self.a)

  def test_same_guid_cannot_advance_even_by_fast_forward(self):
    create_ready_ref_git(self.clone, "origin", REF, self.a, "req-1")
    with self.assertRaises(ReadyPublicationError):
      create_ready_ref_git(self.clone, "origin", REF, self.b, "req-2")
    self.assertEqual(self.remote_ref(), self.a)

  def test_preexisting_ref_rejected_without_modification(self):
    git(self.clone, "push", "origin", self.a + ":" + REF)
    with self.assertRaises(ReadyPublicationError):
      create_ready_ref_git(self.clone, "origin", REF, self.a, "req-1")
    self.assertEqual(self.remote_ref(), self.a)

  def test_non_prelim_branch_is_rejected(self):
    with self.assertRaises(ReadyPublicationError):
      create_ready_ref_git(self.clone, "origin",
        "refs/heads/main", self.b, "req-1")
    self.assertEqual(git(self.clone, "ls-remote", "origin", "main").split()[0],
                     self.a)


if __name__ == "__main__":
  unittest.main()
