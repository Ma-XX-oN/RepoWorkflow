from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

from .process import CommandResult, run_command


def run_series(
  commands: Sequence[Sequence[str]],
  *,
  root: Path | None = None,
  continue_on_failure: bool = False,
) -> list[CommandResult]:
  cwd = (root or Path.cwd()).resolve()
  results: list[CommandResult] = []
  for command in commands:
    result = run_command(command, cwd)
    results.append(result)
    if result.returncode and not continue_on_failure:
      break
  return results


def run_parallel(
  commands: Sequence[Sequence[str]],
  *,
  root: Path | None = None,
  max_workers: int | None = None,
) -> list[CommandResult]:
  cwd = (root or Path.cwd()).resolve()
  results: list[CommandResult | None] = [None] * len(commands)
  with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_index = {
      executor.submit(run_command, command, cwd): index
      for index, command in enumerate(commands)
    }
    for future in as_completed(future_to_index):
      results[future_to_index[future]] = future.result()
  return [result for result in results if result is not None]
