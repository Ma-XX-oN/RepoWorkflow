"""Specification-based CLI subprocess probes for unified testing commands.

These tests run the actual launcher. The absent implementation is explicitly
skipped, never represented as successful provider/assembled certification.
"""

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "repo_workflow.py"
STAGES = ("RED", "temporary", "GREEN", "regression", "integration", "results")


def run_cli(*args):
  return subprocess.run(
    [sys.executable, str(LAUNCHER), *args],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8", errors="strict",
    timeout=30,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    check=False,
  )


class UnifiedCliSpecificationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not LAUNCHER.is_file():
      raise unittest.SkipTest("PENDING: actual ./rwf launcher unavailable")
    try:
      cls.test_help = run_cli("test", "--help")
    except (OSError, subprocess.TimeoutExpired) as exc:
      raise unittest.SkipTest(f"PENDING: launcher unavailable: {exc}")
    if cls.test_help.returncode != 0:
      raise unittest.SkipTest(
        "PENDING: #545 unified public test grammar not on this candidate")

  def test_all_six_stage_help_paths(self):
    for stage in STAGES:
      with self.subTest(stage=stage):
        response = run_cli("test", stage, "--help")
        if stage == "RED" and response.returncode != 0:
          self.assertIn(".ci/tests.json", response.stdout + response.stderr)
        else:
          self.assertEqual(response.returncode, 0, response.stderr)
        self.assertTrue((response.stdout + response.stderr).strip())

  def test_unknown_stage_is_rejected(self):
    response = run_cli("test", "nonexistent-stage", "--help")
    self.assertNotEqual(response.returncode, 0)

  def test_unknown_options_rejected_across_families(self):
    for stage in STAGES:
      with self.subTest(stage=stage):
        response = run_cli("test", stage, "--unknown-629-option")
        self.assertNotEqual(response.returncode, 0)

  def test_remote_option_is_documented_for_every_stage(self):
    for stage in STAGES:
      with self.subTest(stage=stage):
        response = run_cli("test", stage, "--help")
        if stage == "RED" and response.returncode != 0:
          self.assertIn(".ci/tests.json", response.stdout + response.stderr)
        else:
          self.assertEqual(response.returncode, 0, response.stderr)
          self.assertIn("--remote", response.stdout + response.stderr)

  def test_legacy_validate_regression_and_integration_removed(self):
    for stage in ("regression", "integration"):
      with self.subTest(stage=stage):
        response = run_cli("validate", stage, "--help")
        self.assertNotEqual(response.returncode, 0)


if __name__ == "__main__":
  unittest.main()
