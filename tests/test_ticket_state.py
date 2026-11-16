from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import tempfile
import unittest

from repo_workflow.relationship_store import RelationshipStore, RelationshipStoreError
from repo_workflow.relationships import RelationshipGraph, IssueRelationships
from repo_workflow.state_store import WriterIdentity
from repo_workflow.ticket_merge import merge_ticket_csv, TicketMergeError


class TicketStateTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.writer = WriterIdentity("test", "session")
    self.store = RelationshipStore(self.root)
    self.graph = RelationshipGraph({
      "1": IssueRelationships("One, quoted", ()),
      "2": IssueRelationships("Two", ("1",)),
    })
    self.store.create(self.graph, self.writer)

  def test_csv_contains_state_and_dependencies_without_revisions(self):
    self.assertEqual(self.store.path.read_text(),
      'issue,title,dependencies,state\n1,"One, quoted",,not_started\n2,Two,1,not_started\n')

  def test_old_csv_status_is_preserved_and_revision_column_removed_on_write(self):
    self.store.path.write_text(
      'issue,title,dependencies,state,state_revision\n1,One,,completed,7\n2,Two,1,active,3\n')
    old = self.store.read()
    self.store.replace(old.revision, old.graph, self.writer)
    self.assertEqual(self.store.read().states["1"].state, "completed")
    self.assertNotIn("state_revision", self.store.path.read_text())

  def test_dependency_or_title_edit_preserves_state(self):
    self.store.set_state(1, "completed", self.store.read().revision)
    before = self.store.read()
    graph = RelationshipGraph({**self.graph.issues,
      "2": IssueRelationships("Renamed", ())})
    self.store.replace(before.revision, graph, self.writer)
    self.assertEqual(self.store.read().states["1"].state, "completed")
    self.assertEqual(self.store.direct_dependencies(2), ())

  def test_invalid_state_preserves_file(self):
    before = self.store.path.read_bytes()
    with self.assertRaisesRegex(Exception, "invalid ticket state"):
      self.store.set_state(1, "nonsense", self.store.read().revision)
    self.assertEqual(self.store.path.read_bytes(), before)

  def test_missing_csv_does_not_use_a_json_graph_as_authority(self):
    self.store.path.unlink()
    old = self.root / ".repoworkflow/state/relationships/graph.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"value": {"issues": {}}}')
    with self.assertRaisesRegex(RelationshipStoreError, "record is missing"):
      self.store.read()

  def test_concurrent_updates_do_not_silently_overwrite(self):
    revision = self.store.read().revision
    barrier = Barrier(2)
    def update(issue):
      barrier.wait(timeout=5)
      try:
        self.store.set_state(issue, "active", revision)
        return True
      except RelationshipStoreError:
        return False
    with ThreadPoolExecutor(max_workers=2) as workers:
      results = list(workers.map(update, (1, 2)))
    self.assertEqual(results.count(True), 1)

  def test_merge_keeps_independent_state_and_dependency_changes(self):
    base = 'issue,title,dependencies,state\n1,One,,active\n2,Two,1,not_started\n'
    ours = base.replace('1,One,,active', '1,One,,completed')
    theirs = base.replace('2,Two,1,', '2,Two,,')
    merged = merge_ticket_csv(self.root, base, ours, theirs)
    self.assertIn('1,One,,completed', merged)
    self.assertIn('2,Two,,not_started', merged)

  def test_conflicting_state_changes_need_resolution(self):
    base = self.store.path.read_text()
    with self.assertRaisesRegex(TicketMergeError, "divergent state changes"):
      merge_ticket_csv(self.root, base, base.replace('not_started', 'active', 1),
                       base.replace('not_started', 'aborted', 1))
