"""Authoritative RED declaration acceptance through the shipped Python CLI."""
import json
import unittest
from tests import test_test_cli as fixture


class ExpectedRedCliTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def configure(self, declaration, *, exit_code=3, output="case invariant violated"):
    path = self.root / ".ci/tests.json"
    self._catalogue(path, issue_group="issue-545-declared")
    data = json.loads(path.read_text())
    if declaration is not None:
      data["tests"][0]["issue-545-declared"]["expected-red"] = declaration
    path.write_text(json.dumps(data))
    (self.root / "smoke_case.py").write_text(
      "import sys, unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self):\n"
      f"    sys.stderr.write({output!r})\n"
      f"    sys.exit({exit_code})\n"
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "declare RED source")

  def last(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    return json.loads(path.read_text().splitlines()[-1])

  def test_expected_failure_repeated_and_changed_declaration(self):
    # Use a deterministic Python executable as the native harness.
    self.configure({"exit-code": 1, "output-contains": "case invariant violated"})
    for attempt in range(2):
      with self.subTest(attempt=attempt):
        result = self.cli("test", "RED", "issue-545-declared") if not attempt else self.cli("test", "RED")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.last()["redStatus"], "RED")
        self.assertFalse(self.last()["reusable"])
    source = self.root / ".ci/tests.json"
    data = json.loads(source.read_text())
    data["tests"][0]["issue-545-declared"]["expected-red"]["output-contains"] = "a different invariant"
    source.write_text(json.dumps(data))
    changed = self.cli("test", "RED")
    self.assertEqual(changed.returncode, 2)
    self.assertEqual(self.last()["redStatus"], "FAIL")
    self.assertEqual(len((self.root / ".repoworkflow/validation/testResults-545.jsonl").read_text().splitlines()), 3)

  def test_missing_declaration_does_not_run_selected_test(self):
    self.configure(None)
    out = self.cli("test", "RED", "issue-545-declared")
    self.assertEqual(out.returncode, 2)
    self.assertEqual(self.last()["redStatus"], "INCOMPLETE")
    self.assertIsNone(self.last()["groups"][0]["exit_code"])

  def test_invalid_declarations_never_launch(self):
    for declaration in (
      {"exit-code": True, "output-contains": "case invariant violated"},
      {"exit-code": 0, "output-contains": "case invariant violated"},
      {"exit-code": -1, "output-contains": "case invariant violated"},
      {"exit-code": 1, "output-contains": ""},
      {"exit-code": 1, "output-contains": "FAILED"},
      {"exit-code": 1, "output-contains": "Error"},
      {"exit-code": 1, "output-contains": "case invariant violated", "regex": ".*"},
    ):
      with self.subTest(declaration=declaration):
        self.configure(declaration)
        out = self.cli("test", "RED", "issue-545-declared")
        self.assertEqual(out.returncode, 2, out.stderr)
        record = self.last()
        self.assertEqual(record["redStatus"], "INCOMPLETE")
        self.assertIsNone(record["groups"][0]["exit_code"])

  def test_unexpected_pass_classifies_not_red(self):
    self.configure({"exit-code": 1, "output-contains": "case invariant violated"})
    path = self.root / "smoke_case.py"
    path.write_text(
      "import unittest\nclass Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(True)\n"
    )
    self.git("add", "smoke_case.py")
    self.git("commit", "-m", "unexpected passing RED fixture")
    out = self.cli("test", "RED", "issue-545-declared")
    self.assertEqual(out.returncode, 2, out.stderr)
    self.assertEqual(self.last()["redStatus"], "NOT_RED")

  def test_wrong_exit_and_signature_are_fail(self):
    self.configure({"exit-code": 2, "output-contains": "case invariant violated"})
    out = self.cli("test", "RED", "issue-545-declared")
    self.assertEqual(out.returncode, 2)
    self.assertEqual(self.last()["redStatus"], "FAIL")


if __name__ == "__main__":
  unittest.main()
