import unittest

from repo_workflow.relationships import (
  RelationshipGraph,
  RelationshipSchemaError,
  ready_issues,
)


def graph(value):
  return RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": value,
  })


class RelationshipGraphTests(unittest.TestCase):
  def test_round_trip_preserves_exact_title_and_direct_dependencies(self):
    value = {
      "schema_version": 3,
      "issues": {
        "7": {"title": "Seven", "depends_on": []},
        "10": {"title": "Feature: Ten", "depends_on": ["7"]},
      },
    }
    result = RelationshipGraph.from_json_value(value)

    self.assertEqual(result.to_json_value(), value)
    self.assertEqual(result.issue(10).title, "Feature: Ten")
    self.assertEqual(result.issue(10).depends_on, ("7",))

  def test_removed_relationship_fields_are_rejected(self):
    for field, value in (
      ("umbrella", "1"),
      ("shared_umbrellas", ["50"]),
      ("umbrella_depends_on", ["40"]),
      ("parent", "main"),
    ):
      with self.subTest(field=field):
        with self.assertRaisesRegex(
          RelationshipSchemaError,
          "expected title and depends_on only",
        ):
          graph({
            "10": {
              "title": "Ten",
              "depends_on": [],
              field: value,
            },
          })

  def test_title_prefixes_have_no_readiness_semantics(self):
    value = graph({
      "10": {"title": "Initiative: Ten", "depends_on": []},
      "20": {"title": "Epic: Twenty", "depends_on": []},
      "30": {"title": "Feature: Thirty", "depends_on": []},
    })
    self.assertEqual(
      ready_issues(value, completed=set()),
      ("10", "20", "30"),
    )

  def test_unresolved_direct_dependency_blocks_until_complete(self):
    value = graph({
      "7": {"title": "Seven", "depends_on": []},
      "10": {"title": "Ten", "depends_on": ["7"]},
    })
    self.assertEqual(ready_issues(value, completed=set()), ("7",))
    self.assertEqual(ready_issues(value, completed={"7"}), ("10",))

  def test_direct_dependency_cycle_is_rejected(self):
    with self.assertRaisesRegex(
      RelationshipSchemaError,
      "direct dependency cycle",
    ):
      graph({
        "1": {"title": "One", "depends_on": ["2"]},
        "2": {"title": "Two", "depends_on": ["1"]},
      })

  def test_unknown_direct_dependency_is_rejected(self):
    with self.assertRaisesRegex(
      RelationshipSchemaError,
      "unknown direct dependency",
    ):
      graph({
        "10": {"title": "Ten", "depends_on": ["99"]},
      })

  def test_self_dependency_is_rejected(self):
    with self.assertRaisesRegex(RelationshipSchemaError, "self direct"):
      graph({
        "10": {"title": "Ten", "depends_on": ["10"]},
      })

  def test_empty_title_and_duplicate_dependencies_fail_closed(self):
    with self.assertRaisesRegex(RelationshipSchemaError, "title"):
      graph({"10": {"title": "", "depends_on": []}})
    with self.assertRaisesRegex(RelationshipSchemaError, "duplicates"):
      graph({
        "7": {"title": "Seven", "depends_on": []},
        "10": {"title": "Ten", "depends_on": ["7", "7"]},
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
