import unittest

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.lane_traversal import FollowPolicy, ShowChildrenPolicy
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def titled(title: str, *dependencies: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(value) for value in dependencies))


class LaneShowChildrenTests(unittest.TestCase):
  def test_stopped_feature_shows_one_immediate_child_layer(self):
    graph = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Boundary", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Issue 4", 3),
    })
    plan = decompose_lanes(
      graph,
      [1],
      follow=FollowPolicy(epic=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(plan.closure, ("1", "2", "3"))
    self.assertNotIn("4", plan.closure)

  def test_group_matches_feature_epic_and_initiative(self):
    cases = (
      ("Feature: F", FollowPolicy(epic=1)),
      ("Epic: E", FollowPolicy(feature=1)),
      ("Initiative: I", FollowPolicy(feature=1)),
    )
    for title, follow in cases:
      with self.subTest(title=title):
        graph = RelationshipGraph(issues={
          "1": titled("Issue 1"),
          "2": titled(title, 1),
          "3": titled("Issue 3", 2),
        })
        plan = decompose_lanes(
          graph,
          [1],
          follow=follow,
          show_children=ShowChildrenPolicy(group=True),
        )
        self.assertEqual(plan.closure, ("1", "2", "3"))

  def test_type_specific_policy_does_not_match_other_group_kind(self):
    graph = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Epic: Boundary", 1),
      "3": titled("Issue 3", 2),
    })
    plan = decompose_lanes(
      graph,
      [1],
      follow=FollowPolicy(feature=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(plan.closure, ("1", "2"))

  def test_followed_boundary_needs_no_display_only_expansion(self):
    graph = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Boundary", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Issue 4", 3),
    })
    plan = decompose_lanes(
      graph,
      [1],
      follow=FollowPolicy(feature=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))

  def test_display_child_also_reached_normally_keeps_traversing(self):
    graph = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Boundary", 1),
      "3": titled("Issue 3", 1, 2),
      "4": titled("Issue 4", 3),
    })
    plan = decompose_lanes(
      graph,
      [1],
      follow=FollowPolicy(epic=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertIn("4", plan.closure)
    self.assertEqual(len(plan.closure), len(set(plan.closure)))

  def test_selected_group_is_not_treated_as_stopped_boundary(self):
    graph = RelationshipGraph(issues={
      "1": titled("Issue 1"),
      "2": titled("Feature: Seed", 1),
      "3": titled("Issue 3", 2),
      "4": titled("Issue 4", 3),
    })
    plan = decompose_lanes(
      graph,
      [2],
      follow=FollowPolicy(epic=1),
      show_children=ShowChildrenPolicy(feature=True),
    )
    self.assertEqual(plan.closure, ("1", "2", "3", "4"))


if __name__ == "__main__":
  unittest.main()
