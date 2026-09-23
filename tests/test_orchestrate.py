import sys
import unittest
from pathlib import Path

from repo_workflow.orchestrate import run_parallel, run_series


class OrchestrateTests(unittest.TestCase):
  def test_series_preserves_order(self):
    commands = [
      [sys.executable, "-c", "print('first')"],
      [sys.executable, "-c", "print('second')"],
    ]
    results = run_series(commands)
    self.assertEqual([r.stdout.strip() for r in results], ["first", "second"])

  def test_series_stops_after_failure_by_default(self):
    commands = [
      [sys.executable, "-c", "raise SystemExit(1)"],
      [sys.executable, "-c", "print('should-not-run')"],
    ]
    results = run_series(commands)
    self.assertEqual(len(results), 1)

  def test_series_can_continue_after_failure(self):
    commands = [
      [sys.executable, "-c", "raise SystemExit(1)"],
      [sys.executable, "-c", "print('ran')"],
    ]
    results = run_series(commands, continue_on_failure=True)
    self.assertEqual(len(results), 2)
    self.assertEqual(results[1].stdout.strip(), "ran")

  def test_parallel_waits_for_all_and_preserves_input_order(self):
    commands = [
      [sys.executable, "-c", "import time; time.sleep(.15); print('slow')"],
      [sys.executable, "-c", "print('fast')"],
    ]
    results = run_parallel(commands)
    self.assertEqual([r.stdout.strip() for r in results], ["slow", "fast"])

  def test_parallel_reports_all_failures(self):
    commands = [
      [sys.executable, "-c", "raise SystemExit(1)"],
      [sys.executable, "-c", "raise SystemExit(2)"],
    ]
    results = run_parallel(commands)
    self.assertEqual([r.returncode for r in results], [1, 2])


if __name__ == "__main__":
  unittest.main()
