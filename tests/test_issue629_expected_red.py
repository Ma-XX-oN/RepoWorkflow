"""Independent expected-RED declaration contract and negative partitions."""

import json
from pathlib import Path
import tempfile
import unittest


try:
  from repo_workflow.test_red_declaration import red_declaration
except ImportError:
  red_declaration = None


class ExpectedRedDeclarationAcceptanceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if red_declaration is None:
      raise unittest.SkipTest("PENDING #545: expected-RED reader unavailable")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / ".ci").mkdir()
    self.group = "issue-629-expected-failure"

  def write(self, declaration, *, raw=None):
    path = self.root / ".ci/tests.json"
    spec = {
      "test-harnesses": {"unittest": {"command": "python",
        "layout": ["-m", "unittest", "$test"]}},
      "tests": [{
        "test-harness": "unittest",
        self.group: {
          "type": "regression",
          "name": "smoke_case",
          **({"expected-red": declaration} if declaration is not None else {}),
        },
      }],
    }
    path.write_text(raw if raw is not None else json.dumps(spec))
    return path

  def test_positive_exact_code_and_literal_signature(self):
    self.write({"exit-code": 1, "output-contains": "expected sentinel 629"})
    expectation, error = red_declaration(self.root, self.group)
    self.assertEqual(error, "")
    self.assertEqual(expectation.exit_code, 1)
    self.assertEqual(expectation.output_contains, "expected sentinel 629")

  def test_absent_declaration_not_inferred_from_failure(self):
    self.write(None)
    expectation, error = red_declaration(self.root, self.group)
    self.assertIsNone(expectation)
    self.assertTrue(error)

  def test_invalid_exit_code_classes_rejected(self):
    for value in (True, False, 0, -1, 1.0, "1", None):
      with self.subTest(value=value):
        self.write({"exit-code": value, "output-contains": "specific sentinel"})
        expectation, error = red_declaration(self.root, self.group)
        self.assertIsNone(expectation)
        self.assertTrue(error)

  def test_generic_empty_and_nonutF8_equivalent_signatures_rejected(self):
    for value in ("", "   ", "Error", "FAILED", "Traceback",
                  "AssertionError", "Failure", None, 5, "\ud800"):
      with self.subTest(value=repr(value)):
        # json.dumps safely encodes the surrogate; declaration must reject it.
        self.write({"exit-code": 1, "output-contains": value})
        expectation, error = red_declaration(self.root, self.group)
        self.assertIsNone(expectation)
        self.assertTrue(error)

  def test_missing_unknown_or_duplicate_fields_rejected(self):
    cases = (
      {"exit-code": 1},
      {"output-contains": "sentinel"},
      {"exit-code": 1, "output-contains": "sentinel", "regex": ".*"},
    )
    for fields in cases:
      with self.subTest(fields=fields):
        self.write(fields)
        expectation, error = red_declaration(self.root, self.group)
        self.assertIsNone(expectation)
        self.assertTrue(error)
    self.write(None, raw='{"tests":[{"issue-629-expected-failure":'
      '{"expected-red":{"exit-code":1,"exit-code":2,'
      '"output-contains":"sentinel"}}]}')
    expectation, error = red_declaration(self.root, self.group)
    self.assertIsNone(expectation)
    self.assertTrue(error)

  def test_malformed_catalogue_fails_closed(self):
    self.write(None, raw="{bad json")
    expectation, error = red_declaration(self.root, self.group)
    self.assertIsNone(expectation)
    self.assertTrue(error)


if __name__ == "__main__":
  unittest.main()
