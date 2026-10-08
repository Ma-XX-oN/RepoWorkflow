import unittest

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.lane_traversal import FollowPolicy
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(*dependencies: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(value) for value in dependencies))


def titled(title: str, *dependencies: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(value) for value in dependencies))


def graph(mapping: dict[int, tuple[int, ...]]) -> RelationshipGraph:
  return RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      str(issue): relation(*dependencies).to_json_value()
      for issue, dependencies in mapping.items()
    },
  })


class LaneDecompositionTests(unittest.TestCase):
  def test_chain_is_one_lane(self):
    value = graph({1: (), 2: (1,), 3: (2,)})
    plan = decompose_lanes(value, [3])
    self.assertEqual([(x.name, x.issues) for x in plan.lanes], [
      ("A", ("1", "2", "3")),
    ])

  def test_selected_prerequisite_expands_to_complete_connected_component(self):
    value = graph({
      1: (), 2: (1,), 3: (1,), 4: (2, 3), 5: (4,), 9: ()
    })
    plan = decompose_lanes(value, [1])
    self.assertEqual(plan.selected, ("1",))
    self.assertEqual(plan.closure, ("1", "2", "3", "4", "5"))
    self.assertEqual(
      {issue for lane in plan.lanes for issue in lane.issues},
      {"1", "2", "3", "4", "5"},
    )
    self.assertNotIn("9", plan.closure)

  def test_middle_seed_expands_both_dependency_directions(self):
    value = graph({1: (), 2: (1,), 3: (2,), 4: (3,)})
    plan = decompose_lanes(value, [2])
    self.assertEqual(plan.selected, ("2",))
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))

  def test_multiple_seeds_union_disconnected_components(self):
    value = graph({
      1: (), 2: (1,), 3: (), 4: (3,), 5: ()
    })
    plan = decompose_lanes(value, [1, 4])
    self.assertEqual(plan.selected, ("1", "4"))
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))
    self.assertNotIn("5", plan.closure)

  def test_independent_leaves_are_distinct_lanes(self):
    value = graph({1: (), 2: (), 3: ()})
    plan = decompose_lanes(value, [3, 1, 2])
    self.assertEqual([(x.name, x.issues) for x in plan.lanes], [
      ("A", ("1",)), ("B", ("2",)), ("C", ("3",)),
    ])

  def test_branch_starts_new_lane_so_each_lane_is_a_path(self):
    value = graph({1: (), 2: (1,), 3: (1,)})
    plan = decompose_lanes(value, [2, 3])
    self.assertEqual([(x.name, x.issues) for x in plan.lanes], [
      ("A", ("1", "2")), ("B", ("3",)),
    ])

  def test_convergence_has_single_deterministic_owner(self):
    value = graph({105: (), 106: (), 107: (105, 106)})
    plan = decompose_lanes(value, [107])
    self.assertEqual(plan.owner(107), "A")
    self.assertEqual(sum("107" in lane.issues for lane in plan.lanes), 1)
    self.assertEqual([(x.name, x.issues) for x in plan.lanes], [
      ("A", ("105", "107")), ("B", ("106",)),
    ])

  def test_nested_convergence_remains_single_owner(self):
    value = graph({
      1: (), 2: (), 3: (1, 2), 4: (), 5: (3, 4), 6: (5,)
    })
    plan = decompose_lanes(value, [6])
    self.assertEqual(plan.owner(3), "A")
    self.assertEqual(plan.owner(5), "A")
    self.assertEqual(plan.owner(6), "A")
    self.assertEqual(len({i for lane in plan.lanes for i in lane.issues}), 6)

  def test_completed_dependencies_are_excluded_from_closure(self):
    value = graph({1: (), 2: (1,), 3: (2,)})
    plan = decompose_lanes(value, [3], completed=[1])
    self.assertEqual(plan.closure, ("2", "3"))
    self.assertEqual(plan.lanes[0].issues, ("2", "3"))

  def test_replay_is_independent_of_selection_order(self):
    value = graph({1: (), 2: (), 3: (1, 2), 4: ()})
    first = decompose_lanes(value, [4, 3])
    second = decompose_lanes(value, [3, 4, 3])
    self.assertEqual(first, second)

  def test_default_stops_at_encountered_group_boundary(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Boundary", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Issue 4", 3),
    })
    plan = decompose_lanes(value, [1])
    self.assertEqual(plan.closure, ("1", "2"))

  def test_group_seed_is_not_stopped_by_its_own_kind(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Boundary", 1),
      "3": titled("Issue 3", 2),
    })
    plan = decompose_lanes(value, [2])
    self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_type_follow_crosses_one_matching_boundary_per_path(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: First", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Feature: Second", 3),
      "5": titled("Issue 5", 4),
    })
    plan = decompose_lanes(
      value,
      [1],
      follow=FollowPolicy(feature=1),
    )
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))

  def test_type_follow_count_two_crosses_two_boundaries(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: First", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Feature: Second", 3),
      "5": titled("Issue 5", 4),
    })
    plan = decompose_lanes(
      value,
      [1],
      follow=FollowPolicy(feature=2),
    )
    self.assertEqual(plan.closure, ("1", "2", "3", "4", "5"))

  def test_group_budget_is_shared_across_mixed_group_kinds(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: First", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Epic: Second", 3),
      "5": titled("Issue 5", 4),
    })
    one = decompose_lanes(value, [1], follow=FollowPolicy(group=1))
    two = decompose_lanes(value, [1], follow=FollowPolicy(group=2))
    self.assertEqual(one.closure, ("1", "2", "3", "4"))
    self.assertEqual(two.closure, ("1", "2", "3", "4", "5"))

  def test_type_specific_follow_budgets_compose(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: First", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Epic: Second", 3),
      "5": titled("Issue 5", 4),
    })
    plan = decompose_lanes(
      value,
      [1],
      follow=FollowPolicy(feature=1, epic=1),
    )
    self.assertEqual(plan.closure, ("1", "2", "3", "4", "5"))

  def test_same_node_can_be_reached_with_different_remaining_budget(self):
    value = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Costly", 1),
      "3": titled("Issue 3", 1),
      "4": titled("Issue 4", 2, 3),
      "5": titled("Feature: Later", 4),
      "6": titled("Issue 6", 5),
    })
    plan = decompose_lanes(
      value,
      [1],
      follow=FollowPolicy(feature=1),
    )
    self.assertIn("6", plan.closure)

  def test_unknown_selected_issue_fails(self):
    value = graph({1: ()})
    with self.assertRaisesRegex(Exception, "unknown issue"):
      decompose_lanes(value, [2])

  def test_input_graph_is_not_mutated(self):
    value = graph({1: (), 2: (1,)})
    before = value.to_json_value()
    decompose_lanes(value, [2])
    self.assertEqual(value.to_json_value(), before)


if __name__ == "__main__":
  unittest.main()
