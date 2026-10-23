from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "rwf"
PYTHON_ENTRY = ROOT / "repo_workflow.py"


class LauncherTests(unittest.TestCase):
  def posix_shell(self):
    if os.name == "nt":
      self.skipTest("POSIX shell launcher is not a native Windows executable")
    shell = shutil.which("sh")
    if shell is None:
      self.skipTest("POSIX shell is unavailable")
    return shell

  def run_launcher(self, python3: str | None, python: str | None):
    shell = self.posix_shell()
    with tempfile.TemporaryDirectory() as tmp:
      bindir = Path(tmp)
      for name, body in (("python3", python3), ("python", python)):
        if body is not None:
          path = bindir / name
          path.write_text(
            f"#!{shell}\n{body}\n",
            encoding="utf-8",
          )
          path.chmod(0o755)
      env = os.environ.copy()
      env["PATH"] = os.pathsep.join((str(bindir), env.get("PATH", "")))
      return subprocess.run(
        [shell, str(LAUNCHER), "actions-policy", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
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
    result = subprocess.run(
      [sys.executable, str(PYTHON_ENTRY), "actions-policy", "--help"],
      cwd=ROOT,
      env=os.environ.copy(),
      text=True,
      capture_output=True,
      check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage:", result.stdout.lower())

  def test_shell_forwards_unicode_args_cwd_env_stdio_and_exit(self):
    shell = self.posix_shell()
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "path with space"
      root.mkdir()
      shutil.copyfile(LAUNCHER, root / "rwf")
      (root / "repo_workflow.py").write_text(
        "import json, os, sys\n"
        "print(json.dumps({\n"
        "  'args': sys.argv[1:], 'cwd': os.getcwd(),\n"
        "  'env': os.environ.get('RWF_TEST_MARKER'),\n"
        "  'stdin': sys.stdin.read(),\n"
        "}, ensure_ascii=False))\n"
        "print('stderr-Ω', file=sys.stderr)\n"
        "raise SystemExit(23)\n",
        encoding="utf-8",
      )
      bindir = root / "bin"
      bindir.mkdir()
      candidate = bindir / "python3"
      candidate.write_text(
        f"#!{shell}\n{self.python_forwarder()}\n",
        encoding="utf-8",
      )
      candidate.chmod(0o755)
      env = os.environ.copy()
      env["RWF_TEST_MARKER"] = "value ☃"
      env["PATH"] = os.pathsep.join((str(bindir), env.get("PATH", "")))
      args = ["space here", 'quoted "text"', "Unicode Ω"]
      result = subprocess.run(
        [shell, str(root / "rwf"), *args],
        cwd=root,
        env=env,
        input="stdin ☃\n",
        text=True,
        capture_output=True,
        check=False,
      )
      self.assertEqual(result.returncode, 23, result.stderr)
      self.assertEqual(json.loads(result.stdout), {
        "args": args,
        "cwd": str(root.resolve()),
        "env": "value ☃",
        "stdin": "stdin ☃\n",
      })
      self.assertIn("stderr-Ω", result.stderr)


if __name__ == "__main__":
  unittest.main()
