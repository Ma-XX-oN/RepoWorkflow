"""#583 lifecycle event continuity independent positive/negative acceptance."""

from pathlib import Path
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleError, LifecycleStore
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class LifecycleReentryCandidateAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("verifier", "session")
    self.lifecycle = LifecycleStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def step(self, issue, action, expected_revision, candidate="candidate-A"):
    return self.lifecycle.transition(
      issue, action, candidate, 0, self.writer, expected_revision,
    )

  def test_second_abort_generation_retains_all_previous_events(self):
    # L11: abandon and restart twice, preserving both historical generations.
    x = self.step(1, "start", None)
    x = self.step(1, "abort", x.revision)
    first_abandonment = x.lifecycle.history
    x = self.step(1, "re-enter", x.revision)
    x = self.step(1, "abort", x.revision)
    self.assertEqual(x.lifecycle.state, "aborted")
    self.assertEqual(x.revision, 3)
    self.assertEqual(
      [event.transition for event in x.lifecycle.history],
      ["start", "abort", "re-enter", "abort"],
    )
    self.assertEqual(x.lifecycle.history[:2], first_abandonment)
    self.assertFalse(x.lifecycle.dependency_satisfied)
    self.assertEqual(LifecycleStore(self.root).read(1), x)

  def test_rejection_and_resubmit_retains_old_candidate_history(self):
    # L09/L17: old accepted candidate cannot be mistaken for a new review.
    x = self.step(2, "start", None)
    x = self.step(2, "submit-review", x.revision)
    x = self.step(2, "reject/reopen", x.revision)
    old_history = x.lifecycle.history
    x = self.step(2, "submit-review", x.revision, "candidate-B")
    with self.assertRaises(LifecycleError):
      self.step(2, "accept", x.revision, "candidate-A")
    self.assertEqual(LifecycleStore(self.root).read(2), x)
    x = self.step(2, "accept", x.revision, "candidate-B")
    self.assertEqual(x.lifecycle.state, "accepted")
    self.assertEqual(x.lifecycle.history[:3], old_history)
    self.assertEqual(x.lifecycle.history[-1].candidate, "candidate-B")
    self.assertFalse(x.lifecycle.dependency_satisfied)

  def test_accepted_changed_candidate_requires_reopen_new_review(self):
    # L10/L17: complete may not silently bind to a changed candidate.
    x = self.step(3, "start", None)
    x = self.step(3, "submit-review", x.revision)
    x = self.step(3, "accept", x.revision)
    accepted = x
    with self.assertRaises(LifecycleError):
      self.step(3, "complete", x.revision, "candidate-B")
    self.assertEqual(LifecycleStore(self.root).read(3), accepted)
    x = self.step(3, "reject/reopen", x.revision)
    x = self.step(3, "submit-review", x.revision, "candidate-B")
    x = self.step(3, "accept", x.revision, "candidate-B")
    x = self.step(3, "complete", x.revision, "candidate-B")
    self.assertEqual(x.lifecycle.state, "completed")
    self.assertTrue(x.lifecycle.dependency_satisfied)
    self.assertEqual(x.lifecycle.history[2], accepted.lifecycle.history[2])
    self.assertEqual(x.lifecycle.history[-1].candidate, "candidate-B")
    self.assertEqual(LifecycleStore(self.root).read(3), x)


if __name__ == "__main__":
  unittest.main()
