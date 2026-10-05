from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "rwf"


class LauncherTests(unittest.TestCase):
  def run_launcher(self, python3: str | None, python: str | None):
    with tempfile.TemporaryDirectory() as tmp:
      bindir = Path(tmp)
      for name, body in (("python3", python3), ("python", python)):
        if body is not None:
          path = bindir / name
          path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
          path.chmod(0o755)
      env = os.environ.copy()
      env["PATH"] = f"{bindir}:/bin:/usr/bin"
      return subprocess.run(
        ["/bin/sh", str(LAUNCHER), "actions-policy", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
      )

  def test_falls_back_from_broken_python3_to_python(self):
    result = self.run_launcher(
      "exit 9009",
      "exec /usr/bin/python3 \"$@\"",
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage:", result.stdout.lower())

  def test_rejects_non_python3_candidate_and_falls_back(self):
    result = self.run_launcher(
      "exit 1",
      "exec /usr/bin/python3 \"$@\"",
    )
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_no_usable_interpreter_is_actionable(self):
    result = self.run_launcher("exit 1", "exit 1")
    self.assertEqual(result.returncode, 127)
    self.assertIn("Python 3 is required", result.stderr)


if __name__ == "__main__":
  unittest.main()
