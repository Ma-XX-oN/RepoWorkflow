"""GitHub provider adapter for portable repo-ci v1.

This module only forwards mechanics and observations. Core owns all terminal
classification and lifecycle transitions. Compatibility cutover is separate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

from .github_result_transport import TransportError, fetch_bundle, publish_bundle
from .repo_ci_github_policy import check_github_policy


_OPERATIONS = {
  "inspect-context", "resolve-capabilities", "prepare", "execute",
  "publish", "fetch", "check-policy",
}


def _error(request: dict, code: str, message: str) -> dict:
  return {
    "contract_version": request.get("contract_version"),
    "operation": request.get("operation"),
    "invocation_id": request.get("invocation_id"),
    "candidate": request.get("candidate"),
    "status": "error",
    "observations": {},
    "diagnostics": [{"code": code, "message": message}],
    "artifacts": [],
  }


def _response(request: dict, observations: dict, artifacts: list) -> dict:
  return {
    "contract_version": request["contract_version"],
    "operation": request["operation"],
    "invocation_id": request["invocation_id"],
    "candidate": request["candidate"],
    "status": "ok",
    "observations": observations,
    "diagnostics": [],
    "artifacts": artifacts,
  }


def _directory(root: Path, value: object) -> Path:
  if not isinstance(value, str) or not value or "\x00" in value:
    raise TransportError("invalid directory")
  workspace = Path(os.environ.get("RWF_REPO_CI_TRANSPORT_ROOT", str(root))).resolve()
  path = Path(value)
  path = (path if path.is_absolute() else workspace / path).resolve()
  if not path.is_relative_to(workspace):
    raise TransportError("transport directory outside configured workspace")
  return path


def _transport(request: dict, root: Path) -> dict:
  inputs = request.get("inputs")
  requirements = request.get("requirements")
  if not isinstance(inputs, dict) or set(inputs) != {"source_dir", "destination_dir"}:
    raise TransportError("source_dir and destination_dir inputs required")
  if not isinstance(requirements, dict) or not isinstance(requirements.get("artifacts"), list):
    raise TransportError("artifact declaration required")
  source = _directory(root, inputs["source_dir"])
  destination = _directory(root, inputs["destination_dir"])
  declared = requirements["artifacts"]
  if request["operation"] == "publish":
    if any(not isinstance(n, str) or not n or "/" in n or "\\" in n for n in declared):
      raise TransportError("unsafe artifact declaration")
    records = {}
    for name in declared:
      if name in records:
        raise TransportError("duplicate artifact declaration")
      path = source / name
      if path.is_symlink() or not path.is_file():
        raise TransportError("missing declared artifact")
      records[name] = path.read_bytes()
    manifest = publish_bundle(request, records, destination)
    return _response(request, {"transport": "published", "count": len(records)},
                     manifest["artifacts"])
  if destination.exists():
    raise TransportError("retrieval destination already exists")
  records = fetch_bundle(source, request["invocation_id"],
                         request["candidate"], declared)
  destination.mkdir(parents=True, exist_ok=False)
  for name, data in records.items():
    (destination / name).write_bytes(data)
  return _response(request, {"transport": "fetched", "count": len(records)},
                   [{"name": name, "size": len(data)} for name, data in sorted(records.items())])




def _execute_consumer(request: dict, root: Path) -> dict:
  """Invoke core's existing validator; transport its facts unchanged."""
  inputs = request.get("inputs")
  requirements = request.get("requirements")
  candidate = request.get("candidate")
  if not isinstance(inputs, dict) or not isinstance(requirements, dict):
    return _error(request, "invalid-request", "consumer execution inputs required")
  if set(inputs) != {"consumer_workspace", "result_path", "mode", "base"}:
    return _error(request, "invalid-request", "invalid consumer execution inputs")
  stages = requirements.get("stages")
  if not isinstance(stages, list) or len(stages) != 1 or (
    not isinstance(stages[0], str) or not stages[0]
  ):
    return _error(request, "invalid-request", "one environment stage required")
  if not isinstance(candidate, dict) or not all(
    isinstance(candidate.get(k), str) and candidate[k]
    for k in ("repository", "commit", "base")
  ):
    return _error(request, "invalid-request", "candidate identity required")
  if inputs["base"] != candidate["base"]:
    return _error(request, "identity-mismatch", "base identity mismatch")
  if inputs["mode"] not in ("development", "stable"):
    return _error(request, "invalid-request", "invalid execution mode")
  allowed_workspace = os.environ.get("RWF_REPO_CI_WORKSPACE")
  allowed_results = os.environ.get("RWF_REPO_CI_RESULT_ROOT")
  if not allowed_workspace or not allowed_results:
    return _error(request, "prerequisite-unavailable", "consumer boundary unconfigured")
  workspace = Path(inputs["consumer_workspace"]).resolve()
  results_root = Path(allowed_results).resolve()
  destination = Path(inputs["result_path"]).resolve()
  if workspace != Path(allowed_workspace).resolve() or not (
    destination.is_relative_to(results_root)
    and destination.suffix == ".json"
    and destination != results_root
  ):
    return _error(request, "invalid-request", "consumer workspace or output not permitted")
  if destination.exists():
    return _error(request, "transport-failed", "existing result cannot be overwritten")
  try:
    head = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True,
      text=True, check=True, timeout=10,
    ).stdout.strip()
  except (OSError, subprocess.SubprocessError):
    return _error(request, "prerequisite-unavailable", "consumer checkout unavailable")
  if head != candidate["commit"]:
    return _error(request, "identity-mismatch", "candidate not checked out")
  if os.environ.get("GITHUB_REPOSITORY") not in (None, candidate["repository"]):
    return _error(request, "identity-mismatch", "repository identity mismatch")
  executable = root / "repo_workflow.py"
  operation = "stable-run" if inputs["mode"] == "stable" else "run"
  command = [
    sys.executable, str(executable), operation, "--environment", stages[0],
    "--expected-sha", candidate["commit"], "--result", str(destination),
  ]
  try:
    completed = subprocess.run(
      command, cwd=workspace, capture_output=True, timeout=3500, check=False,
    )
  except (OSError, subprocess.TimeoutExpired):
    return _error(request, "execution-unavailable", "core validator unavailable")
  try:
    observed = json.loads(destination.read_text(encoding="utf-8"))
  except (OSError, UnicodeError, ValueError):
    return _error(request, "transport-failed", "core result missing or malformed")
  if (
    not isinstance(observed, dict)
    or observed.get("schema") != 1
    or observed.get("commit") != candidate["commit"]
    or observed.get("environment") != stages[0]
    or observed.get("status") not in ("PASS", "FAIL", "INCOMPLETE")
    or completed.returncode not in (0, 1, 2)
  ):
    return _error(request, "integrity-failed", "core result identity or status invalid")
  return _response(request, {
    "stages": [{
      "stage": stages[0], "candidate": candidate,
      "complete": True, "outcome": "core-reported",
      "core_result": observed, "core_exit_code": completed.returncode,
    }],
  }, [])


