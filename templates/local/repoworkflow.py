#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "RepoWorkflow" / "repo_workflow.py"
FORCE_FLAG = "--force-repair"


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    command,
    cwd=ROOT,
    check=check,
    capture_output=True,
    text=True,
  )


def expected_pin() -> str:
  result = run(["git", "rev-parse", "HEAD:RepoWorkflow"])
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError(f"cannot read RepoWorkflow gitlink: {detail}")
  return result.stdout.strip()


def actual_pin() -> str | None:
  result = run(["git", "-C", "RepoWorkflow", "rev-parse", "HEAD"])
  if result.returncode:
    return None
  return result.stdout.strip()


def repair() -> None:
  result = run([
    "git", "submodule", "update", "--init", "--recursive", "--force", "RepoWorkflow"
  ])
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError(f"RepoWorkflow repair failed: {detail}")


def main(argv: list[str] | None = None) -> int:
  args = list(sys.argv[1:] if argv is None else argv)
  force = FORCE_FLAG in args
  args = [arg for arg in args if arg != FORCE_FLAG]

  expected = expected_pin()
  actual = actual_pin()
  if force or actual != expected:
    repair()
    actual = actual_pin()
  if actual != expected:
    raise RuntimeError(
      f"RepoWorkflow checkout {actual or '<missing>'} does not match pinned {expected}"
    )

  result = subprocess.run([sys.executable, str(ENGINE), *args], cwd=ROOT)
  return result.returncode


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except RuntimeError as exc:
    print(f"RepoWorkflow launcher error: {exc}", file=sys.stderr)
    raise SystemExit(2)
