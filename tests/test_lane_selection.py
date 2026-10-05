from pathlib import Path
import tempfile
import unittest

from repo_workflow.lane_selection import LaneSelectionError, LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships(None, (), tuple(str(x) for x in deps), (), None)


class LaneSelectionTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")
    self.relationships = RelationshipStore(self.root)
    self.relationships.create(
      RelationshipGraph(issues={
        "1": relation(), "2": relation(), "3": relation(1, 2), "4": relation()
      }),
      self.writer,
    )
    self.store = LaneSelectionStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_create_records_roots_closure_revision_and_assignment(self):
    result = self.store.select((3,), self.writer)
    self.assertEqual(result.value.roots, ("3",))
    self.assertEqual(result.value.closure, ("1", "2", "3"))
    self.assertEqual(
      result.value.graph_revision,
      self.relationships.read().revision,
    )
    self.assertEqual(set(result.value.assignment), {"1", "2", "3"})

  def test_add_recomputes_complete_decomposition_atomically(self):
    first = self.store.select((3,), self.writer)
    second = self.store.add((4,), self.writer, expected_revision=first.revision)
    self.assertEqual(second.value.roots, ("3", "4"))
    self.assertEqual(second.value.closure, ("1", "2", "3", "4"))

  def test_remove_recomputes_closure(self):
    first = self.store.select((3, 4), self.writer)
    second = self.store.remove((3,), self.writer, expected_revision=first.revision)
    self.assertEqual(second.value.roots, ("4",))
    self.assertEqual(second.value.closure, ("4",))

  def test_clear_removes_only_local_selection(self):
    before_graph = self.relationships.read()
    first = self.store.select((3,), self.writer)
    cleared = self.store.clear(expected_revision=first.revision)
    self.assertIsNone(cleared.value)
    self.assertIsNone(self.store.read().value)
    self.assertEqual(self.relationships.read(), before_graph)

  def test_failed_edit_preserves_previous_selection(self):
    first = self.store.select((3,), self.writer)
    with self.assertRaises(Exception):
      self.store.add((999,), self.writer, expected_revision=first.revision)
    self.assertEqual(self.store.read(), first)

  def test_stale_edit_preserves_previous_selection(self):
    first = self.store.select((3,), self.writer)
    second = self.store.add((4,), self.writer, expected_revision=first.revision)
    with self.assertRaisesRegex(LaneSelectionError, "stale"):
      self.store.remove((4,), self.writer, expected_revision=first.revision)
    self.assertEqual(self.store.read(), second)

  def test_selection_is_worktree_local(self):
    self.store.select((3,), self.writer)
    self.assertFalse(
      (self.root / ".repoworkflow" / "state" / "lane-selection").exists()
    )


if __name__ == "__main__":
  unittest.main()
