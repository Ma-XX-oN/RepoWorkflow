import unittest

from repo_workflow.lane_selection_cli import _selection_arguments
from repo_workflow.lane_traversal import (
  FollowPolicy,
  LaneTraversalError,
  group_kind,
  parse_follow_arguments,
)


class LaneTraversalTests(unittest.TestCase):
  def test_group_kind_uses_synchronized_title_prefixes(self):
    self.assertEqual(group_kind("Feature: One"), "feature")
    self.assertEqual(group_kind("Epic: Two"), "epic")
    self.assertEqual(group_kind("Initiative: Three"), "initiative")
    self.assertIsNone(group_kind("Issue 4"))
    self.assertIsNone(group_kind("feature: lower-case is ordinary"))

  def test_omitted_follow_count_defaults_to_one(self):
    self.assertEqual(
      parse_follow_arguments([("feature", None)]),
      FollowPolicy(feature=1),
    )

  def test_positive_follow_count_is_accepted(self):
    self.assertEqual(
      parse_follow_arguments([("epic", "3")]),
      FollowPolicy(epic=3),
    )

  def test_zero_and_malformed_follow_counts_are_rejected(self):
    for value in ("0", "-1", "x", ""):
      with self.subTest(value=value):
        with self.assertRaises(LaneTraversalError):
          parse_follow_arguments([("epic", value)])

  def test_distinct_type_follow_flags_compose(self):
    self.assertEqual(
      parse_follow_arguments([
        ("feature", None),
        ("epic", "2"),
        ("initiative", None),
      ]),
      FollowPolicy(feature=1, epic=2, initiative=1),
    )

  def test_duplicate_same_type_is_rejected(self):
    with self.assertRaisesRegex(LaneTraversalError, "duplicate"):
      parse_follow_arguments([
        ("feature", None),
        ("feature", "2"),
      ])

  def test_selection_parser_removes_follow_from_focus_roots(self):
    positional, as_json, refresh, follow, show_children = _selection_arguments([
      "5",
      "--follow", "epic", "2",
      "6",
      "--refresh",
      "--json",
    ])
    self.assertEqual(positional, ["5", "6"])
    self.assertTrue(as_json)
    self.assertTrue(refresh)
    self.assertEqual(follow, FollowPolicy(epic=2))
    self.assertIsNone(show_children)

  def test_selection_parser_keeps_omitted_follow_distinct_from_default(self):
    positional, as_json, refresh, follow, show_children = _selection_arguments(["5"])
    self.assertEqual(positional, ["5"])
    self.assertFalse(as_json)
    self.assertFalse(refresh)
    self.assertIsNone(follow)
    self.assertIsNone(show_children)


if __name__ == "__main__":
  unittest.main()
