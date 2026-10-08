import unittest
from pathlib import Path

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def titled(title: str, *dependencies: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(value) for value in dependencies))


class LaneTerminalRootExpansionTests(unittest.TestCase):
  def test_ordinary_terminal_launches_dependant_traversal(self):
    graph = RelationshipGraph(issues={
      "1": titled("Implement foundation"),
      "2": titled("Implement middle", 1),
      "3": titled("Implement seed", 2),
      "4": titled("Implement dependant", 1),
    })
    plan = decompose_lanes(graph, [3])
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))

  def test_bug_terminal_is_included_but_does_not_launch_dependants(self):
    graph = RelationshipGraph(issues={
      "1": titled("Bug: Boundary"),
      "2": titled("Implement seed", 1),
      "3": titled("Unrelated dependant", 1),
    })
    plan = decompose_lanes(graph, [2])
    self.assertEqual(plan.closure, ("1", "2"))

  def test_refactor_terminal_is_included_but_does_not_launch_dependants(self):
    graph = RelationshipGraph(issues={
      "1": titled("Refactor: Boundary"),
      "2": titled("Implement seed", 1),
      "3": titled("Unrelated dependant", 1),
    })
    plan = decompose_lanes(graph, [2])
    self.assertEqual(plan.closure, ("1", "2"))

  def test_bug_before_terminal_does_not_stop_dependency_traversal(self):
    graph = RelationshipGraph(issues={
      "1": titled("Implement foundation"),
      "2": titled("Bug: Intermediate", 1),
      "3": titled("Implement seed", 2),
    })
    plan = decompose_lanes(graph, [3])
    self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_refactor_before_terminal_does_not_stop_dependency_traversal(self):
    graph = RelationshipGraph(issues={
      "1": titled("Implement foundation"),
      "2": titled("Refactor: Intermediate", 1),
      "3": titled("Implement seed", 2),
    })
    plan = decompose_lanes(graph, [3])
    self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_terminal_bug_seed_launches_dependants(self):
    graph = RelationshipGraph(issues={
      "1": titled("Bug: Seed"),
      "2": titled("Implement dependant", 1),
      "3": titled("Implement next", 2),
    })
    plan = decompose_lanes(graph, [1])
    self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_terminal_refactor_seed_launches_dependants(self):
    graph = RelationshipGraph(issues={
      "1": titled("Refactor: Seed"),
      "2": titled("Implement dependant", 1),
    })
    plan = decompose_lanes(graph, [1])
    self.assertEqual(plan.closure, ("1", "2"))

  def test_multiple_seeds_union_overlapping_and_disjoint_projections(self):
    graph = RelationshipGraph(issues={
      "1": titled("Implement shared root"),
      "2": titled("Implement first seed", 1),
      "3": titled("Implement sibling", 1),
      "10": titled("Refactor: Other root"),
      "11": titled("Implement second seed", 10),
      "12": titled("Unrelated refactor dependant", 10),
    })
    plan = decompose_lanes(graph, [2, 11])
    self.assertEqual(
      plan.closure,
      ("1", "2", "3", "10", "11"),
    )

  def test_canonical_413_projects_exact_six_nodes(self):
    root = Path(__file__).resolve().parents[1]
    graph = RelationshipStore(root).read().graph
    plan = decompose_lanes(graph, [413])
    self.assertEqual(
      plan.closure,
      ("409", "410", "411", "412", "413", "456"),
    )

  def test_repeated_projection_is_deterministic(self):
    graph = RelationshipGraph(issues={
      "1": titled("Implement root"),
      "2": titled("Implement seed", 1),
      "3": titled("Implement sibling", 1),
    })
    self.assertEqual(
      decompose_lanes(graph, [2]),
      decompose_lanes(graph, [2]),
    )


if __name__ == "__main__":
  unittest.main()
