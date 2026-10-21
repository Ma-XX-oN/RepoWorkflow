"""Contract tests for manual integration declarations (RWF #700)."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.manual_test_catalogue import (
  ManualCase,
  ManualCatalogueError,
  find_manual_case,
  read_manual_cases,
)
from repo_workflow.test_catalogue import load_test_catalogue


class ManualCatalogueTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.path = self.root / ".ci/tests.json"
    self.path.parent.mkdir()

  def base(self):
    return {
      "test-harnesses": {
        "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]},
      },
      "tests": [{
        "test-harness": "unittest",
        "issue-700-automatic": {
          "type": "regression", "name": "tests.test_test_catalogue",
        },
        "issue-701-automatic": {
          "type": "regression", "name": "tests.test_test_catalogue",
        },
      }],
      "aliases": {"automatic": ["issue-700-automatic"]},
    }

  def manual(self, name="issue-700-manual--sample", **updates):
    value = {
      "type": "manual",
      "instructions": "Look at the exact source SHA.",
      "expected_result": "The source SHA is unchanged.",
    }
    value.update(updates)
    return name, value

  def write(self, value):
    self.path.write_text(json.dumps(value, indent=2), encoding="utf-8")

  def value_with(self, *cases):
    value = self.base()
    for name, metadata in cases:
      value["tests"][0][name] = metadata
    return value

  def test_no_manual_entries_returns_empty_and_preserves_automated_groups(self):
    self.write(self.base())
    self.assertEqual(read_manual_cases(self.root, 700), ())
    self.assertIn("issue-700-automatic", load_test_catalogue(self.root).groups)
    self.assertEqual(
      load_test_catalogue(self.root).expand_aliases(["automatic"]),
      ("issue-700-automatic",),
    )

  def test_one_manual_case_is_frozen_and_lookup_exact(self):
    name, metadata = self.manual()
    self.write(self.value_with((name, metadata)))
    cases = read_manual_cases(self.root, 700)
    self.assertEqual(len(cases), 1)
    self.assertIsInstance(cases[0], ManualCase)
    self.assertEqual(cases[0].name, name)
    self.assertEqual(cases[0].instructions, metadata["instructions"])
    self.assertEqual(cases[0].expected_result, metadata["expected_result"])
    self.assertRegex(cases[0].definition_digest, r"^[0-9a-f]{64}$")
    self.assertEqual(find_manual_case(self.root, 700, name), cases[0])
    with self.assertRaises((AttributeError, TypeError)):
      cases[0].instructions = "forged"

  def test_order_is_lexicographic_independent_of_manifest_layout(self):
    names = ["issue-700-manual--z", "issue-700-manual--9", "issue-700-manual--Alpha"]
    value = self.value_with(*(self.manual(name) for name in names))
    self.write(value)
    first = read_manual_cases(self.root, 700)
    self.assertEqual([case.name for case in first], sorted(names))
    value["tests"][0] = dict(reversed(list(value["tests"][0].items())))
    self.write(value)
    second = read_manual_cases(self.root, 700)
    self.assertEqual(first, second)

  def test_other_issues_not_selected_and_foreign_explicit_lookup_rejected(self):
    value = self.value_with(self.manual("issue-701-manual--foreign"))
    self.write(value)
    self.assertEqual(read_manual_cases(self.root, 700), ())
    self.assertEqual(len(read_manual_cases(self.root, 701)), 1)
    with self.assertRaisesRegex(ManualCatalogueError, "not declared for issue 700"):
      find_manual_case(self.root, 700, "issue-701-manual--foreign")

  def test_substring_in_automatic_group_is_not_manual(self):
    value = self.value_with((
      "issue-700-automatic-manual--spoof",
      {"type": "regression", "name": "tests.test_test_catalogue"},
    ))
    self.write(value)
    self.assertEqual(read_manual_cases(self.root, 700), ())

  def test_valid_name_without_manual_type_is_rejected(self):
    value = self.value_with((
      "issue-700-manual--spoof",
      {"type": "regression", "name": "tests.test_test_catalogue"},
    ))
    self.write(value)
    with self.assertRaisesRegex(ManualCatalogueError, "requires type=manual"):
      read_manual_cases(self.root, 700)

  def test_invalid_issue_inputs_rejected(self):
    self.write(self.base())
    for issue in (0, -1, "700", True, 1.0):
      with self.subTest(issue=issue):
        with self.assertRaisesRegex(ManualCatalogueError, "positive integer"):
          read_manual_cases(self.root, issue)

  def test_name_grammar_rejects_invalid_or_ambiguous_manual_entries(self):
    names = (
      "issue-0-manual--bad", "issue-0700-manual--bad",
      "issue-seven-manual--bad", "issue-700-manual--",
      "issue-700-manual---bad", "issue-700-manual--bad space",
      "issue-700-manual--bad!", "issue-700-manual--å",
      "issue-700-manual--bad.dot", "manual--standalone",
    )
    for name in names:
      with self.subTest(name=name):
        self.write(self.value_with(self.manual(name)))
        with self.assertRaisesRegex(ManualCatalogueError, "invalid manual case name"):
          read_manual_cases(self.root, 700)

  def test_missing_or_invalid_metadata_is_rejected(self):
    for field in ("type", "instructions", "expected_result"):
      for altered in (None, "", "  ", [], 0, False):
        name, metadata = self.manual()
        metadata[field] = altered
        self.write(self.value_with((name, metadata)))
        with self.subTest(field=field, altered=altered):
          with self.assertRaises(ManualCatalogueError):
            read_manual_cases(self.root, 700)
    name, metadata = self.manual()
    for field in ("instructions", "expected_result", "type"):
      changed = dict(metadata)
      changed.pop(field)
      self.write(self.value_with((name, changed)))
      with self.subTest(missing=field):
        with self.assertRaises(ManualCatalogueError):
          read_manual_cases(self.root, 700)

  def test_executable_metadata_and_unknown_fields_are_rejected(self):
    for field, value in (
      ("name", "tests.some_executable"),
      ("command", "rm -rf /"),
      ("code", "print('PASS')"),
      ("other", "ambiguous"),
    ):
      name, metadata = self.manual()
      metadata[field] = value
      self.write(self.value_with((name, metadata)))
      with self.subTest(field=field):
        with self.assertRaisesRegex(ManualCatalogueError, "requires exactly"):
          read_manual_cases(self.root, 700)

  def test_manual_case_in_automated_alias_is_rejected(self):
    value = self.value_with(self.manual())
    value["aliases"]["bad"] = ["issue-700-manual--sample"]
    self.write(value)
    with self.assertRaisesRegex(ManualCatalogueError, "cannot include a manual case"):
      read_manual_cases(self.root, 700)

  def test_manual_case_with_runnable_command_override_is_rejected(self):
    value = self.value_with(self.manual())
    value["tests"][0]["command"] = "python"
    self.write(value)
    with self.assertRaisesRegex(ManualCatalogueError, "executable command override"):
      read_manual_cases(self.root, 700)

  def test_duplicate_group_names_across_declarations_fail(self):
    value = self.value_with(self.manual())
    value["tests"].append({"test-harness": "unittest", **dict([self.manual()])})
    self.write(value)
    with self.assertRaisesRegex(ManualCatalogueError, "duplicate test group"):
      read_manual_cases(self.root, 700)

  def test_duplicate_json_keys_in_same_object_fail(self):
    self.path.write_text('''{
      "test-harnesses": {"unittest": {}},
      "tests": [{"test-harness": "unittest",
        "issue-700-manual--one": {
          "type": "manual", "type": "manual",
          "instructions": "inspect", "expected_result": "PASS"}}]
    }''')
    with self.assertRaisesRegex(ManualCatalogueError, "duplicate JSON key: type"):
      read_manual_cases(self.root, 700)

  def test_duplicate_top_level_json_key_fails(self):
    self.path.write_text('{"tests":[],"tests":[],"test-harnesses":{}}')
    with self.assertRaisesRegex(ManualCatalogueError, "duplicate JSON key: tests"):
      read_manual_cases(self.root, 700)

  def test_invalid_catalogue_and_unknown_harness_fail(self):
    self.path.unlink(missing_ok=True)
    with self.assertRaisesRegex(ManualCatalogueError, "cannot read"):
      read_manual_cases(self.root, 700)
    for contents in ("{", "[]", '{"tests": [], "test-harnesses": []}'):
      self.path.write_text(contents)
      with self.subTest(contents=contents):
        with self.assertRaises(ManualCatalogueError):
          read_manual_cases(self.root, 700)
    value = self.value_with(self.manual())
    value["tests"][0]["test-harness"] = "missing"
    self.write(value)
    with self.assertRaisesRegex(ManualCatalogueError, "unknown test harness"):
      read_manual_cases(self.root, 700)

  def test_definition_digest_is_stable_and_suffers_drift_on_change(self):
    name, metadata = self.manual()
    value = self.value_with((name, metadata))
    self.write(value)
    original = read_manual_cases(self.root, 700)[0].definition_digest
    self.assertEqual(len(bytes.fromhex(original)), hashlib.sha256().digest_size)
    self.path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    self.assertEqual(read_manual_cases(self.root, 700)[0].definition_digest, original)
    for field in ("instructions", "expected_result"):
      changed = self.value_with((name, {**metadata, field: metadata[field] + " new"}))
      self.write(changed)
      self.assertNotEqual(read_manual_cases(self.root, 700)[0].definition_digest, original)
    changed = self.value_with((name, metadata))
    changed["test-harnesses"]["unittest"]["command"] = "python3"
    self.write(changed)
    self.assertNotEqual(read_manual_cases(self.root, 700)[0].definition_digest, original)
    changed = self.value_with((name, metadata))
    changed["tests"][0]["issue-701-automatic"]["name"] = "different"
    self.write(changed)
    self.assertEqual(read_manual_cases(self.root, 700)[0].definition_digest, original)

  def test_no_mutation_or_command_execution_for_listing_and_lookup(self):
    value = self.value_with(self.manual())
    self.write(value)
    before = self.path.read_bytes()
    files_before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
    with patch("subprocess.run", side_effect=AssertionError("spawned command")), \
         patch("subprocess.Popen", side_effect=AssertionError("spawned command")):
      self.assertEqual(len(read_manual_cases(self.root, 700)), 1)
      self.assertEqual(
        find_manual_case(self.root, 700, "issue-700-manual--sample").name,
        "issue-700-manual--sample",
      )
    self.assertEqual(self.path.read_bytes(), before)
    self.assertEqual(
      sorted(p.relative_to(self.root) for p in self.root.rglob("*")),
      files_before,
    )


if __name__ == "__main__":
  unittest.main()
