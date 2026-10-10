"""Shipped CLI tests for non-launchable GREEN and temporary harnesses."""
from pathlib import Path
import json
import unittest

from tests import test_test_cli as fixture


class TestLaunchFailures(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def _missing_executable_catalogue(self, target: Path, group: str):
    self._catalogue(target, issue_group=group)
    value = json.loads(target.read_text())
    value["test-harnesses"]["unittest"]["command"] = (
      "rwf-test-nonexistent-executable-545"
    )
    target.write_text(json.dumps(value))
    return target

  def _log(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertTrue(path.is_file())
    return json.loads(path.read_text().splitlines()[-1])

  def test_green_missing_executable_is_failed_or_incomplete_evidence(self):
    self._missing_executable_catalogue(
      self.root / ".ci/tests.json", "issue-545-green-missing",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "register GREEN")
    # RED commits the single selected group, independently of its outcome.
    self.assertEqual(
      self.cli("test", "RED", "issue-545-green-missing").returncode, 2,
    )
    output = self.cli("test", "GREEN")
    self.assertEqual(output.returncode, 2, output.stderr)
    record = self._log()
    self.assertEqual(record["kind"], "GREEN")
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])
    self.assertIsNone(record["groups"][0]["exit_code"])
    read = self.cli("test", "results")
    self.assertEqual(read.returncode, 0, read.stderr)
    self.assertEqual(json.loads(read.stdout.splitlines()[-1]), record)

  def test_signalled_temporary_runner_is_incomplete_not_failed(self):
    import os
    if os.name == "nt":
      self.skipTest("negative signal return codes are POSIX-specific")
    self._catalogue(
      self.root / ".ci/temp-tests.json", issue_group="issue-545-signal",
    )
    (self.root / "smoke_case.py").write_text(
      "import os, signal, unittest\\n"
      "class Smoke(unittest.TestCase):\\n"
      "  def test_pass(self):\\n"
      "    os.kill(os.getpid(), signal.SIGTERM)\\n"
    )
    self.git("add", ".ci/temp-tests.json", "smoke_case.py")
    self.git("commit", "-m", "signalled temporary test")
    result = self.cli("test", "temporary")
    self.assertEqual(result.returncode, 2, result.stderr)
    record = self._log()
    self.assertEqual(record["kind"], "temporary")
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])
    self.assertLess(record["groups"][0]["exit_code"], 0)


  def test_signalled_green_runner_is_incomplete_not_failed(self):
    import os
    if os.name == "nt":
      self.skipTest("negative signal return codes are POSIX-specific")
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-signal-green",
    )
    (self.root / "smoke_case.py").write_text(
      "import os, signal, unittest\\n"
      "class Smoke(unittest.TestCase):\\n"
      "  def test_pass(self):\\n"
      "    os.kill(os.getpid(), signal.SIGTERM)\\n"
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "signalled GREEN group")
    self.assertEqual(
      self.cli("test", "RED", "issue-545-signal-green").returncode, 2,
    )
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 2, result.stderr)
    record = self._log()
    self.assertEqual(record["kind"], "GREEN")
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])
    self.assertLess(record["groups"][0]["exit_code"], 0)


  def test_temporary_missing_executable_is_incomplete_evidence(self):
    self._missing_executable_catalogue(
      self.root / ".ci/temp-tests.json", "issue-545-temp-missing",
    )
    self.git("add", ".ci/temp-tests.json", "smoke_case.py")
    self.git("commit", "-m", "register temporary")
    output = self.cli("test", "temporary")
    self.assertEqual(output.returncode, 2, output.stderr)
    record = self._log()
    self.assertEqual(record["kind"], "temporary")
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])
    self.assertIsNone(record["groups"][0]["exit_code"])
    read = self.cli("test", "results")
    self.assertEqual(read.returncode, 0, read.stderr)
    self.assertEqual(json.loads(read.stdout.splitlines()[-1]), record)


if __name__ == "__main__":
  unittest.main()
