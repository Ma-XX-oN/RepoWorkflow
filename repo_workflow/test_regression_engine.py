"""Authoritative engine checkout self-regression adapter."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def self_regression(root: Path, *, stage: str = "regression") -> str:
  if stage not in {"regression", "integration"}:
    raise ValueError("invalid regression adapter stage")
  with tempfile.TemporaryDirectory(prefix="rwf-self-regression-cache-") as cache:
    result = subprocess.run(
      [sys.executable, str(root / "scripts" / "validate.py"), stage],
      cwd=root, capture_output=True, text=True, check=False,
      env={**os.environ, "PYTHONPYCACHEPREFIX": cache},
    )
  if result.stdout:
    print(result.stdout, end="")
  if result.stderr:
    print(result.stderr, end="", file=sys.stderr)
  return "PASS" if result.returncode == 0 else "FAIL"
