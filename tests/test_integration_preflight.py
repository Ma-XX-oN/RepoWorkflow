"""Black-box local integration preflight tests."""
from pathlib import Path
import unittest

from tests import test_test_cli as fixture


class IntegrationPreflightTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli

  def test_issue_sandbox_with_only_support_files_blocks_integration(self):
    sandbox = self.root / ".ci" / "temp-tests" / "545"
    sandbox.mkdir(parents=True)
    (sandbox / "reference.cpp").write_text("int main() { return 0; }\n")
    result = self.cli("test", "integration")
    self.assertEqual(result.returncode, 2)
    self.assertIn(".ci/temp-tests/545", result.stderr)
    self.assertIn("complete removal", result.stderr)
    self.assertNotIn("preflight passed", result.stderr)

  def test_empty_issue_sandbox_blocks_and_complete_removal_advances(self):
    sandbox = self.root / ".ci" / "temp-tests" / "545"
    sandbox.mkdir(parents=True)
    blocked = self.cli("test", "integration")
    self.assertEqual(blocked.returncode, 2)
    self.assertIn(".ci/temp-tests/545", blocked.stderr)
    sandbox.rmdir()
    advanced = self.cli("test", "integration")
    self.assertEqual(advanced.returncode, 2)
    self.assertIn("environment adapter", advanced.stderr)
    self.assertNotIn("succeeded", advanced.stdout)

  def test_another_issues_sandbox_is_not_owned_by_current_issue(self):
    sandbox = self.root / ".ci" / "temp-tests" / "544"
    sandbox.mkdir(parents=True)
    (sandbox / "fixture.bin").write_bytes(b"x")
    result = self.cli("test", "integration")
    self.assertEqual(result.returncode, 2)
    self.assertIn("environment adapter", result.stderr)


if __name__ == "__main__":
  unittest.main()
