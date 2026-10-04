import unittest

from repo_workflow.relationships import (
  RelationshipGraph,
  RelationshipSchemaError,
  ready_issues,
)


class RelationshipGraphTests(unittest.TestCase):
  def test_round_trip_preserves_distinct_relationship_types(self):
    value = {
      "schema_version": 2,
      "issues": {
        "10": {
          "umbrella": "1",
          "shared_umbrellas": ["50"],
          "depends_on": ["7"],
          "umbrella_depends_on": ["40"],
          "parent": "issue-7",
        },
        "7": {
          "umbrella": "1",
          "shared_umbrellas": [],
          "depends_on": [],
          "umbrella_depends_on": [],
          "parent": "main",
        },
      },
    }
    graph = RelationshipGraph.from_json_value(value)

    self.assertEqual(graph.to_json_value(), value)
    issue = graph.issue("10")
    self.assertEqual(issue.umbrella, "1")
    self.assertEqual(issue.shared_umbrellas, ("50",))
    self.assertEqual(issue.depends_on, ("7",))
    self.assertEqual(issue.umbrella_depends_on, ("40",))
    self.assertEqual(issue.parent, "issue-7")

  def test_umbrella_membership_and_attachment_do_not_block_readiness(self):
    graph = RelationshipGraph.from_json_value({
      "schema_version": 2,
      "issues": {
        "10": {
          "umbrella": "1",
          "shared_umbrellas": ["50"],
          "depends_on": [],
          "umbrella_depends_on": [],
          "parent": "issue-9",
        },
      },
    })

    self.assertEqual(ready_issues(graph, completed=set()), ("10",))

  def test_unresolved_direct_leaf_dependency_blocks_until_complete(self):
    graph = RelationshipGraph.from_json_value({
      "schema_version": 2,
      "issues": {
        "10": {
          "umbrella": "1",
          "shared_umbrellas": [],
          "depends_on": ["7"],
          "umbrella_depends_on": [],
          "parent": "main",
        },
        "7": {
          "umbrella": "1",
          "shared_umbrellas": [],
          "depends_on": [],
          "umbrella_depends_on": [],
          "parent": "main",
        },
      },
    })

    self.assertEqual(ready_issues(graph, completed=set()), ("7",))
    self.assertEqual(ready_issues(graph, completed={"7"}), ("10",))

  def test_parent_never_becomes_dependency(self):
    graph = RelationshipGraph.from_json_value({
      "schema_version": 2,
      "issues": {
        "10": {
          "umbrella": None,
          "shared_umbrellas": [],
          "depends_on": [],
          "umbrella_depends_on": [],
          "parent": "issue-7",
        },
      },
    })

    self.assertEqual(ready_issues(graph, completed=set()), ("10",))

  def test_direct_dependency_cycle_is_rejected(self):
    with self.assertRaisesRegex(
      RelationshipSchemaError,
      "direct dependency cycle",
    ):
      RelationshipGraph.from_json_value({
        "schema_version": 2,
        "issues": {
          "1": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": ["2"],
            "umbrella_depends_on": [],
            "parent": "main",
          },
          "2": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": ["1"],
            "umbrella_depends_on": [],
            "parent": "main",
          },
        },
      })

  def test_unknown_direct_dependency_is_rejected(self):
    with self.assertRaisesRegex(
      RelationshipSchemaError,
      "unknown direct dependency",
    ):
      RelationshipGraph.from_json_value({
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": ["99"],
            "umbrella_depends_on": [],
            "parent": "main",
          },
        },
      })

  def test_self_relationships_are_rejected(self):
    with self.assertRaises(RelationshipSchemaError):
      RelationshipGraph.from_json_value({
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": "10",
            "shared_umbrellas": [],
            "depends_on": [],
            "umbrella_depends_on": [],
            "parent": "main",
          },
        },
      })

  def test_schema_version_must_be_supported(self):
    with self.assertRaisesRegex(
      RelationshipSchemaError,
      "unsupported relationship schema version",
    ):
      RelationshipGraph.from_json_value({
        "schema_version": 2,
        "issues": {},
      })


if __name__ == "__main__":
  unittest.main()
