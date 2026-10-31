from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.validate as validate_script


class ValidateScriptTests(unittest.TestCase):
  def test_malformed_committed_ticket_state_blocks_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      state = root / ".repoworkflow"
      state.mkdir()
      (state / "tickets.csv").write_text(
        (
          "issue,title,dependencies\n"
          "10,Valid,\n"
          "20,Missing third field\n"
        ),
        encoding="utf-8",
      )
      with (
        patch.object(validate_script, "ROOT", root),
        patch.object(validate_script, "run") as run,
      ):
        self.assertEqual(validate_script.main(), 1)
      run.assert_not_called()

  def test_imported_testcase_does_not_cross_stage_boundary(self):
    class Owned(unittest.TestCase):
      def test_ok(self):
        pass

    class External(unittest.TestCase):
      def test_other(self):
        pass

    External.__module__ = "tests.test_integration_only"
    loaded = unittest.TestSuite([
      Owned("test_ok"), Owned("test_ok"), External("test_other"),
    ])
    with patch.object(
      validate_script.unittest.defaultTestLoader,
      "loadTestsFromNames",
      return_value=loaded,
    ):
      result = validate_script.unique_suite(("tests.test_validate_script",))
    self.assertEqual(result.countTestCases(), 1)

  def test_missing_module_is_not_filtered_out(self):
    suite = validate_script.unique_suite(
      ("tests.test_missing_catalogue_module_109_negative",)
    )
    self.assertEqual(suite.countTestCases(), 1)
    result = unittest.TestResult()
    suite.run(result)
    self.assertEqual(len(result.errors), 1)

  def test_explicit_empty_dependency_field_reaches_test_execution(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      state = root / ".repoworkflow"
      state.mkdir()
      (state / "tickets.csv").write_text(
        "issue,title,dependencies\n10,Valid,\n",
        encoding="utf-8",
      )
      suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
      with (
        patch.object(validate_script, "ROOT", root),
        patch.object(validate_script, "selected_modules",
                     return_value=("tests.test_validate_script",)) as selected,
        patch.object(validate_script, "unique_suite", return_value=suite),
        patch.object(validate_script, "run", return_value=0) as run,
      ):
        self.assertEqual(validate_script.main(), 0)
      run.assert_called_once()
      selected.assert_called_once_with(root, "regression")


if __name__ == "__main__":
  unittest.main()
