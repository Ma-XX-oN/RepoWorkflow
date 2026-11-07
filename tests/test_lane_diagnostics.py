from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from repo_workflow.lane_diagnostics import LaneDiagnostics


class LaneDiagnosticsTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "--allow-empty", "-m", "initial"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )

  def test_provider_progress_and_record_are_structured_without_payload(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      diagnostics = LaneDiagnostics(
        root,
        ("lanes", "view", "--refresh", "--debug"),
      )
      stderr = io.StringIO()
      with redirect_stderr(stderr):
        value = diagnostics.provider(
          "dependencies",
          203,
          lambda: {"secret": "must-not-be-logged"},
          index=1,
          total=2,
        )
      self.assertEqual(value, {"secret": "must-not-be-logged"})
      self.assertEqual(
        stderr.getvalue().strip(),
        "Refreshing dependencies: 1/2 (#203)",
      )

      diagnostics.hit("relationships", 3)
      diagnostics.miss("relationships", 1)
      started = time.perf_counter()
      diagnostics.phase("render", started)
      diagnostics.set_semantic_edges([(201, 203), (201, 203)])
      path = diagnostics.finish()
      self.assertIsNotNone(path)
      record = json.loads(path.read_text(encoding="utf-8"))

      self.assertTrue(record["success"])
      self.assertEqual(
        record["command"],
        ["lanes", "view", "--refresh", "--debug"],
      )
      self.assertEqual(record["provider_calls"], {"dependencies": 1})
      self.assertEqual(record["cache_hits"], {"relationships": 3})
      self.assertEqual(record["cache_misses"], {"relationships": 1})
      self.assertEqual(record["semantic_edges"], [[201, 203]])
      self.assertGreaterEqual(record["elapsed_seconds"], 0)
      self.assertGreaterEqual(record["provider_seconds"]["dependencies"], 0)
      self.assertGreaterEqual(record["phase_seconds"]["render"], 0)
      self.assertRegex(
        record["repository_head"],
        r"^[0-9a-f]{40}$",
      )
      self.assertNotIn("must-not-be-logged", path.read_text(encoding="utf-8"))

  def test_timing_accounting_is_internally_consistent(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      diagnostics = LaneDiagnostics(
        root,
        ("lanes", "view", "--refresh"),
        started=10.0,
      )

      with mock.patch(
        "repo_workflow.lane_diagnostics.time.perf_counter",
        side_effect=[11.0, 12.0, 13.0, 15.0],
      ):
        diagnostics.provider("dependencies", 203, lambda: None)
        diagnostics.phase("render", 12.5)
        path = diagnostics.finish()

      self.assertIsNotNone(path)
      record = json.loads(path.read_text(encoding="utf-8"))
      self.assertEqual(record["provider_calls"], {"dependencies": 1})
      self.assertEqual(record["provider_seconds"], {"dependencies": 1.0})
      self.assertEqual(record["phase_seconds"], {"render": 0.5})
      self.assertEqual(record["elapsed_seconds"], 5.0)
      self.assertLessEqual(
        sum(record["provider_seconds"].values()),
        record["elapsed_seconds"],
      )
      self.assertTrue(
        all(
          seconds <= record["elapsed_seconds"]
          for seconds in record["phase_seconds"].values()
        )
      )

  def test_error_record_and_concurrent_records_are_distinct(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      def write(index: int):
        diagnostics = LaneDiagnostics(root, ("lanes", "view", str(index)))
        return diagnostics.finish(
          error=RuntimeError("boom") if index == 0 else None
        )

      with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(write, range(16)))

      self.assertTrue(all(path is not None for path in paths))
      self.assertEqual(len({path.name for path in paths}), 16)
      first = json.loads(paths[0].read_text(encoding="utf-8"))
      self.assertFalse(first["success"])
      self.assertEqual(first["error"], "RuntimeError")

  def test_failure_record_does_not_persist_raw_secret_bearing_error(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      diagnostics = LaneDiagnostics(root, ("lanes", "view", "--refresh"))
      path = diagnostics.finish(
        error=RuntimeError("provider leaked token ghp_super_secret"),
      )
      self.assertIsNotNone(path)
      text_value = path.read_text(encoding="utf-8")
      self.assertNotIn("ghp_super_secret", text_value)
      record = json.loads(text_value)
      self.assertEqual(record["error"], "RuntimeError")

  def test_diagnostic_write_failure_is_warning_not_command_failure(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      diagnostics = LaneDiagnostics(root, ("lanes", "view"))
      stderr = io.StringIO()
      with (
        mock.patch.object(
          LaneDiagnostics,
          "_write",
          side_effect=OSError("disk unavailable"),
        ),
        redirect_stderr(stderr),
      ):
        self.assertIsNone(diagnostics.finish())

      self.assertIn(
        "could not write lane invocation diagnostics: disk unavailable",
        stderr.getvalue(),
      )

  def test_debug_projection_reports_sources_timing_and_edges(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      diagnostics = LaneDiagnostics(root, ("lanes", "view", "--debug"))
      diagnostics.hit("metadata", 3)
      diagnostics.miss("relationships", 1)
      diagnostics.provider_counts["dependencies"] = 1
      diagnostics.provider_seconds["dependencies"] = 0.25
      diagnostics.phase_seconds["render"] = 0.01
      diagnostics.set_semantic_edges([(145, 185), (145, 216), (185, 216)])

      output = "\n".join(diagnostics.debug_lines())
      self.assertIn("DATA SOURCES", output)
      self.assertIn("provider requests: 1", output)
      self.assertIn("metadata: cache hits=3 misses=0", output)
      self.assertIn("relationships: cache hits=0 misses=1", output)
      self.assertIn("provider dependencies: 0.250s", output)
      self.assertIn("render: 0.010s", output)
      self.assertIn("145 -> 216", output)


if __name__ == "__main__":
  unittest.main()
