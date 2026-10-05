from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .git import changed_files, repository_state
from .process import run_command


class TicketDependencyError(RuntimeError):
  pass


def _positive(value: Any, label: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise TicketDependencyError(f"ticket dependency adapter returned invalid {label}")
  return value


def _normalize_dependencies(value: Any) -> tuple[int, ...]:
  if not isinstance(value, list):
    raise TicketDependencyError(
      "ticket dependency adapter returned invalid dependency set"
    )
  dependencies = tuple(_positive(item, "dependency number") for item in value)
  if tuple(sorted(set(dependencies))) != dependencies:
    raise TicketDependencyError(
      "ticket dependency adapter returned unsorted or duplicate dependencies"
    )
  return dependencies


def _invoke(root: Path, config: dict, arguments: list[str]) -> Any:
  command = config.get("dependencyCommand")
  if not isinstance(command, list) or not command or not all(
    isinstance(item, str) and item for item in command
  ):
    raise TicketDependencyError("ticket dependency adapter is not configured")

  before_state = repository_state(root)
  before_changes = changed_files(root)
  result = run_command([*command, *arguments], root)
  after_state = repository_state(root)
  after_changes = changed_files(root)
  if after_state != before_state or after_changes != before_changes:
    raise TicketDependencyError("ticket dependency adapter modified repository state")
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise TicketDependencyError(
      "ticket dependency adapter failed" + (f": {detail}" if detail else "")
    )
  try:
    return json.loads(result.stdout)
  except json.JSONDecodeError as exc:
    raise TicketDependencyError(
      "ticket dependency adapter returned malformed JSON"
    ) from exc


def _result(value: Any, requested: int) -> tuple[int, ...]:
  if not isinstance(value, dict) or set(value) != {
    "schema_version", "issue", "dependencies"
  }:
    raise TicketDependencyError("ticket dependency adapter returned invalid result")
  if value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
    raise TicketDependencyError(
      "ticket dependency adapter returned unsupported schema version"
    )
  issue = _positive(value["issue"], "issue number")
  if issue != requested:
    raise TicketDependencyError(
      "ticket dependency adapter returned the wrong issue number"
    )
  dependencies = _normalize_dependencies(value["dependencies"])
  if requested in dependencies:
    raise TicketDependencyError(
      "ticket dependency adapter returned self dependency"
    )
  return dependencies


def read_ticket_dependencies(
  root: Path,
  config: dict,
  issue_number: int,
) -> tuple[int, ...]:
  issue = _positive(issue_number, "requested issue number")
  return _result(
    _invoke(root, config, ["dependency", "get", str(issue)]),
    issue,
  )


def replace_ticket_dependencies(
  root: Path,
  config: dict,
  issue_number: int,
  dependencies: list[int] | tuple[int, ...],
) -> tuple[int, ...]:
  issue = _positive(issue_number, "requested issue number")
  normalized = tuple(sorted(set(
    _positive(item, "requested dependency number") for item in dependencies
  )))
  if issue in normalized:
    raise TicketDependencyError("ticket dependency replacement contains self dependency")
  result = _result(
    _invoke(
      root,
      config,
      ["dependency", "replace", str(issue), *(str(item) for item in normalized)],
    ),
    issue,
  )
  if result != normalized:
    raise TicketDependencyError(
      "ticket dependency adapter did not confirm the requested complete set"
    )
  return result
