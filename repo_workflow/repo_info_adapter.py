from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

from .git import changed_files, repository_state
from .process import run_command


class RepoInfoError(RuntimeError):
  pass


def _fail(label: str) -> RepoInfoError:
  return RepoInfoError(f"repository information adapter returned invalid {label}")


def _exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
  if not isinstance(value, dict) or set(value) != fields:
    raise _fail(label)
  return value


def _positive_integer(value: Any, label: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise _fail(label)
  return value


def _nonempty_text(value: Any, label: str) -> str:
  if not isinstance(value, str) or not value:
    raise _fail(label)
  return value


def _schema(value: dict[str, Any], label: str) -> None:
  schema = value["schema_version"]
  if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
    raise RepoInfoError(
      f"repository information adapter returned unsupported {label} schema version"
    )


def _github_repository(url: str) -> str | None:
  value = url.strip()
  patterns = (
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
    r"^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
    r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$",
  )
  for pattern in patterns:
    match = re.fullmatch(pattern, value)
    if match:
      return f"{match.group(1)}/{match.group(2)}"
  return None


def resolve_info_config(root: Path, config: dict | None = None) -> dict:
  if config is None:
    config_path = root / ".ci" / "repoworkflow.json"
    if config_path.exists():
      from .config import load_config
      config = load_config(root)

  if config is not None and config.get("infoCommand"):
    return config

  remotes = run_command(["git", "remote"], root)
  if remotes.returncode:
    raise RepoInfoError("cannot discover repository provider from Git remotes")
  repositories: set[str] = set()
  for remote in remotes.stdout.splitlines():
    name = remote.strip()
    if not name:
      continue
    value = run_command(["git", "remote", "get-url", name], root)
    if value.returncode:
      raise RepoInfoError(f"cannot read Git remote URL for {name}")
    repository = _github_repository(value.stdout.strip())
    if repository is not None:
      repositories.add(repository)

  if not repositories:
    raise RepoInfoError(
      "repository information adapter is not configured and no GitHub remote "
      "could be discovered"
    )
  if len(repositories) != 1:
    raise RepoInfoError("repository information provider discovery is ambiguous")

  adapter = (
    Path(__file__).resolve().parents[1] / "adapters" / "repo-info-github.py"
  )
  repository = next(iter(repositories))
  return {
    "infoCommand": [
      sys.executable,
      str(adapter),
      "--repository",
      repository,
    ],
  }


def _invoke(root: Path, config: dict, arguments: list[str]) -> Any:
  command = config.get("infoCommand")
  if not isinstance(command, list) or not command or not all(
    isinstance(item, str) and item for item in command
  ):
    raise RepoInfoError("repository information adapter is not configured")
  before_state = repository_state(root)
  before_changes = changed_files(root)
  result = run_command([*command, *arguments], root)
  after_state = repository_state(root)
  after_changes = changed_files(root)
  if after_state != before_state or after_changes != before_changes:
    raise RepoInfoError("repository information adapter modified repository state")
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise RepoInfoError(
      "repository information adapter failed"
      + (f": {detail}" if detail else "")
    )
  try:
    return json.loads(result.stdout)
  except json.JSONDecodeError as exc:
    raise RepoInfoError(
      "repository information adapter returned malformed JSON"
    ) from exc


def repository_info(root: Path, config: dict) -> dict[str, Any]:
  value = _exact_object(
    _invoke(root, config, ["repository"]),
    {"schema_version", "repository", "provider"},
    "repository result",
  )
  _schema(value, "repository")
  _nonempty_text(value["repository"], "repository identity")
  _nonempty_text(value["provider"], "provider identity")
  return value


def issue_info(root: Path, config: dict, issue_number: int) -> dict[str, Any]:
  requested = _positive_integer(issue_number, "requested issue number")
  value = _exact_object(
    _invoke(root, config, ["issue", "get", str(requested)]),
    {"schema_version", "number", "title", "state", "link"},
    "issue result",
  )
  _schema(value, "issue")
  returned = _positive_integer(value["number"], "issue number")
  if returned != requested:
    raise RepoInfoError(
      "repository information adapter returned the wrong issue number"
    )
  _nonempty_text(value["title"], "issue title")
  link = _nonempty_text(value["link"], "issue link")
  if not (link.startswith("https://") or link.startswith("http://")):
    raise _fail("issue link")
  if not isinstance(value["state"], str) or value["state"] not in {"open", "closed"}:
    raise _fail("issue state")
  return value


def list_open_issues(root: Path, config: dict) -> dict[str, Any]:
  value = _exact_object(
    _invoke(root, config, ["issue", "list-open"]),
    {"schema_version", "issues"},
    "open-issue list result",
  )
  _schema(value, "open-issue list")
  issues = value["issues"]
  if not isinstance(issues, list):
    raise _fail("open-issue list")
  prior = 0
  for item in issues:
    issue = _exact_object(item, {"number", "title"}, "open-issue entry")
    number = _positive_integer(issue["number"], "open-issue number")
    _nonempty_text(issue["title"], "open-issue title")
    if number <= prior:
      raise RepoInfoError(
        "repository information adapter returned unsorted or duplicate issues"
      )
    prior = number
  return value
