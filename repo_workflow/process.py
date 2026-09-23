from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
  command: list[str]
  returncode: int
  stdout: str
  stderr: str
  duration_seconds: float


def run_command(
  command: Sequence[str],
  root: Path,
  *,
  env: Mapping[str, str] | None = None,
) -> CommandResult:
  rendered = [str(value) for value in command]
  started = time.monotonic()
  try:
    completed = subprocess.run(
      rendered,
      cwd=root,
      env=dict(env) if env is not None else None,
      text=True,
      capture_output=True,
      check=False,
    )
  except OSError as exc:
    return CommandResult(
      command=rendered,
      returncode=2,
      stdout="",
      stderr=f"unable to execute command: {exc}",
      duration_seconds=time.monotonic() - started,
    )
  return CommandResult(
    command=rendered,
    returncode=completed.returncode,
    stdout=completed.stdout,
    stderr=completed.stderr,
    duration_seconds=time.monotonic() - started,
  )
