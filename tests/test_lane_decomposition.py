import unittest

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(*dependencies: int) -> IssueRelationships:
  return IssueRelationships(
    umbrella=None,
    shared_umbrellas=(),
    depends_on=tuple(str(value) for value in dependencies),
    umbrella_depends_on=(),
    parent=None,
  )


def graph(mapping: dict[int, tuple[int, ...]]) -> RelationshipGraph:
  return RelationshipGraph.from_json_value({
    "schema_version": 2,
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
