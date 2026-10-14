import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.state_store import WriterIdentity


class IndependentCloneLifecyclePublicationTests(unittest.TestCase):
  def git(self, root, *arguments, check=True):
    return subprocess.run(
      ["git", "-C", str(root), *arguments],
      text=True, capture_output=True, check=check,
    )

  def test_conflicting_lifecycle_revisions_reject_stale_remote_push(self):
    # C12: two independently prepared issues cannot silently replace origin.
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      seed = root / "seed"
      seed.mkdir()
      self.git(seed, "init", "-b", "main")
      self.git(seed, "config", "user.name", "Test Agent")
      self.git(seed, "config", "user.email", "test@example.invalid")
      (seed / "README.md").write_text("seed\n", encoding="utf-8")
      self.git(seed, "add", "README.md")
      self.git(seed, "commit", "-m", "seed")
      remote = root / "origin.git"
      self.git(root, "init", "--bare", str(remote))
      self.git(seed, "remote", "add", "origin", str(remote))
      self.git(seed, "push", "origin", "main")

      clones = []
      for name in ("first", "second"):
        clone = root / name
        self.git(root, "clone", "--branch", "main", str(remote), str(clone))
        self.git(clone, "config", "user.name", "Test Agent")
        self.git(clone, "config", "user.email", "test@example.invalid")
        snapshot = LifecycleStore(clone).transition(
          1, "start", name, 0, WriterIdentity(name, "session"), None,
        )
        self.assertEqual(snapshot.revision, 0)
        self.assertEqual(snapshot.lifecycle.state, "active")
        self.git(clone, "add", ".repoworkflow/state/issues/1/lifecycle.json")
        self.git(clone, "commit", "-m", name + " lifecycle start")
        clones.append(clone)

      self.git(clones[0], "push", "origin", "HEAD:refs/heads/main")
      stale = self.git(
        clones[1], "push", "origin", "HEAD:refs/heads/main",
        check=False,
      )
      self.assertNotEqual(stale.returncode, 0)
      self.assertIn("rejected", stale.stderr.lower())
      self.assertEqual(LifecycleStore(clones[1]).read(1).lifecycle.state, "active")

      witness = root / "witness"
      self.git(root, "clone", "--branch", "main", str(remote), str(witness))
      authority = LifecycleStore(witness).read(1)
      self.assertEqual(authority.revision, 0)
      self.assertEqual(authority.lifecycle.history[0].candidate, "first")
      self.assertEqual(authority.lifecycle.state, "active")


if __name__ == "__main__":
  unittest.main()
