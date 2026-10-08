import unittest

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.lane_traversal import FollowPolicy, ShowChildrenPolicy
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(title: str = "Issue", *dependencies: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(value) for value in dependencies))


class LaneFollowActivationTests(unittest.TestCase):
  def test_no_follow_keeps_single_explicit_seed_only(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation("Issue 2", 1),
      "3": relation("Issue 3", 2),
    })

    plan = decompose_lanes(graph, [2])

    self.assertEqual(plan.selected, ("2",))
    self.assertEqual(plan.closure, ("2",))

  def test_no_follow_keeps_multiple_explicit_seeds_only(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation("Issue 2", 1),
      "3": relation(),
      "4": relation("Issue 4", 3),
    })

    plan = decompose_lanes(graph, [2, 4])

    self.assertEqual(plan.selected, ("2", "4"))
    self.assertEqual(plan.closure, ("2", "4"))

  def test_valid_follow_form_enables_ordinary_traversal(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation("Issue 2", 1),
      "3": relation("Issue 3", 2),
    })

    plan = decompose_lanes(
      graph,
      [2],
      follow=FollowPolicy(feature=1),
    )

    self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_no_follow_keeps_group_seed_only(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation("Feature: Seed", 1),
      "3": relation("Issue 3", 2),
    })

    plan = decompose_lanes(graph, [2])

    self.assertEqual(plan.closure, ("2",))

  def test_show_children_does_not_enable_ordinary_traversal(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation("Issue 2", 1),
      "3": relation("Feature: Boundary", 2),
      "4": relation("Issue 4", 3),
    })

    plan = decompose_lanes(
      graph,
      [1],
      show_children=ShowChildrenPolicy(feature=True),
    )

    self.assertEqual(plan.closure, ("1",))


if __name__ == "__main__":
  unittest.main()
