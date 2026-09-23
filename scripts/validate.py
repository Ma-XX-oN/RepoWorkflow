#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> int:
  return subprocess.run([sys.executable, *args], cwd=ROOT, check=False).returncode


def main() -> int:
  compile_rc = run(
    "-m", "compileall", "-q", "repo_workflow", "repo_workflow.py", "helpers", "tests"
  )
  test_rc = run("-m", "unittest", "discover", "-s", "tests", "-v")
  if compile_rc:
    return 1
  return 0 if test_rc == 0 else 1


if __name__ == "__main__":
  raise SystemExit(main())
