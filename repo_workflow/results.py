from __future__ import annotations

import json
from pathlib import Path
import platform
import sys
from typing import Any

from .artifacts import ARTIFACT_ENVIRONMENT_ID
from .guard import Candidate, validate_candidate, validate_stable_candidate
from .git import (
  changed_files,
  git,
  repository_state,
  restore_repository_state,
)
from .process import run_command


class ResultError(RuntimeError):
  pass


def _platform_name() -> str:
  if sys.platform.startswith("win"):
    return "windows"
  if sys.platform == "darwin":
    return "macos"
  if sys.platform.startswith("linux"):
    return "linux"
  return sys.platform


def _find_environment(config: dict, env_id: str) -> dict:
  for environment in config["environments"]:
    if environment["id"] == env_id:
      return environment
  raise ResultError(f"unknown environment: {env_id}")


def _run_environment_for_candidate(
  root: Path,
  config: dict,
  env_id: str,
  result_path: Path,
  candidate: Candidate,
) -> int:
  environment = _find_environment(config, env_id)
  required_platform = environment.get("platform", "any")
  actual_platform = _platform_name()
  result: dict[str, Any] = {
    "schema": 1,
    "environment": env_id,
    "required": bool(environment.get("required", True)),
    "version": candidate.version,
    "commit": candidate.commit,
    "declared": {
      "platform": required_platform,
      "capabilities": list(environment.get("capabilities", [])),
    },
    "runtime": {
      "platform": actual_platform,
      "python": platform.python_version(),
    },
    "status": "PASS",
    "command": list(environment["validationCommand"]),
  }
  if required_platform not in {"any", actual_platform}:
    result["status"] = "INCOMPLETE"
    result["message"] = (
      f"required platform {required_platform} is unavailable on {actual_platform}"
    )
    rc = 2
  else:
    before_state = repository_state(root)
    command_result = run_command(environment["validationCommand"], root)
    result["durationSeconds"] = command_result.duration_seconds
    result["stdout"] = command_result.stdout
    result["stderr"] = command_result.stderr
    result["returncode"] = command_result.returncode
    mutations = changed_files(root)
    after_state = repository_state(root)
    history_changed = after_state.commit != before_state.commit
    head_ref_changed = after_state.head_ref != before_state.head_ref
    refs_changed = after_state.refs != before_state.refs
    if mutations or history_changed or head_ref_changed or refs_changed:
      result["status"] = "FAIL"
      details = []
      if mutations:
        details.append("worktree=" + ", ".join(mutations))
      if history_changed:
        details.append("HEAD changed")
      if head_ref_changed:
        details.append("HEAD reference changed")
      if refs_changed:
        details.append("local Git refs changed")
      result["message"] = "validation modified repository state: " + "; ".join(details)
      restore_repository_state(root, before_state)
      rc = 1
    elif command_result.returncode == 0:
      rc = 0
    elif command_result.returncode == 2:
      result["status"] = "INCOMPLETE"
      rc = 2
    else:
      result["status"] = "FAIL"
      rc = 1
  result_path.parent.mkdir(parents=True, exist_ok=True)
  result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
  return rc


def run_environment(
  root: Path,
  config: dict,
  env_id: str,
  result_path: Path,
  *,
  expected_sha: str | None = None,
) -> int:
  candidate = validate_candidate(root, config, expected_sha=expected_sha)
  return _run_environment_for_candidate(root, config, env_id, result_path, candidate)


def run_stable_environment(
  root: Path,
  config: dict,
  env_id: str,
  result_path: Path,
  *,
  expected_sha: str | None = None,
) -> int:
  candidate = validate_stable_candidate(root, expected_sha=expected_sha)
  return _run_environment_for_candidate(root, config, env_id, result_path, candidate)


def collect_results(results_dir: Path) -> list[dict[str, Any]]:
  values: list[dict[str, Any]] = []
  for path in sorted(results_dir.rglob("*.json")):
    try:
      value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
      continue
    if isinstance(value, dict) and value.get("schema") == 1 and "environment" in value:
      values.append(value)
  return values


