from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "templates" / "local" / "repoworkflow.py"


def load_launcher():
  spec = spec_from_file_location("repoworkflow_launcher", LAUNCHER)
  assert spec is not None and spec.loader is not None
  module = module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def completed(args, returncode=0, stdout="", stderr=""):
  return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class LocalLauncherTests(unittest.TestCase):
  def test_matching_pin_skips_submodule_update(self):
    launcher = load_launcher()
    calls = []

    def fake_run(command, **kwargs):
      calls.append(command)
      if command[:3] == ["git", "rev-parse", "HEAD:RepoWorkflow"]:
        return completed(command, stdout="abc\n")
      if command[:4] == ["git", "-C", "RepoWorkflow", "rev-parse"]:
        return completed(command, stdout="abc\n")
      if command[0] == launcher.sys.executable:
        return completed(command, returncode=0)
      raise AssertionError(command)

    with patch.object(launcher.subprocess, "run", side_effect=fake_run):
      self.assertEqual(launcher.main(["verify", "--push"]), 0)

    self.assertFalse(any("submodule" in command for command in calls))
    self.assertEqual(calls[-1][-2:], ["verify", "--push"])

  def test_mismatched_pin_repairs_before_delegation(self):
    launcher = load_launcher()
    actual_reads = 0
    calls = []

    def fake_run(command, **kwargs):
      nonlocal actual_reads
      calls.append(command)
      if command[:3] == ["git", "rev-parse", "HEAD:RepoWorkflow"]:
        return completed(command, stdout="new\n")
      if command[:4] == ["git", "-C", "RepoWorkflow", "rev-parse"]:
        actual_reads += 1
        value = "old\n" if actual_reads == 1 else "new\n"
        return completed(command, stdout=value)
      if command[:3] == ["git", "submodule", "update"]:
        return completed(command)
      if command[0] == launcher.sys.executable:
        return completed(command)
      raise AssertionError(command)

    with patch.object(launcher.subprocess, "run", side_effect=fake_run):
      self.assertEqual(launcher.main(["verify"]), 0)

    repair_index = next(i for i, command in enumerate(calls) if "submodule" in command)
    engine_index = next(i for i, command in enumerate(calls) if command[0] == launcher.sys.executable)
    self.assertLess(repair_index, engine_index)

  def test_missing_checkout_repairs_before_delegation(self):
    launcher = load_launcher()
    actual_reads = 0

    def fake_run(command, **kwargs):
      nonlocal actual_reads
      if command[:3] == ["git", "rev-parse", "HEAD:RepoWorkflow"]:
        return completed(command, stdout="new\n")
      if command[:4] == ["git", "-C", "RepoWorkflow", "rev-parse"]:
        actual_reads += 1
        if actual_reads == 1:
          return completed(command, returncode=128, stderr="missing")
        return completed(command, stdout="new\n")
      if command[:3] == ["git", "submodule", "update"]:
        return completed(command)
      if command[0] == launcher.sys.executable:
        return completed(command)
      raise AssertionError(command)

    with patch.object(launcher.subprocess, "run", side_effect=fake_run):
      self.assertEqual(launcher.main(["verify"]), 0)

  def test_force_repair_updates_even_matching_pin(self):
    launcher = load_launcher()
    repairs = 0

    def fake_run(command, **kwargs):
      nonlocal repairs
      if command[:3] == ["git", "rev-parse", "HEAD:RepoWorkflow"]:
        return completed(command, stdout="abc\n")
      if command[:4] == ["git", "-C", "RepoWorkflow", "rev-parse"]:
        return completed(command, stdout="abc\n")
      if command[:3] == ["git", "submodule", "update"]:
        repairs += 1
        return completed(command)
      if command[0] == launcher.sys.executable:
        self.assertNotIn("--force-repair", command)
        return completed(command)
      raise AssertionError(command)

    with patch.object(launcher.subprocess, "run", side_effect=fake_run):
      self.assertEqual(launcher.main(["--force-repair", "verify"]), 0)

    self.assertEqual(repairs, 1)

  def test_failed_repair_never_runs_engine(self):
    launcher = load_launcher()

    def fake_run(command, **kwargs):
      if command[:3] == ["git", "rev-parse", "HEAD:RepoWorkflow"]:
        return completed(command, stdout="new\n")
      if command[:4] == ["git", "-C", "RepoWorkflow", "rev-parse"]:
        return completed(command, returncode=128)
      if command[:3] == ["git", "submodule", "update"]:
        return completed(command, returncode=1, stderr="repair failed")
      if command[0] == launcher.sys.executable:
        raise AssertionError("engine must not run after failed repair")
      raise AssertionError(command)

    with patch.object(launcher.subprocess, "run", side_effect=fake_run):
      with self.assertRaisesRegex(RuntimeError, "repair failed"):
        launcher.main(["verify"])


if __name__ == "__main__":
  unittest.main()
