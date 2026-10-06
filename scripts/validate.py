#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.relationship_store import (
  RelationshipStore,
  RelationshipStoreError,
)


def run(*args: str) -> int:
  return subprocess.run([sys.executable, *args], cwd=ROOT, check=False).returncode


def main() -> int:
  try:
    RelationshipStore(ROOT).read()
  except RelationshipStoreError as error:
    print(f"repository ticket state is invalid: {error}", file=sys.stderr)
    return 1

  compile_rc = run(
    "-m", "compileall", "-q", "repo_workflow", "repo_workflow.py", "helpers", "tests"
  )
  test_rc = run("-m", "unittest", "discover", "-s", "tests", "-v")
  if compile_rc:
    return 1
  return 0 if test_rc == 0 else 1


if __name__ == "__main__":
  raise SystemExit(main())
