from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OutputBoundaryEnforcementTests(unittest.TestCase):
  def test_cp1252_print_and_diagnostics_use_strict_utf8(self):
    child = (
      "import io, sys\n"
      "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252', errors='strict', write_through=True)\n"
      "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='cp1252', errors='strict', write_through=True)\n"
      "from repo_workflow.output import configure_utf8_output\n"
      "assert configure_utf8_output()\n"
      "print('→ λ ✓')\n"
      "print('error → λ ✓', file=sys.stderr)\n"
    )
    result = subprocess.run(
      [sys.executable, "-c", child], cwd=ROOT, capture_output=True, check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, "→ λ ✓\n".encode("utf-8"))
    self.assertEqual(result.stderr, "error → λ ✓\n".encode("utf-8"))

  def test_unconfigurable_output_fails_closed(self):
    child = (
      "import sys\n"
      "class Unconfigurable:\n"
      "  def write(self, s): return len(s)\n"
      "original = sys.stdout\n"
      "sys.stdout = Unconfigurable()\n"
      "from repo_workflow.output import configure_utf8_output\n"
      "assert not configure_utf8_output()\n"
      "sys.stdout = original\n"
    )
    result = subprocess.run(
      [sys.executable, "-c", child], cwd=ROOT, capture_output=True, check=False,
    )
    self.assertEqual(result.returncode, 0)
    self.assertIn(b"cannot configure UTF-8 stdout output", result.stderr)

  def test_main_and_all_scripts_initialize_the_shared_streams(self):
    paths = [ROOT / "repo_workflow.py", *sorted((ROOT / "scripts").glob("*.py"))]
    self.assertGreater(len(paths), 10)
    for path in paths:
      with self.subTest(path=path.relative_to(ROOT).as_posix()):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        guard = next(
          (node for node in tree.body
           if isinstance(node, ast.If)
           and isinstance(node.test, ast.Compare)
           and isinstance(node.test.left, ast.Name)
           and node.test.left.id == "__name__"
           and len(node.test.comparators) == 1
           and isinstance(node.test.comparators[0], ast.Constant)
           and node.test.comparators[0].value == "__main__"),
          None,
        )
        self.assertIsNotNone(guard, "entry point must have a main guard")
        calls = [
          node for statement in guard.body for node in ast.walk(statement)
          if isinstance(node, ast.Call)
        ]
        init = [
          node for node in calls if isinstance(node.func, ast.Name)
          and node.func.id in {"configure_utf8_output", "_configure_utf8_output"}
        ]
        self.assertEqual(len(init), 1, "entry point must initialize shared output")
        self.assertIn(
          "from repo_workflow.output import configure_utf8_output",
          source,
          "entry point must use the canonical output implementation",
        )
        exits = [
          node for node in calls if isinstance(node.func, ast.Name)
          and node.func.id == "main"
        ]
        if exits:
          self.assertLess(init[0].lineno, min(node.lineno for node in exits))

  def test_no_direct_fd_writes_outside_approved_boundary(self):
    files = [
      ROOT / "repo_workflow.py",
      *((ROOT / "repo_workflow").glob("*.py")),
      *((ROOT / "scripts").glob("*.py")),
    ]
    allowed = {ROOT / "repo_workflow" / "output.py"}
    for path in files:
      if path in allowed:
        continue
      tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
      for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
          continue
        f = node.func
        if (
          isinstance(f, ast.Attribute)
          and isinstance(f.value, ast.Name)
          and f.value.id == "os"
          and f.attr == "write"
        ):
          self.fail(f"unauthorized direct os.write in {path}:{node.lineno}")


if __name__ == "__main__":
  unittest.main()
