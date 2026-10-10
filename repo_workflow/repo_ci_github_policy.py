"""Read-only GitHub workflow-policy adapter for portable repo-ci v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .actions_policy import ActionsPolicyError, check_actions_policy


_OPERATIONS = {"check-policy"}
_REQUIRED = {"contract_version", "operation", "invocation_id",
             "candidate", "requirements", "inputs"}
_CANDIDATE_FIELDS = {"repository", "commit", "base"}


def _error(request: object, code: str, message: str) -> dict[str, Any]:
  source = request if isinstance(request, dict) else {}
  return {
    "contract_version": 1,
    "operation": source.get("operation"),
    "invocation_id": source.get("invocation_id"),
    "candidate": source.get("candidate"),
    "status": "error",
    "observations": {},
    "diagnostics": [{"code": code, "message": message}],
    "artifacts": [],
  }


def _valid_identity(value: object) -> bool:
  return isinstance(value, str) and bool(value) and not any(
    ord(char) < 32 or ord(char) == 127 for char in value
  )


def check_github_policy(
  request: object, *, root: Path, engine_root: Path,
  migration_workflows: list[str] | None = None,
) -> dict[str, Any]:
  """Inspect declared GitHub workflow bootstrap without mutating repository state."""
  if not isinstance(request, dict):
    return _error(request, "invalid-request", "request must be an object")
  if type(request.get("contract_version")) is not int or request["contract_version"] != 1:
    return _error(request, "unsupported-version", "expected contract_version 1")
  if request.get("operation") != "check-policy":
    return _error(request, "unsupported-operation", "only check-policy is supported")
  if set(request) != _REQUIRED:
    return _error(request, "invalid-request", "request fields do not match v1 envelope")
  if not _valid_identity(request["invocation_id"]):
    return _error(request, "invalid-request", "invocation_id is required")
  candidate = request["candidate"]
  if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_FIELDS or not all(
    _valid_identity(candidate[field]) for field in _CANDIDATE_FIELDS
  ):
    return _error(request, "invalid-request", "exact candidate identity is required")
  requirements = request["requirements"]
  if not isinstance(requirements, dict) or set(requirements) != {
    "stages", "capabilities", "artifacts"
  } or any(not isinstance(requirements[key], list) for key in requirements):
    return _error(request, "invalid-request", "requirements collections are required")
  if any(requirements[key] for key in ("stages", "capabilities", "artifacts")):
    return _error(request, "capability-unavailable", "policy adapter has no execution capabilities")
  inputs = request["inputs"]
  if not isinstance(inputs, dict) or set(inputs) != {"policies"}:
    return _error(request, "invalid-request", "inputs.policies is required")
  policies = inputs["policies"]
  if not isinstance(policies, list) or not policies or any(
    policy != "canonical-bootstrap" for policy in policies
  ) or len(policies) != 1:
    return _error(request, "invalid-request", "unknown or duplicated policy")
  try:
    check_actions_policy(root, engine_root, migration_workflows=migration_workflows)
    observations = {"policies": [{
      "id": "canonical-bootstrap", "satisfied": True,
    }]}
    diagnostics: list[dict[str, str]] = []
  except (ActionsPolicyError, OSError) as exc:
    observations = {"policies": [{
      "id": "canonical-bootstrap", "satisfied": False,
    }]}
    diagnostics = [{"code": "prerequisite-unavailable", "message": str(exc)}]
  return {
    "contract_version": 1,
    "operation": request["operation"],
    "invocation_id": request["invocation_id"],
    "candidate": candidate,
    "status": "ok",
    "observations": observations,
    "diagnostics": diagnostics,
    "artifacts": [],
  }
