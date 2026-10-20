"""#583 L15 detached-client loss and fresh clone identity acceptance."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity


class FreshCloneLifecycleAcceptance(unittest.TestCase):
  def git(self, root, *args):
    return subprocess.run(
      ["git", "-C", str(root), *args],
      capture_output=True, text=True, check=True,
    )

  def test_lost_writer_clone_recovered_by_new_session_without_history_loss(self):
    # L15: a different clone + writer/session resumes authoritative lifecycle.
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      origin = root / "bare.git"
      self.git(root, "init", "--bare", str(origin))
      first = root / "first"
      first.mkdir()
      self.git(first, "init", "-b", "main")
      self.git(first, "config", "user.name", "Actor A")
      self.git(first, "config", "user.email", "actor-a@example.invalid")
      (first / "README.md").write_text("fixture\n", encoding="utf-8")
      old = WriterIdentity("actor-a", "session-a")
      RelationshipStore(first).create(
        RelationshipGraph(issues={
          "1": IssueRelationships("First issue", ()),
        }), old,
      )
      before = LifecycleStore(first).transition(
        1, "start", "same-candidate", 0, old, None,
      )
      self.assertEqual(before.revision, 0)
      RelationshipStore(first).refresh_states(old)
      self.git(first, "add", ".")
      self.git(first, "commit", "-m", "original writer lifecycle start")
      self.git(first, "remote", "add", "origin", str(origin))
      self.git(first, "push", "origin", "main")

      # The writer's worktree and process/session become unavailable.
      shutil.rmtree(first)
      replacement = root / "replacement"
      self.git(root, "clone", "-b", "main", str(origin), str(replacement))
      self.git(replacement, "config", "user.name", "Actor B")
      self.git(replacement, "config", "user.email", "actor-b@example.invalid")
      resumed = LifecycleStore(replacement).read(1)
      self.assertEqual(resumed, before)
      self.assertEqual(
        RelationshipStore(replacement).read().states["1"].state, "active",
      )
      next_writer = WriterIdentity("actor-b", "session-b")
      transitioned = LifecycleStore(replacement).transition(
        1, "submit-review", "same-candidate", 0,
        next_writer, resumed.revision,
      )
      self.assertEqual(transitioned.revision, 1)
      self.assertEqual(transitioned.lifecycle.state, "in_review")
      self.assertEqual(
        transitioned.lifecycle.history[0], before.lifecycle.history[0],
      )
      RelationshipStore(replacement).refresh_states(next_writer)
      self.git(replacement, "add", ".")
      self.git(replacement, "commit", "-m", "new session resumes old writer")
      self.git(replacement, "push", "origin", "main")

      witness = root / "witness"
      self.git(root, "clone", "-b", "main", str(origin), str(witness))
      durable = LifecycleStore(witness).read(1)
      record = LifecycleStore(witness).records.read("issues/1/lifecycle")
      self.assertEqual(durable, transitioned)
      self.assertEqual(record["revision"], 1)
      self.assertEqual(record["writer_id"], "actor-b")
      self.assertEqual(record["session_id"], "session-b")
      self.assertEqual(record["previous_revision"], 0)
      self.assertEqual(len(durable.lifecycle.history), 2)
      self.assertEqual(
        RelationshipStore(witness).read().states["1"].lifecycle_revision, 1,
      )
      self.assertEqual(
        RelationshipStore(witness).path.read_bytes(),
        RelationshipStore(replacement).path.read_bytes(),
      )


if __name__ == "__main__":
  unittest.main()