def _execute(request: dict, root: Path) -> dict:
  """Run explicitly declared catalogue groups; report facts, not PASS."""
  from .self_ci import SelfCiError, group_command

  requirements = request.get("requirements")
  inputs = request.get("inputs")
  candidate = request.get("candidate")
  if isinstance(inputs, dict) and "consumer_workspace" in inputs:
    return _execute_consumer(request, root)
  if not isinstance(requirements, dict) or not isinstance(inputs, dict):
    return _error(request, "invalid-request", "invalid execute envelope")
  stages = requirements.get("stages")
  groups = inputs.get("stage_groups")
  if (not isinstance(stages, list) or not isinstance(groups, dict)
      or len(stages) != len(set(x for x in stages if isinstance(x, str)))
      or not all(isinstance(x, str) and x for x in stages)
      or set(groups) != set(stages)
      or not all(isinstance(v, str) and v for v in groups.values())):
    return _error(request, "invalid-request", "stage/group declaration mismatch")
  if not isinstance(candidate, dict):
    return _error(request, "invalid-request", "candidate identity required")
  try:
    head = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
      text=True, check=True, timeout=10,
    ).stdout.strip()
  except (OSError, subprocess.SubprocessError):
    return _error(request, "prerequisite-unavailable", "checkout unavailable")
  if candidate.get("commit") != head:
    return _error(request, "identity-mismatch", "candidate is not checked out")
  base = inputs.get("base")
  if not isinstance(base, str) or base != candidate.get("base"):
    return _error(request, "identity-mismatch", "base identity mismatch")
  commands = {}
  for stage in stages:
    try:
      commands[stage] = group_command(root, groups[stage])
    except (SelfCiError, OSError, ValueError) as exc:
      return _error(request, "prerequisite-unavailable",
                    f"unavailable declared test group for {stage}: {exc}")
  observations = []
  for stage in stages:
    try:
      result = subprocess.run(
        commands[stage], cwd=root, capture_output=True, timeout=120, check=False,
      )
    except (OSError, subprocess.TimeoutExpired):
      observations.append({
        "stage": stage, "candidate": candidate, "complete": False,
        "outcome": "unavailable",
      })
      continue
    observations.append({
      "stage": stage, "candidate": candidate, "complete": True,
      "outcome": "succeeded" if result.returncode == 0 else "failed",
      "exit_code": result.returncode,
    })
  return _response(request, {"stages": observations}, [])

def handle_request(request: dict, root: Path) -> dict:
  operation = request.get("operation")
  if operation not in _OPERATIONS:
    return _error(request, "unsupported-operation", "unsupported operation")
  if operation in {"inspect-context", "resolve-capabilities", "prepare"}:
    source = root / "adapters" / "repo-ci-github-event.py"
    return runpy.run_path(str(source))["map_request"](request)
  if operation == "check-policy":
    return check_github_policy(request, root=root, engine_root=root)
  if operation == "execute":
    return _execute(request, root)
  try:
    return _transport(request, root)
  except TransportError as exc:
    message = str(exc)
    code = ("identity-mismatch" if "identity" in message
            else "integrity-failed" if "integrity" in message
            else "transport-failed")
    return _error(request, code, message)
  except OSError:
    return _error(request, "transport-failed", "transport filesystem failure")


def main() -> int:
  try:
    if len(sys.argv) != 2:
      raise ValueError("expected one operation")
    request = json.load(sys.stdin)
    if not isinstance(request, dict) or request.get("operation") != sys.argv[1]:
      raise ValueError("mismatched or invalid request")
    result = handle_request(request, Path.cwd())
  except (ValueError, UnicodeError) as exc:
    print(json.dumps({"code": "invalid-request", "message": str(exc)}),
          file=sys.stderr)
    return 2
  print(json.dumps(result, separators=(",", ":")))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
