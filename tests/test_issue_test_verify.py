from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import shutil
import tempfile
import unittest

from repo_workflow.command_grammar import Context, parse_tokens
from repo_workflow.public_commands import COMMANDS
from repo_workflow.issue_test_contract import (
  IssueTest,
  IssueTestContract,
  IssueTestContractStore,
)
from repo_workflow.issue_test_verify import verify_issue_tests
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class IssueTestVerifyTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def write(self, tests, trust="repository"):
    IssueTestContractStore(self.root).write(
      IssueTestContract(issue=256, tests=tuple(tests), trust=trust),
      self.writer,
    )

  def verify(self):
    output = StringIO()
    with redirect_stdout(output):
      code = verify_issue_tests(self.root, 256)
    return code, json.loads(output.getvalue())

  def test_no_tests_is_green(self):
    self.write(())
    code, result = self.verify()
    self.assertEqual(code, 0)
    self.assertEqual(result["status"], "green")
    self.assertEqual(result["tests"], [])

  def test_green_tests_return_zero(self):
    self.write((IssueTest("python", "assert True\n"),))
    code, result = self.verify()
    self.assertEqual(code, 0)
    self.assertEqual(result["status"], "green")

  def test_red_test_returns_one(self):
    self.write((IssueTest("python", "assert False\n"),))
    code, result = self.verify()
    self.assertEqual(code, 1)
    self.assertEqual(result["status"], "red")

  def test_untrusted_test_returns_error_without_execution(self):
    self.write(
      (IssueTest("python", "open('should-not-exist', 'w').write('bad')\n"),),
      trust="ticket-proposed",
    )
    code, result = self.verify()
    self.assertEqual(code, 2)
    self.assertEqual(result["status"], "error")
    self.assertFalse((self.root / "should-not-exist").exists())

  def test_missing_contract_is_explicit_error(self):
    code, result = self.verify()
    self.assertEqual(code, 2)
    self.assertEqual(result["status"], "error")


  def test_bash_file_requirement_is_red_then_green_through_durable_contract(self):
    if shutil.which("bash") is None:
      self.skipTest("Bash evaluator is unavailable")
    self.write((IssueTest("bash", "test -f promised.txt\n"),))

    red_code, red = self.verify()
    self.assertEqual(red_code, 1)
    self.assertEqual(red["status"], "red")

    (self.root / "promised.txt").write_text("fulfilled\n", encoding="utf-8")
    green_code, green = self.verify()
    self.assertEqual(green_code, 0)
    self.assertEqual(green["status"], "green")

  def test_public_validate_issue_grammar_accepts_issue_number(self):
    parse_tokens(
      COMMANDS,
      Context(self.root, legal_only=False),
      ["validate", "issue", "261"],
    )


if __name__ == "__main__":
  unittest.main()
