from pathlib import Path
import tempfile
import unittest

from repo_workflow.lane_selection import LaneSelectionError, LaneSelectionStore
from repo_workflow.lane_traversal import FollowPolicy, ShowChildrenPolicy
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(x) for x in deps))


def titled(title: str, *deps: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(x) for x in deps))


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
    result = self.store.select(
      (3,),
      self.writer,
      follow=FollowPolicy(feature=1),
    )
    self.assertEqual(result.value.roots, ("3",))
    self.assertEqual(result.value.closure, ("1", "2", "3"))
    self.assertEqual(
      result.value.graph_revision,
      self.relationships.read().revision,
    )
    self.assertEqual(set(result.value.assignment), {"1", "2", "3"})

  def test_followed_dependency_is_focus_inside_complete_component(self):
    result = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(feature=1),
    )
    self.assertEqual(result.value.roots, ("1",))
    self.assertEqual(result.value.closure, ("1", "2", "3"))
    self.assertEqual(set(result.value.assignment), {"1", "2", "3"})

  def test_add_focus_in_same_component_preserves_complete_component(self):
    first = self.store.select(
      (1,), self.writer, follow=FollowPolicy(feature=1)
    )
    second = self.store.add((3,), self.writer, expected_revision=first.revision)
    self.assertEqual(second.value.roots, ("1", "3"))
    self.assertEqual(second.value.closure, ("1", "2", "3"))

  def test_remove_focus_in_same_component_keeps_component_from_remaining_seed(self):
    first = self.store.select(
      (1, 3), self.writer, follow=FollowPolicy(feature=1)
    )
    second = self.store.remove((1,), self.writer, expected_revision=first.revision)
    self.assertEqual(second.value.roots, ("3",))
    self.assertEqual(second.value.closure, ("1", "2", "3"))

  def test_add_recomputes_complete_decomposition_atomically(self):
    first = self.store.select(
      (3,), self.writer, follow=FollowPolicy(feature=1)
    )
    second = self.store.add((4,), self.writer, expected_revision=first.revision)
    self.assertEqual(second.value.roots, ("3", "4"))
    self.assertEqual(second.value.closure, ("1", "2", "3", "4"))

  def test_remove_recomputes_closure(self):
    first = self.store.select(
      (3, 4), self.writer, follow=FollowPolicy(feature=1)
    )
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

  def test_enabled_selection_stops_at_unfollowed_group_boundary(self):
    before = self.relationships.read()
    self.relationships.replace(
      before.revision,
      RelationshipGraph(issues={
        "1": titled("Issue 1"),
        "2": titled("Feature: Boundary", 1),
        "3": titled("Issue 3", 2),
      }),
      self.writer,
    )
    result = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(epic=1),
    )
    self.assertEqual(result.value.closure, ("1", "2"))
    self.assertEqual(result.value.follow, FollowPolicy(epic=1))

  def test_follow_policy_is_persisted_with_selection(self):
    before = self.relationships.read()
    self.relationships.replace(
      before.revision,
      RelationshipGraph(issues={
        "1": titled("Issue 1"),
        "2": titled("Feature: Boundary", 1),
        "3": titled("Issue 3", 2),
      }),
      self.writer,
    )
    result = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(feature=1),
    )
    self.assertEqual(result.value.closure, ("1", "2", "3"))
    self.assertEqual(
      self.store.read().value.follow,
      FollowPolicy(feature=1),
    )

  def test_add_without_new_follow_flags_preserves_policy(self):
    before = self.relationships.read()
    self.relationships.replace(
      before.revision,
      RelationshipGraph(issues={
        "1": titled("Issue 1"),
        "2": titled("Feature: Boundary", 1),
        "3": titled("Issue 3", 2),
        "4": titled("Issue 4"),
      }),
      self.writer,
    )
    first = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(feature=1),
    )
    second = self.store.add(
      (4,),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(second.value.follow, FollowPolicy(feature=1))
    self.assertEqual(second.value.closure, ("1", "2", "3", "4"))

  def test_schema_one_selection_reads_with_default_follow_policy(self):
    revision = self.relationships.read().revision
    self.store.records.create(
      "selection",
      {
        "schema_version": 1,
        "roots": ["1"],
        "closure": ["1"],
        "graph_revision": revision,
        "assignment": {"1": "A"},
      },
      self.writer,
    )
    current = self.store.read()
    self.assertEqual(current.value.follow, FollowPolicy())
    self.assertEqual(current.value.show_children, ShowChildrenPolicy())
    self.assertEqual(current.value.schema_version, 3)

  def test_show_children_policy_is_persisted_with_selection(self):
    before = self.relationships.read()
    self.relationships.replace(
      before.revision,
      RelationshipGraph(issues={
        "1": titled("Issue 1"),
        "2": titled("Feature: Boundary", 1),
        "3": titled("Issue 3", 2),
        "4": titled("Issue 4", 3),
      }),
      self.writer,
    )
    result = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(epic=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(result.value.closure, ("1", "2", "3"))
    self.assertEqual(
      self.store.read().value.show_children,
      ShowChildrenPolicy(feature=True),
    )

  def test_add_without_new_show_children_flags_preserves_policy(self):
    before = self.relationships.read()
    self.relationships.replace(
      before.revision,
      RelationshipGraph(issues={
        "1": titled("Issue 1"),
        "2": titled("Feature: Boundary", 1),
        "3": titled("Issue 3", 2),
        "4": titled("Issue 4"),
      }),
      self.writer,
    )
    first = self.store.select(
      (1,),
      self.writer,
      follow=FollowPolicy(epic=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    second = self.store.add(
      (4,),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(
      second.value.show_children,
      ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(second.value.closure, ("1", "2", "3", "4"))

  def test_schema_two_selection_reads_with_default_show_children_policy(self):
    revision = self.relationships.read().revision
    self.store.records.create(
      "selection",
      {
        "schema_version": 2,
        "roots": ["1"],
        "closure": ["1"],
        "graph_revision": revision,
        "follow": FollowPolicy().to_json_value(),
        "assignment": {"1": "A"},
      },
      self.writer,
    )
    current = self.store.read()
    self.assertEqual(current.value.show_children, ShowChildrenPolicy())
    self.assertEqual(current.value.schema_version, 3)

  def test_selection_is_worktree_local(self):
    self.store.select((3,), self.writer)
    self.assertFalse(
      (self.root / ".repoworkflow" / "state" / "lane-selection").exists()
    )


if __name__ == "__main__":
  unittest.main()
