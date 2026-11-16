"""Ticket transitions use the CSV alone, including after a restart."""
from pathlib import Path
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore, LifecycleError
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import RelationshipGraph, IssueRelationships
from repo_workflow.state_store import WriterIdentity
from repo_workflow.workspace_readiness import workspace_readiness


class LifecycleStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.tickets = RelationshipStore(self.root)
    self.tickets.create(RelationshipGraph({
      "1": IssueRelationships("One", ()),
      "2": IssueRelationships("Two", ("1",)),
    }), WriterIdentity("test", "session"))
    self.store = LifecycleStore(self.root)

  def advance(self, action):
    return self.store.transition(1, action, self.store.read(1).revision)

  def test_transitions_update_csv_without_another_state_file(self):
    for action, expected in (("start", "active"), ("submit-review", "in_review"),
                             ("accept", "accepted"), ("complete", "completed")):
      result = self.advance(action)
      self.assertEqual(result.lifecycle.state, expected)
      self.assertEqual(self.tickets.read().states["1"].state, expected)
      self.assertEqual(LifecycleStore(self.root).read(1), result)
    self.assertFalse((self.root / ".repoworkflow/state").exists())
    self.assertEqual(self.tickets.path.read_text().splitlines()[0],
                     "issue,title,dependencies,state")

  def test_dependency_readiness_uses_the_other_ticket_state(self):
    self.assertEqual(workspace_readiness(self.root)[1].blockers, ("1",))
    for action in ("start", "submit-review", "accept", "complete"):
      self.advance(action)
    self.assertEqual(workspace_readiness(self.root)[1].status, "ready")

  def test_stale_csv_update_preserves_newer_state(self):
    old = self.store.read(1)
    current = self.advance("start")
    with self.assertRaisesRegex(LifecycleError, "stale ticket-state"):
      self.store.transition(1, "abort", old.revision)
    self.assertEqual(self.store.read(1), current)

  def test_illegal_transition_preserves_csv(self):
    before = self.tickets.path.read_bytes()
    with self.assertRaisesRegex(LifecycleError, "illegal ticket transition"):
      self.advance("complete")
    self.assertEqual(self.tickets.path.read_bytes(), before)

  def test_abort_resume_and_explicit_reopening(self):
    for action in ("start", "abort", "re-enter", "submit-review", "accept",
                   "complete", "reject/reopen"):
      self.advance(action)
    self.assertEqual(self.store.read(1).lifecycle.state, "active")

  def test_obsolete_json_cannot_override_csv(self):
    path = self.root / ".repoworkflow/state/issues/1/lifecycle.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"state":"completed"}')
    self.assertEqual(self.store.read(1).lifecycle.state, "not_started")
    self.advance("start")
    self.assertEqual(path.read_text(), '{"state":"completed"}')
