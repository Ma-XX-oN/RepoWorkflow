from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
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

  def test_unicode_native_capture_streams_remain_usable(self):
    class FrameworkCapture(io.StringIO):
      pass

    stdout = FrameworkCapture()
    stderr = FrameworkCapture()
    with redirect_stdout(stdout), redirect_stderr(stderr):
      from repo_workflow.output import configure_utf8_output
      self.assertTrue(configure_utf8_output())
      print("captured → λ ✓")
      print("diagnostic → λ ✓", file=sys.stderr)
    self.assertEqual(stdout.getvalue(), "captured → λ ✓\n")
    self.assertEqual(stderr.getvalue(), "diagnostic → λ ✓\n")

  def test_already_strict_utf8_capture_without_reconfigure(self):
    class FrameworkStream:
      encoding = "utf-8"
      errors = "strict"
      closed = False

      def __init__(self):
        self.text = io.StringIO()

      def write(self, value):
        return self.text.write(value)

    stdout = FrameworkStream()
    stderr = FrameworkStream()
    with redirect_stdout(stdout), redirect_stderr(stderr):
      from repo_workflow.output import configure_utf8_output
      self.assertTrue(configure_utf8_output())
      print("unicode λ ✓")
      print("stderr λ ✓", file=sys.stderr)
    self.assertEqual(stdout.text.getvalue(), "unicode λ ✓\n")
    self.assertEqual(stderr.text.getvalue(), "stderr λ ✓\n")

  def test_legacy_metadata_stream_without_reconfigure_fails_closed(self):
    child = (
      "import sys\n"
      "class Legacy:\n"
      "  encoding='cp1252'\n"
      "  errors='strict'\n"
      "  def write(self, data): return len(data)\n"
      "original = sys.stdout\n"
      "sys.stdout = Legacy()\n"
      "from repo_workflow.output import configure_utf8_output\n"
      "try:\n"
      "  assert not configure_utf8_output()\n"
      "finally:\n"
      "  sys.stdout = original\n"
    )
    result = subprocess.run(
      [sys.executable, "-c", child], cwd=ROOT, capture_output=True, check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn(b"cannot configure UTF-8 stdout output", result.stderr)

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

  def test_hosted_cache_git_output_uses_shared_utf8_boundary(self):
    from unittest.mock import patch
    from repo_workflow.github_cache import (
      hosted_cache_checker, read_remote_published_log,
    )
    from repo_workflow.process import CommandResult

    def outcome(command, root, *, code=0, stdout="", stderr=""):
      return CommandResult(
        list(command), code, stdout, stderr, 0.0,
      )

    with patch("repo_workflow.github_cache.run_command") as command:
      command.return_value = outcome(("git",), Path.cwd(), code=2,
                                     stderr="invalid UTF-8 command output")
      self.assertIsNone(hosted_cache_checker(ROOT, "GREEN"))
      command.assert_called_once()
    with patch("repo_workflow.github_cache.run_command") as command:
      command.return_value = outcome(("git",), Path.cwd(), code=2,
                                     stderr="invalid UTF-8 command output")
      self.assertIsNone(read_remote_published_log(
        ROOT, branch="issue-545-test", relative=".repoworkflow/validation/testResults-545.jsonl",
      ))
      command.assert_called_once()

  def test_invalid_utf8_git_invocation_output_fails_closed(self):
    from unittest.mock import patch
    from repo_workflow.ci_invocation import CiInvocationError, _git
    from repo_workflow.process import BinaryCommandResult

    def raw(stdout: bytes, stderr: bytes, code: int):
      return BinaryCommandResult(["git"], code, stdout, stderr, 0.0)

    with patch("repo_workflow.ci_invocation.run_command_bytes",
               return_value=raw(b"\xff", b"", 0)):
      with self.assertRaisesRegex(CiInvocationError, "invalid UTF-8 Git output"):
        _git(ROOT, "rev-parse", "HEAD")
      with self.assertRaisesRegex(CiInvocationError, "committed CI marker is not UTF-8"):
        _git(ROOT, "show", "HEAD:.ci/run", raw=True)

    with patch("repo_workflow.ci_invocation.run_command_bytes",
               return_value=raw(b"", b"\xff", 1)):
      with self.assertRaisesRegex(CiInvocationError, "invalid UTF-8 Git diagnostic"):
        _git(ROOT, "show", "HEAD:.ci/run", raw=True)

  def test_audited_git_consumers_cannot_reintroduce_locale_text_capture(self):
    for name in (
      "repo_workflow/github_cache.py",
      "repo_workflow/ci_invocation.py",
      "repo_workflow/pre_merge_gate.py",
      "repo_workflow/engine_remote.py",
      "repo_workflow/hosted_terminal_publication.py",
      "repo_workflow/hosted_cache.py",
      "repo_workflow/terminal_tag.py",
      "repo_workflow/ticket_merge.py",
      "repo_workflow/results.py",
      "scripts/probe-ticket-merge.py",
      "scripts/on-demand-ci-plan.py",
      "scripts/publish-hosted-result.py",
    ):
      source = ROOT / name
      tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
      for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
          continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in {"run", "check_output"}:
          for kwarg in node.keywords:
            if kwarg.arg == "text" and isinstance(kwarg.value, ast.Constant):
              self.assertNotEqual(
                kwarg.value.value, True,
                f"locale-dependent subprocess capture in {name}:{node.lineno}",
              )

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
