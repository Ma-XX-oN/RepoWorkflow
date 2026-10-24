from __future__ import annotations

import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "repo_workflow.py"
MARKERS = "→ ─│└ ✓ ○ ● ◎ ♥ ✕"


class WindowsUnicodeOutputTests(unittest.TestCase):
  def invoke(
    self, *args: str, legacy: bool = False, markers: bool = False,
    stdout=None, stderr=None,
  ):
    env = os.environ.copy()
    # Do not hide an encoding defect behind Python's encoding override.
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    if not legacy:
      argv = [sys.executable, str(ENTRYPOINT), *args]
    else:
      setup = (
        "import io, runpy, sys\n"
        "entry = sys.argv[1]\n"
        "markers = sys.argv[2] == '1'\n"
        "sys.argv = [entry, *sys.argv[3:]]\n"
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, "
        "encoding='cp1252', errors='strict', write_through=True)\n"
        "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, "
        "encoding='cp1252', errors='strict', write_through=True)\n"
        "try:\n"
        "  runpy.run_path(entry, run_name='__main__')\n"
        "except SystemExit:\n"
        "  if markers:\n"
        "    sys.stdout.write('→ ─│└ ✓ ○ ● ◎ ♥ ✕\\n')\n"
        "    sys.stderr.write('diagnostic → ─│└ ✓\\n')\n"
        "  raise\n"
      )
      argv = [
        sys.executable, "-c", setup, str(ENTRYPOINT),
        "1" if markers else "0", *args,
      ]
    streams = (
      {"capture_output": True}
      if stdout is None and stderr is None
      else {"stdout": stdout, "stderr": stderr}
    )
    return subprocess.run(
      argv, cwd=ROOT, env=env, check=False, **streams,
    )

  def test_legacy_cp1252_subprocess_round_trips_all_glyphs(self):
    result = self.invoke("--help", legacy=True, markers=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    stdout = result.stdout.decode("utf-8", errors="strict")
    stderr = result.stderr.decode("utf-8", errors="strict")
    self.assertIn(MARKERS, stdout)
    self.assertIn("diagnostic → ─│└ ✓", stderr)
    self.assertIn("test", stdout)
    self.assertNotIn(b"\\u2192", result.stdout)
    self.assertNotIn(b"?", result.stderr)

  def test_legacy_cp1252_json_is_unchanged(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root, capabilities=["unicode → ✓ 日本語"])
      plain = self.invoke("--root", str(root), "matrix")
      legacy = self.invoke("--root", str(root), "matrix", legacy=True)
      self.assertEqual(plain.returncode, 0, plain.stderr)
      self.assertEqual(legacy.returncode, 0, legacy.stderr)
      value = json.loads(legacy.stdout.decode("utf-8", errors="strict"))
      self.assertIn("include", value)
      self.assertEqual(value["include"][0]["capabilities"], ["unicode → ✓ 日本語"])
      self.assertEqual(plain.stdout, legacy.stdout)
      self.assertEqual(plain.stderr, legacy.stderr)

  def test_nonzero_diagnostic_remains_nonzero_under_cp1252(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      result = self.invoke(
        "--root", str(root), "matrix", "--invalid=→",
        legacy=True,
      )
      self.assertEqual(result.returncode, 2, result.stderr)
      stderr = result.stderr.decode("utf-8", errors="strict")
      self.assertIn("error:", stderr.lower())
      self.assertIn("--invalid=→", stderr)
      self.assertEqual(result.stdout, b"")

  def test_real_public_lane_rendering_under_legacy_cp1252(self):
    # Reuse the repository's existing authentic canonical-graph fixture.
    from tests.test_canonical_lane_smoke import (
      CANONICAL_TICKETS, CanonicalLaneSmokeTests, TYPE_PREFIXES,
    )
    import csv

    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      CanonicalLaneSmokeTests().make_repo(root)
      with CANONICAL_TICKETS.open(encoding="utf-8", newline="") as handle:
        selected = [
          row["issue"] for row in csv.DictReader(handle)
          if row["title"].startswith(TYPE_PREFIXES)
        ]
      self.assertTrue(selected)
      selected_result = self.invoke(
        "--root", str(root), "lanes", "select", *selected,
        legacy=True,
      )
      self.assertEqual(
        selected_result.returncode, 0,
        selected_result.stderr.decode("utf-8", errors="replace"),
      )
      selected_text = selected_result.stdout.decode("utf-8", errors="strict")
      self.assertIn("→", selected_text)
      view = self.invoke(
        "--root", str(root), "lanes", "view", "--legend",
        legacy=True,
      )
      self.assertEqual(
        view.returncode, 0, view.stderr.decode("utf-8", errors="replace"),
      )
      rendered = view.stdout.decode("utf-8", errors="strict")
      self.assertIn("Legend:", rendered)
      self.assertIn("✓ accepted", rendered)
      self.assertTrue(any(ch in rendered for ch in "─│└"), rendered)

  def test_redirected_file_streams_remain_utf8(self):
    # Real stdout/stderr file redirection, not just subprocess.PIPE.
    with tempfile.TemporaryDirectory() as td:
      stdout_path = Path(td) / "stdout"
      stderr_path = Path(td) / "stderr"
      with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        result = self.invoke(
          "--help", legacy=True, markers=True, stdout=out, stderr=err,
        )
      self.assertEqual(result.returncode, 0)
      self.assertIn(MARKERS, stdout_path.read_text(encoding="utf-8"))
      self.assertIn("diagnostic →", stderr_path.read_text(encoding="utf-8"))

  def test_inprocess_unicode_text_capture_is_preserved(self):
    scope = runpy.run_path(str(ENTRYPOINT), run_name="test_p9_source")
    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
      self.assertTrue(scope["_configure_utf8_output"]())
      print(MARKERS)
      print("diagnostic →", file=sys.stderr)
    self.assertEqual(out.getvalue(), MARKERS + "\n")
    self.assertEqual(err.getvalue(), "diagnostic →\n")

  def test_unconfigurable_stream_fails_explicitly(self):
    bootstrap = (
      "import io, runpy, sys\n"
      "class NoopReconfigure(io.TextIOBase):\n"
      "  @property\n"
      "  def encoding(self): return 'cp1252'\n"
      "  @property\n"
      "  def errors(self): return 'replace'\n"
      "  def reconfigure(self, **kwargs): pass\n"
      "entry, mode = sys.argv[1:]\n"
      "sys.argv = [entry, '--help']\n"
      "if mode == 'noop':\n"
      "  sys.stdout = NoopReconfigure()\n"
      "else:\n"
      "  setattr(sys, mode, io.TextIOBase())\n"
      "runpy.run_path(entry, run_name='__main__')\n"
    )
    for mode, target in (
      ("stdout", "stdout"), ("stderr", "stderr"), ("noop", "stdout"),
    ):
      with self.subTest(mode=mode):
        result = subprocess.run(
          [sys.executable, "-c", bootstrap, str(ENTRYPOINT), mode],
          cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(
          f"RepoWorkflow error: cannot configure UTF-8 {target} output".encode(),
          result.stderr,
        )
        self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
  unittest.main()
