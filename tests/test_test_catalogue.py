from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.test_catalogue import (
  CATALOGUE_PATH,
  TestCatalogueError,
  load_test_catalogue,
  parse_test_catalogue,
)


class TestCatalogueTests(unittest.TestCase):
  def value(self):
    return {
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [
        {
          "test-harness": "unittest",
          "issue-474-catalogue": {
            "type": "regression",
            "name": "tests.test_test_catalogue",
          },
          "issue-456-grammar": {
            "type": "regression",
            "name": "tests.test_quantified_grammar",
          },
        },
      ],
      "aliases": {
        "command-grammar": [
          "issue-456-grammar",
          "issue-456-grammar",
        ],
        "catalogue": [
          "issue-474-catalogue",
        ],
      },
    }

  def test_aliases_expand_by_sorted_union_and_deduplicate(self):
    catalogue = parse_test_catalogue(self.value())
    self.assertEqual(
      catalogue.expand_aliases(["catalogue", "command-grammar"]),
      ("issue-456-grammar", "issue-474-catalogue"),
    )

  def test_alias_names_are_deterministic(self):
    catalogue = parse_test_catalogue(self.value())
    self.assertEqual(
      catalogue.alias_names(),
      ("catalogue", "command-grammar"),
    )

  def test_unknown_alias_fails_closed(self):
    catalogue = parse_test_catalogue(self.value())
    with self.assertRaisesRegex(TestCatalogueError, "unknown test alias"):
      catalogue.expand_aliases(["missing"])

  def test_unknown_alias_member_group_fails_closed(self):
    value = self.value()
    value["aliases"]["broken"] = ["issue-999-missing"]
    with self.assertRaisesRegex(TestCatalogueError, "unknown test group"):
      parse_test_catalogue(value)

  def test_duplicate_group_key_fails_closed(self):
    value = self.value()
    value["tests"].append({
      "test-harness": "unittest",
      "issue-474-catalogue": {
        "type": "regression",
        "name": "duplicate",
      },
    })
    with self.assertRaisesRegex(TestCatalogueError, "duplicate test group"):
      parse_test_catalogue(value)

  def test_aliases_are_not_recursive(self):
    value = self.value()
    value["aliases"]["recursive"] = ["command-grammar"]
    with self.assertRaisesRegex(TestCatalogueError, "unknown test group"):
      parse_test_catalogue(value)

  def test_load_uses_ci_tests_json(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      path = root / CATALOGUE_PATH
      path.parent.mkdir(parents=True)
      path.write_text(json.dumps(self.value()), encoding="utf-8")
      loaded = load_test_catalogue(root)
      self.assertIn("issue-474-catalogue", loaded.groups)

  def test_missing_catalogue_reports_authoritative_path(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      with self.assertRaisesRegex(TestCatalogueError, r"\.ci.*tests\.json"):
        load_test_catalogue(root)


if __name__ == "__main__":
  unittest.main()
