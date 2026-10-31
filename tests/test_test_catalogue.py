from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.test_catalogue import (
  CATALOGUE_PATH,
  TestCatalogueError,
  load_test_catalogue,
  parse_test_catalogue,
  stage_groups,
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

  def test_stage_selection_is_catalogue_owned_and_deduplicated(self):
    value = self.value()
    value["tests"][0]["issue-474-alias"] = {
      "type": "regression", "name": "tests.test_test_catalogue",
    }
    value["tests"][0]["issue-474-integration"] = {
      "type": "integration", "name": "tests.test_completion",
    }
    value["tests"][0]["issue-474-manual--review"] = {
      "type": "manual", "instructions": "Inspect",
      "expected_result": "PASS",
    }
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      path = root / CATALOGUE_PATH
      path.parent.mkdir()
      path.write_text(json.dumps(value), encoding="utf-8")
      self.assertEqual(stage_groups(root, "regression"), (
        "issue-456-grammar", "issue-474-catalogue",
      ))
      self.assertEqual(stage_groups(root, "integration"), (
        "issue-456-grammar", "issue-474-catalogue",
        "issue-474-integration",
      ))
      with self.assertRaisesRegex(TestCatalogueError, "unknown retained"):
        stage_groups(root, "temporary")

  def test_aliases_expand_by_sorted_union_and_deduplicate(self):
    catalogue = parse_test_catalogue(self.value())
    self.assertEqual(
      catalogue.expand_aliases(["catalogue", "command-grammar"]),
      ("issue-456-grammar", "issue-474-catalogue"),
    )

  def test_alias_groups_add_to_required_issue_groups(self):
    catalogue = parse_test_catalogue(self.value())
    self.assertEqual(
      catalogue.verification_groups(
        ["issue-474-catalogue"],
        ["command-grammar"],
      ),
      ("issue-456-grammar", "issue-474-catalogue"),
    )

  def test_unknown_required_group_fails_closed(self):
    catalogue = parse_test_catalogue(self.value())
    with self.assertRaisesRegex(TestCatalogueError, "unknown required test group"):
      catalogue.verification_groups(["issue-999-missing"], [])

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

  def test_integration_is_an_authoritative_stage(self):
    value = self.value()
    value["tests"][0]["issue-474-catalogue"]["type"] = "integration"
    self.assertIn("issue-474-catalogue", parse_test_catalogue(value).groups)

  def test_legacy_invariant_type_is_rejected(self):
    value = self.value()
    value["tests"][0]["issue-474-catalogue"]["type"] = "invariant"
    with self.assertRaisesRegex(TestCatalogueError, "regression, integration or manual"):
      parse_test_catalogue(value)

  def test_manual_integration_case_type_is_retained(self):
    value = self.value()
    value["tests"][0]["issue-474-catalogue"] = {
      "type": "manual",
      "instructions": "Inspect the candidate.",
      "expected_result": "Expected terminal observed.",
    }
    self.assertIn("issue-474-catalogue", parse_test_catalogue(value).groups)

  def test_undefined_type_is_rejected(self):
    value = self.value()
    del value["tests"][0]["issue-474-catalogue"]["type"]
    with self.assertRaisesRegex(TestCatalogueError, "regression, integration or manual"):
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
