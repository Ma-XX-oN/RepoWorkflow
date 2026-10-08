from pathlib import Path
import tempfile
import unittest

from repo_workflow.lane_projection import ProjectionRule
from repo_workflow.lane_selection import LaneSelectionError, LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(x) for x in deps))


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
        "1": relation(),
        "2": relation(),
        "3": relation(1, 2),
        "4": relation(1),
        "5": relation(3),
        "6": relation(),
      }),
      self.writer,
    )
    self.store = LaneSelectionStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_default_both_is_union_from_seed_without_direction_reversal(self):
    result = self.store.select((1,), self.writer)
    self.assertEqual(result.value.roots, ("1",))
    self.assertEqual(result.value.closure, ("1", "3", "4", "5"))
    self.assertNotIn("2", result.value.closure)

  def test_dependencies_rule_projects_prerequisite_closure(self):
    result = self.store.select_rules(
      (ProjectionRule("3", "dependencies"),),
      self.writer,
    )
    self.assertEqual(result.value.closure, ("1", "2", "3"))

  def test_dependents_rule_projects_downstream_closure(self):
    result = self.store.select_rules(
      (ProjectionRule("1", "dependents"),),
      self.writer,
    )
    self.assertEqual(result.value.closure, ("1", "3", "4", "5"))

  def test_single_rule_projects_only_seed(self):
    result = self.store.select_rules(
      (ProjectionRule("3", "single"),),
      self.writer,
    )
    self.assertEqual(result.value.closure, ("3",))

  def test_add_preserves_existing_rule_modes(self):
    first = self.store.select_rules(
      (ProjectionRule("3", "dependencies"),),
      self.writer,
    )
    second = self.store.add_rules(
      (ProjectionRule("6", "single"),),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(
      second.value.includes,
      (
        ProjectionRule("3", "dependencies"),
        ProjectionRule("6", "single"),
      ),
    )
    self.assertEqual(second.value.closure, ("1", "2", "3", "6"))

  def test_same_seed_different_modes_are_distinct_rules(self):
    first = self.store.select_rules(
      (ProjectionRule("3", "single"),),
      self.writer,
    )
    second = self.store.add_rules(
      (ProjectionRule("3", "dependencies"),),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(
      set(second.value.includes),
      {
        ProjectionRule("3", "single"),
        ProjectionRule("3", "dependencies"),
      },
    )

  def test_remove_matches_seed_and_mode_not_projected_nodes(self):
    first = self.store.select_rules(
      (
        ProjectionRule("3", "single"),
        ProjectionRule("3", "dependencies"),
        ProjectionRule("6", "single"),
      ),
      self.writer,
    )
    second = self.store.remove_rules(
      (ProjectionRule("3", "single"),),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertIn(
      ProjectionRule("3", "dependencies"),
      second.value.includes,
    )
    self.assertNotIn(
      ProjectionRule("3", "single"),
      second.value.includes,
    )
    self.assertEqual(second.value.closure, ("1", "2", "3", "6"))

  def test_exclude_rule_subtracts_projection_without_mutating_includes(self):
    first = self.store.select_rules(
      (ProjectionRule("1", "dependents"),),
      self.writer,
    )
    second = self.store.exclude_rules(
      (ProjectionRule("4", "single"),),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(second.value.includes, first.value.includes)
    self.assertEqual(
      second.value.excludes,
      (ProjectionRule("4", "single"),),
    )
    self.assertEqual(second.value.closure, ("1", "3", "5"))

  def test_duplicate_rule_add_is_idempotent(self):
    first = self.store.select_rules(
      (ProjectionRule("3", "single"),),
      self.writer,
    )
    second = self.store.add_rules(
      (ProjectionRule("3", "single"),),
      self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(
      second.value.includes,
      (ProjectionRule("3", "single"),),
    )

  def test_legacy_schema_three_migrates_roots_to_both_rules(self):
    revision = self.relationships.read().revision
    self.store.records.create(
      "selection",
      {
        "schema_version": 3,
        "roots": ["1", "3"],
        "closure": ["1", "2", "3"],
        "graph_revision": revision,
        "follow": {
          "group": 0,
          "feature": 0,
          "epic": 0,
          "initiative": 0,
        },
        "show_children": {
          "group": False,
          "feature": False,
          "epic": False,
          "initiative": False,
        },
        "assignment": {"1": "A", "2": "B", "3": "A"},
      },
      self.writer,
    )
    current = self.store.read()
    self.assertEqual(
      current.value.includes,
      (
        ProjectionRule("1", "both"),
        ProjectionRule("3", "both"),
      ),
    )
    self.assertEqual(current.value.excludes, ())
    self.assertEqual(current.value.schema_version, 4)

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
      self.store.add_rules(
        (ProjectionRule("999", "single"),),
        self.writer,
        expected_revision=first.revision,
      )
    self.assertEqual(self.store.read(), first)

  def test_stale_edit_preserves_previous_selection(self):
    first = self.store.select((3,), self.writer)
    second = self.store.add((6,), self.writer, expected_revision=first.revision)
    with self.assertRaisesRegex(LaneSelectionError, "stale"):
      self.store.remove((6,), self.writer, expected_revision=first.revision)
    self.assertEqual(self.store.read(), second)

  def test_selection_is_worktree_local(self):
    self.store.select((3,), self.writer)
    self.assertFalse(
      (self.root / ".repoworkflow" / "state" / "lane-selection").exists()
    )


  def test_changed_graph_reprojects_saved_rules_before_inspection(self):
    selected = self.store.select_rules(
      (ProjectionRule("3", "dependencies"),),
      self.writer,
    )
    self.assertEqual(selected.value.closure, ("1", "2", "3"))
    snapshot = self.relationships.read()
    changed = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(),
      "3": relation(1, 2, 6),
      "4": relation(1),
      "5": relation(3),
      "6": relation(),
    })
    self.relationships.replace(snapshot.revision, changed, self.writer)
    actual = self.store.read()
    self.assertEqual(actual.value.closure, ("1", "2", "3", "6"))
    self.assertEqual(actual.value.graph_revision, self.relationships.read().revision)
    self.assertEqual(set(actual.value.assignment), set(actual.value.closure))


if __name__ == "__main__":
  unittest.main()
