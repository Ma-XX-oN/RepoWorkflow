from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "rwf"
PYTHON_ENTRY = ROOT / "repo_workflow.py"


def capture_utf8(command, *, input=None, **kwargs):
  assert "capture_output" not in kwargs
  assert "encoding" not in kwargs and "errors" not in kwargs
  assert "check" not in kwargs
  result = subprocess.run(
    command,
    input=input.encode("utf-8") if input is not None else None,
    capture_output=True,
    check=False,
    **kwargs,
  )
  # Decode on this thread: Windows subprocess reader threads otherwise swallow
  # UnicodeDecodeError and produce a misleading None result.
  return subprocess.CompletedProcess(
    result.args,
    result.returncode,
    result.stdout.decode("utf-8", "strict"),
    result.stderr.decode("utf-8", "strict"),
  )


class LauncherTests(unittest.TestCase):
  def posix_shell(self):
    # Probe actual execution support, including POSIX shells on Windows.
    candidates = (os.environ.get("SHELL"), shutil.which("sh"))
    for shell in dict.fromkeys(value for value in candidates if value):
      with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "shell-probe"
        probe.write_text(
          "#!/bin/sh\n"
          "for value in one; do\n"
          "  if [ \"$value\" = one ]; then exec \"$@\"; fi\n"
          "done\n"
          "exit 9\n",
          encoding="utf-8",
        )
        probe.chmod(0o755)
        try:
          completed = subprocess.run(
            [shell, str(probe), sys.executable, "-c", "raise SystemExit(37)"],
            capture_output=True,
            check=False,
          )
        except OSError:
          continue
        if completed.returncode == 37:
          return shell
    self.skipTest("No installed shell can execute the existing POSIX launcher")

  def test_unusable_shell_does_not_hide_working_alternative(self):
    compatible = shutil.which("sh")
    if compatible is None:
      self.skipTest("No installed POSIX shell to exercise fallback selection")
    with patch.dict(os.environ, {"SHELL": sys.executable}):
      with patch("tests.test_launcher.shutil.which", return_value=compatible):
        self.assertEqual(self.posix_shell(), compatible)

  def test_missing_shell_capability_is_reported_as_ineligible(self):
    with patch.dict(os.environ, {"SHELL": sys.executable}):
      with patch("tests.test_launcher.shutil.which", return_value=None):
        with self.assertRaises(unittest.SkipTest):
          self.posix_shell()

  def run_launcher(self, python3: str | None, python: str | None):
    shell = self.posix_shell()
    with tempfile.TemporaryDirectory() as tmp:
      bindir = Path(tmp)
      for name, body in (("python3", python3), ("python", python)):
        if body is not None:
          path = bindir / name
          path.write_text(
            f"#!/bin/sh\n{body}\n",
            encoding="utf-8",
          )
          path.chmod(0o755)
      env = os.environ.copy()
      env["PATH"] = os.pathsep.join((str(bindir), env.get("PATH", "")))
      return capture_utf8(
        [shell, str(LAUNCHER), "actions-policy", "--help"],
        cwd=ROOT,
        env=env,
      )

  def python_forwarder(self):
    return f'exec {shlex.quote(sys.executable)} "$@"'

  def test_falls_back_from_broken_python3_to_python(self):
    result = self.run_launcher(
      "exit 9009",
      self.python_forwarder(),
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage:", result.stdout.lower())

  def test_rejects_old_major_only_python_probe_and_falls_back(self):
    simulated_39 = (
      'if [ "$1" = "-c" ]; then\n'
      '  case "$2" in\n'
      '    *"version_info.major == 3"*) exit 0 ;;\n'
      '  esac\n'
      'fi\n'
      'exit 39'
    )
    result = self.run_launcher(
      simulated_39,
      self.python_forwarder(),
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage:", result.stdout.lower())

  def test_no_usable_interpreter_is_actionable(self):
    result = self.run_launcher("exit 1", "exit 1")
    self.assertEqual(result.returncode, 127)
    self.assertIn("Python 3.10 or newer is required", result.stderr)

  def test_existing_python_entry_works_without_shell(self):
    result = capture_utf8(
      [sys.executable, str(PYTHON_ENTRY), "actions-policy", "--help"],
      cwd=ROOT,
      env=os.environ.copy(),
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage:", result.stdout.lower())

  def test_invalid_capture_decodes_on_calling_thread(self):
    # Windows subprocess text reader threads do not relay codec exceptions.
    for invalid_stream in ("stdout", "stderr"):
      with self.subTest(invalid_stream=invalid_stream):
        captured = subprocess.CompletedProcess(
          ["fake"], 0,
          stdout=b"\xff" if invalid_stream == "stdout" else b"valid",
          stderr=b"\xff" if invalid_stream == "stderr" else b"valid",
        )
        with patch("tests.test_launcher.subprocess.run", return_value=captured):
          with self.assertRaises(UnicodeDecodeError):
            capture_utf8(["fake"])

  def test_parent_capture_rejects_invalid_utf8(self):
    for file_descriptor in (1, 2):
      with self.subTest(file_descriptor=file_descriptor):
        with self.assertRaises(UnicodeDecodeError):
          capture_utf8(
            [sys.executable, "-c", f"import os; os.write({file_descriptor}, bytes([255]))"],
          )

  def test_shell_forwards_unicode_args_cwd_env_stdio_and_exit(self):
    shell = self.posix_shell()
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "path with space"
      root.mkdir()
      shutil.copyfile(LAUNCHER, root / "rwf")
      (root / "repo_workflow.py").write_text(
        "import json, os, sys\n"
        "payload = {\n"
        "  'args': sys.argv[1:], 'cwd': os.getcwd(),\n"
        "  'env': os.environ.get('RWF_TEST_MARKER'),\n"
        "  'stdin': sys.stdin.buffer.read().decode('utf-8', 'strict'),\n"
        "}\n"
        "os.write(1, (json.dumps(payload, ensure_ascii=False) + '\\n').encode('utf-8'))\n"
        "os.write(2, 'stderr-Ω\\n'.encode('utf-8'))\n"
        "raise SystemExit(23)\n",
        encoding="utf-8",
      )
      bindir = root / "bin"
      bindir.mkdir()
      candidate = bindir / "python3"
      candidate.write_text(
        f"#!/bin/sh\n{self.python_forwarder()}\n",
        encoding="utf-8",
      )
      candidate.chmod(0o755)
      env = os.environ.copy()
      env["RWF_TEST_MARKER"] = "value ☃"
      env["PATH"] = os.pathsep.join((str(bindir), env.get("PATH", "")))
      args = ["space here", 'quoted "text"', "Unicode Ω"]
      result = capture_utf8(
        [shell, str(root / "rwf"), *args],
        cwd=root,
        env=env,
        input="stdin ☃\n",
      )
      self.assertEqual(result.returncode, 23, result.stderr)
      actual = json.loads(result.stdout)
      self.assertTrue(Path(actual.pop("cwd")).samefile(root))
      self.assertEqual(actual, {
        "args": args,
        "env": "value ☃",
        "stdin": "stdin ☃\n",
      })
      self.assertIn("stderr-Ω", result.stderr)


if __name__ == "__main__":
  unittest.main()
