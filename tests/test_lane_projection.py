import unittest

from repo_workflow.lane_projection import (
  LaneProjectionError,
  ProjectionRule,
  normalize_rules,
  project_rule,
  project_rules,
  selection_expression,
)
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(*dependencies: int) -> IssueRelationships:
  return IssueRelationships(
    "Issue",
    tuple(str(value) for value in dependencies),
  )


def graph(mapping: dict[int, tuple[int, ...]]) -> RelationshipGraph:
  return RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      str(issue): relation(*dependencies).to_json_value()
      for issue, dependencies in mapping.items()
    },
  })


class LaneProjectionTests(unittest.TestCase):
  def setUp(self):
    self.graph = graph({
      1: (),
      2: (1,),
      3: (2,),
      4: (1,),
      5: (3,),
      6: (4,),
      7: (),
    })

  def test_single_projects_only_seed(self):
    self.assertEqual(
      project_rule(self.graph, ProjectionRule("3", "single")),
      frozenset({"3"}),
    )

  def test_dependencies_include_seed_and_transitive_dependencies(self):
    self.assertEqual(
      project_rule(self.graph, ProjectionRule("3", "dependencies")),
      frozenset({"1", "2", "3"}),
    )

  def test_dependents_include_seed_and_transitive_dependents(self):
    self.assertEqual(
      project_rule(self.graph, ProjectionRule("2", "dependents")),
      frozenset({"2", "3", "5"}),
    )

  def test_both_is_union_of_independent_seed_origin_directions(self):
    self.assertEqual(
      project_rule(self.graph, ProjectionRule("2", "both")),
      frozenset({"1", "2", "3", "5"}),
    )

  def test_both_does_not_reverse_direction_from_dependency(self):
    # #4 also depends on #1, but #4 is not a dependant of seed #2.
    self.assertNotIn(
      "4",
      project_rule(self.graph, ProjectionRule("2", "both")),
    )
    self.assertNotIn(
      "6",
      project_rule(self.graph, ProjectionRule("2", "both")),
    )

  def test_both_does_not_reverse_direction_from_dependant(self):
    value = graph({
      1: (),
      2: (1,),
      3: (),
      4: (2, 3),
    })
    # #3 is a dependency of dependant #4, not a dependency of seed #2.
    self.assertEqual(
      project_rule(value, ProjectionRule("2", "both")),
      frozenset({"1", "2", "4"}),
    )

  def test_fork_and_convergence_count_unique_nodes_once(self):
    value = graph({
      1: (),
      2: (1,),
      3: (1,),
      4: (2, 3),
      5: (4,),
    })
    self.assertEqual(
      project_rule(value, ProjectionRule("1", "dependents")),
      frozenset({"1", "2", "3", "4", "5"}),
    )

  def test_multiple_include_rules_are_unioned(self):
    self.assertEqual(
      project_rules(
        self.graph,
        (
          ProjectionRule("3", "dependencies"),
          ProjectionRule("7", "single"),
        ),
      ),
      ("1", "2", "3", "7"),
    )

  def test_exclude_rules_are_subtracted_after_include_union(self):
    self.assertEqual(
      project_rules(
        self.graph,
        (ProjectionRule("1", "dependents"),),
        (ProjectionRule("4", "dependents"),),
      ),
      ("1", "2", "3", "5"),
    )

  def test_excluding_seed_itself_removes_it(self):
    self.assertEqual(
      project_rules(
        self.graph,
        (ProjectionRule("3", "dependencies"),),
        (ProjectionRule("2", "single"),),
      ),
      ("1", "3"),
    )

  def test_duplicate_rules_are_idempotent(self):
    rule = ProjectionRule("3", "dependencies")
    self.assertEqual(
      project_rules(self.graph, (rule, rule)),
      ("1", "2", "3"),
    )

  def test_rule_identity_includes_mode(self):
    rules = normalize_rules((
      ProjectionRule("3", "single"),
      ProjectionRule("3", "dependencies"),
      ProjectionRule("3", "single"),
    ))
    self.assertEqual(
      rules,
      (
        ProjectionRule("3", "dependencies"),
        ProjectionRule("3", "single"),
      ),
    )

  def test_selection_expression_is_compact_and_deterministic(self):
    self.assertEqual(
      selection_expression(
        (
          ProjectionRule("413", "both"),
          ProjectionRule("521", "single"),
        ),
        (ProjectionRule("456", "dependents"),),
      ),
      "(inc_both(#413) ∪ #521) − inc_dependents(#456)",
    )

  def test_selection_expression_names_dependencies_explicitly(self):
    self.assertEqual(
      selection_expression(
        (ProjectionRule("7", "single"),),
        (ProjectionRule("3", "dependencies"),),
      ),
      "#7 − inc_dependencies(#3)",
    )

  def test_invalid_mode_is_rejected(self):
    with self.assertRaisesRegex(LaneProjectionError, "invalid projection mode"):
      ProjectionRule("1", "connected")

  def test_unknown_seed_is_rejected_by_graph(self):
    with self.assertRaisesRegex(Exception, "unknown issue"):
      project_rule(self.graph, ProjectionRule("999", "single"))


if __name__ == "__main__":
  unittest.main()