def evaluate_results(
  config: dict,
  results: list[dict[str, Any]],
  version: str,
  commit: str,
) -> tuple[str, str | None, list[str]]:
  configured = {env["id"] for env in config["environments"]}
  configured.add(ARTIFACT_ENVIRONMENT_ID)
  required = {
    env["id"] for env in config["environments"] if env.get("required", True)
  }
  if config.get("artifacts"):
    required.add(ARTIFACT_ENVIRONMENT_ID)
  by_environment: dict[str, dict[str, Any]] = {}
  for result in results:
    env_id = result.get("environment")
    if env_id not in configured:
      raise ResultError(f"unknown result environment: {env_id}")
    if env_id in by_environment:
      raise ResultError(f"duplicate result environment: {env_id}")
    if result.get("version") != version:
      raise ResultError(f"{env_id} result version does not match candidate")
    if result.get("commit") != commit:
      raise ResultError(f"{env_id} result commit does not match candidate")
    by_environment[env_id] = result
  warnings: list[str] = []
  missing = sorted(required - set(by_environment))
  if missing:
    warnings.append("missing required result(s): " + ", ".join(missing))
    return "INCOMPLETE", None, warnings
  incomplete = sorted(
    env_id for env_id in required
    if by_environment[env_id].get("status") == "INCOMPLETE"
  )
  if incomplete:
    warnings.append("required environment incomplete: " + ", ".join(incomplete))
    return "INCOMPLETE", None, warnings
  invalid = sorted(
    env_id for env_id in required
    if by_environment[env_id].get("status") not in {"PASS", "FAIL"}
  )
  if invalid:
    warnings.append("required environment has invalid status: " + ", ".join(invalid))
    return "INCOMPLETE", None, warnings
  failed = sorted(
    env_id for env_id in required
    if by_environment[env_id].get("status") == "FAIL"
  )
  if failed:
    return "FAIL", f"v{version}-CI-FAIL", warnings
  return "PASS", f"v{version}", warnings


def finalize_results(
  root: Path,
  results_dir: Path,
  *,
  do_tag: bool,
  push: bool,
  expected_sha: str | None = None,
) -> str:
  from .config import load_config

  if push and not do_tag:
    raise ResultError("push requires tag creation")
  config = load_config(root)
  candidate = validate_candidate(root, config, expected_sha=expected_sha)
  outcome, tag, warnings = evaluate_results(
    config,
    collect_results(results_dir),
    candidate.version,
    candidate.commit,
  )
  for warning in warnings:
    print(f"WARNING: {warning}", file=sys.stderr)
  print(f"CI outcome: {outcome}")
  if tag:
    print(f"Result tag: {tag}")
  if outcome == "INCOMPLETE":
    return outcome
  if do_tag and tag:
    git(root, "tag", "-a", tag, candidate.commit, "-m", tag)
    if push:
      git(root, "push", candidate.remote, f"refs/tags/{tag}")
  return outcome


def finalize_stable_results(
  root: Path,
  results_dir: Path,
  *,
  do_tag: bool,
  push: bool,
  expected_sha: str | None = None,
) -> str:
  from .config import load_config

  if push and not do_tag:
    raise ResultError("push requires tag creation")
  config = load_config(root)
  candidate = validate_stable_candidate(root, expected_sha=expected_sha)
  outcome, _development_tag, warnings = evaluate_results(
    config,
    collect_results(results_dir),
    candidate.version,
    candidate.commit,
  )
  for warning in warnings:
    print(f"WARNING: {warning}", file=sys.stderr)
  print(f"Stable release outcome: {outcome}")
  if outcome != "PASS":
    return outcome
  tag = f"v{candidate.version}"
  print(f"Stable release tag: {tag}")
  if do_tag:
    git(root, "tag", "-a", tag, candidate.commit, "-m", tag)
    if push:
      git(root, "push", candidate.remote, f"refs/tags/{tag}")
  return outcome
