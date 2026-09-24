from __future__ import annotations

import json
from pathlib import Path
import re

from .git import git


DEFAULT_PYTHON_VERSION = "3.13"
_TOOLCHAIN_CAPABILITY = re.compile(r"^(node|python)-([0-9]+(?:\.[0-9]+){0,2})$")


class AdapterError(RuntimeError):
  pass


def _toolchain_versions(capabilities) -> dict[str, str]:
  found: dict[str, set[str]] = {"node": set(), "python": set()}
  for capability in capabilities or []:
    match = _TOOLCHAIN_CAPABILITY.fullmatch(str(capability))
    if match is not None:
      found[match.group(1)].add(match.group(2))
  for tool, versions in found.items():
    if len(versions) > 1:
      raise AdapterError(
        f"conflicting {tool} toolchain capabilities: {', '.join(sorted(versions))}"
      )
  return {
    "nodeVersion": next(iter(found["node"]), ""),
    "pythonVersion": next(iter(found["python"]), DEFAULT_PYTHON_VERSION),
  }


def request_changed(root: Path, event_name: str, event_path: Path) -> bool:
  if event_name == "workflow_dispatch":
    return True
  if event_name != "push":
    return False
  try:
    event = json.loads(event_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as exc:
    raise AdapterError(f"cannot read GitHub event: {exc}") from exc
  before = str(event.get("before") or "")
  after = str(event.get("after") or "")
  if not after:
    raise AdapterError("push event is missing after SHA")

  if before and set(before) != {"0"}:
    completed = git(root, "diff", "--name-only", before, after, check=False)
    if completed.returncode:
      detail = (completed.stderr or completed.stdout).strip()
      raise AdapterError(f"cannot determine pushed paths: {detail}")
    return ".ci/run-ci-request" in set(completed.stdout.splitlines())

  commits = event.get("commits")
  if isinstance(commits, list):
    changed: set[str] = set()
    for commit in commits:
      if not isinstance(commit, dict):
        continue
      for key in ("added", "modified", "removed"):
        values = commit.get(key, [])
        if isinstance(values, list):
          changed.update(str(value) for value in values)
    if changed:
      return ".ci/run-ci-request" in changed

  completed = git(
    root,
    "diff-tree",
    "--root",
    "--no-commit-id",
    "--name-only",
    "-r",
    after,
    check=False,
  )
  if completed.returncode:
    detail = (completed.stderr or completed.stdout).strip()
    raise AdapterError(f"cannot determine pushed paths: {detail}")
  return ".ci/run-ci-request" in set(completed.stdout.splitlines())


def load_github_config(root: Path) -> dict:
  path = root / ".ci" / "github.json"
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as exc:
    raise AdapterError(f"missing GitHub adapter configuration: {path}") from exc
  except json.JSONDecodeError as exc:
    raise AdapterError(f"invalid GitHub adapter JSON: {exc}") from exc
  if not isinstance(value, dict) or value.get("schema") != 1:
    raise AdapterError("github.json must declare schema 1")
  runners = value.get("runners")
  if not isinstance(runners, dict):
    raise AdapterError("github.json runners mapping is required")
  prepare = value.get("prepareRunner")
  if not isinstance(prepare, str) or not prepare:
    raise AdapterError("github.json prepareRunner is required")
  unknown = sorted(set(value) - {"schema", "runners", "prepareRunner"})
  if unknown:
    raise AdapterError("github.json has unsupported fields: " + ", ".join(unknown))
  for key, runner in runners.items():
    if not isinstance(key, str) or not key or not isinstance(runner, str) or not runner:
      raise AdapterError("github.json runner mappings must use non-empty strings")
  return value


def github_matrix(config: dict, github_config: dict) -> dict:
  runners = github_config.get("runners", {})
  include = []
  for environment in config["environments"]:
    env_id = environment["id"]
    runner = runners.get(env_id)
    if not isinstance(runner, str) or not runner:
      raise AdapterError(f"no GitHub runner mapping for environment: {env_id}")
    include.append({
      "id": env_id,
      "runner": runner,
      **_toolchain_versions(environment.get("capabilities", [])),
    })
  extra = sorted(set(runners) - {env["id"] for env in config["environments"]})
  if extra:
    raise AdapterError("GitHub runner mapping has unknown environment(s): " + ", ".join(extra))
  return {"include": include}


def github_prepare_runner(github_config: dict) -> str:
  runner = github_config.get("prepareRunner")
  if not isinstance(runner, str) or not runner:
    raise AdapterError("GitHub prepare runner is not configured")
  return runner


def github_prepare_context(config: dict, github_config: dict) -> dict[str, str]:
  capabilities = []
  for artifact in config.get("artifacts", []):
    capabilities.extend(artifact.get("capabilities", []))
  return {
    "runner": github_prepare_runner(github_config),
    **_toolchain_versions(capabilities),
  }
