from pathlib import Path
import tempfile
import unittest

from repo_workflow.current_work_store import CurrentWorkStore, CurrentWorkError
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import RelationshipGraph, IssueRelationships
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class CurrentWorkStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    RepoFixture(self.repo)
    self.writer = WriterIdentity("test", "session")
    self.tickets = RelationshipStore(self.repo)
    self.tickets.create(RelationshipGraph({"1": IssueRelationships("One", ())}), self.writer)
    self.store = CurrentWorkStore(self.repo)

  def test_selection_has_no_ticket_state_or_revision_copy(self):
    before = self.tickets.path.read_bytes()
    self.store.project_start(1, self.writer, None)
    value = self.store.read(validate_durable=True).value.to_json_value()
    self.assertEqual(value, {"current": {"issue": "1"}, "resume": None, "selected_issue": "1"})
    self.assertEqual(self.tickets.path.read_bytes(), before)

  def test_csv_change_does_not_invalidate_issue_selection(self):
    selected = self.store.project_start(1, self.writer, None)
    self.tickets.set_state(1, "active", self.tickets.read().revision)
    self.assertEqual(self.store.read(validate_durable=True), selected)

  def test_abort_retains_resume_selection(self):
    selected = self.store.project_start(1, self.writer, None)
    result = self.store.project_abort(1, self.writer, selected.revision)
    self.assertIsNone(result.value.current)
    self.assertEqual(result.value.resume.issue, "1")

  def test_stale_local_selection_update_is_rejected(self):
    self.store.project_start(1, self.writer, None)
    with self.assertRaises(CurrentWorkError):
      self.store.project_start(1, self.writer, None)
