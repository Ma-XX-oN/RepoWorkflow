from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.results import evaluate_results, run_environment
from tests.support import RepoFixture


class FailDiagnosticTests(unittest.TestCase):
  def test_genuine_failure_reports_reason_and_captured_output(self):
    body = (
      "import sys\n"
      "print('failing test output')\n"
      "print('assertion detail', file=sys.stderr)\n"
      "raise SystemExit(7)\n"
    )
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root, validation_body=body)
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 1)
      value = json.loads(result_path.read_text())
      self.assertEqual(value["status"], "FAIL")
      self.assertIn("returned 7", value["message"])
      self.assertIn("failing test output", value["stdout"])
      self.assertIn("assertion detail", value["stderr"])
      outcome, tag, warnings = evaluate_results(
        load_config(root), [value], value["version"], value["commit"]
      )
      self.assertEqual(outcome, "FAIL")
      self.assertEqual(tag, f"v{value['version']}-CI-FAIL")
      text = "\n".join(warnings)
      self.assertIn("returned 7", text)
      self.assertIn("failing test output", text)
      self.assertIn("assertion detail", text)


if __name__ == "__main__":
  unittest.main()
