from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence


@dataclass(frozen=True)
class BinaryCommandResult:
  command: list[str]
  returncode: int
  stdout: bytes
  stderr: bytes
  duration_seconds: float


@dataclass(frozen=True)
class CommandResult:
  command: list[str]
  returncode: int
  stdout: str
  stderr: str
  duration_seconds: float


def run_command_bytes(
  command: Sequence[str],
  root: Path,
  *,
  env: Mapping[str, str] | None = None,
  input_data: bytes | None = None,
) -> BinaryCommandResult:
  rendered = [str(value) for value in command]
  started = time.monotonic()
  try:
    completed = subprocess.run(
      rendered,
      cwd=root,
      env=dict(env) if env is not None else None,
      input=input_data,
      capture_output=True,
      check=False,
    )
  except (OSError, UnicodeError) as exc:
    return BinaryCommandResult(
      rendered, 2, b"", f"unable to execute command: {exc}".encode("utf-8"),
      time.monotonic() - started,
    )
  return BinaryCommandResult(
    rendered, completed.returncode, completed.stdout, completed.stderr,
    time.monotonic() - started,
  )


def run_command(
  command: Sequence[str],
  root: Path,
  *,
  env: Mapping[str, str] | None = None,
) -> CommandResult:
  result = run_command_bytes(command, root, env=env)
  try:
    stdout = result.stdout.decode("utf-8", "strict")
    stderr = result.stderr.decode("utf-8", "strict")
  except UnicodeDecodeError as exc:
    return CommandResult(
      result.command, 2, "", f"invalid UTF-8 command output: {exc}",
      result.duration_seconds,
    )
  return CommandResult(
    result.command, result.returncode, stdout, stderr, result.duration_seconds,
  )
