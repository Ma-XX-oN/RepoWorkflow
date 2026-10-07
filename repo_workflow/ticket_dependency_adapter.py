from __future__ import annotations

import json
from pathlib import Path
import sys
from dataclasses import dataclass
from typing import Any

from .git import changed_files, repository_state
from .process import run_command
from .repo_info_adapter import _github_repository


class TicketDependencyError(RuntimeError):
  pass


@dataclass(frozen=True)
class TicketRelationships:
  dependencies: tuple[int, ...]
  dependants: tuple[int, ...]


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


def resolve_dependency_config(
  root: Path,
  config: dict | None = None,
) -> dict:
  if config is None:
    config_path = root / ".ci" / "repoworkflow.json"
    if config_path.exists():
      from .config import load_config
      config = load_config(root)

  if config is not None and config.get("dependencyCommand"):
    return config

  remotes = run_command(["git", "remote"], root)
  if remotes.returncode:
    raise TicketDependencyError(
      "cannot discover ticket dependency provider from Git remotes"
    )
  repositories: set[str] = set()
  for remote in remotes.stdout.splitlines():
    name = remote.strip()
    if not name:
      continue
    value = run_command(["git", "remote", "get-url", name], root)
    if value.returncode:
      raise TicketDependencyError(f"cannot read Git remote URL for {name}")
    repository = _github_repository(value.stdout.strip())
    if repository is not None:
      repositories.add(repository)

  if not repositories:
    raise TicketDependencyError(
      "ticket dependency adapter is not configured and no GitHub remote "
      "could be discovered"
    )
  if len(repositories) != 1:
    raise TicketDependencyError(
      "ticket dependency provider discovery is ambiguous"
    )

  adapter = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "github-ticket-dependencies.py"
  )
  return {
    "dependencyCommand": [sys.executable, str(adapter)],
  }


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


def read_ticket_relationships(
  root: Path,
  config: dict,
  issue_number: int,
) -> TicketRelationships:
  issue = _positive(issue_number, "requested issue number")
  value = _invoke(root, config, ["dependency", "related", str(issue)])
  if not isinstance(value, dict) or set(value) != {
    "schema_version", "issue", "dependencies", "dependants"
  }:
    raise TicketDependencyError(
      "ticket dependency adapter returned invalid related result"
    )
  if value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
    raise TicketDependencyError(
      "ticket dependency adapter returned unsupported schema version"
    )
  returned_issue = _positive(value["issue"], "issue number")
  if returned_issue != issue:
    raise TicketDependencyError(
      "ticket dependency adapter returned the wrong issue number"
    )
  dependencies = _normalize_dependencies(value["dependencies"])
  dependants = _normalize_dependencies(value["dependants"])
  if issue in dependencies or issue in dependants:
    raise TicketDependencyError(
      "ticket dependency adapter returned self dependency"
    )
  return TicketRelationships(dependencies, dependants)


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
