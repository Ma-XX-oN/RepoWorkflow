"""Provider-neutral repository-host mutation dispatcher."""
from __future__ import annotations

import json
import re
import subprocess


class HostMutationError(RuntimeError):
  def __init__(self, message, code="invalid_response"):
    super().__init__(message)
    self.code = code


_OPERATIONS = (
  "issue.update", "issue.comment", "pull_request.create",
  "pull_request.update", "pull_request.merge", "check.publish",
)
_ERRORS = {
  "invalid_request", "unsupported", "unauthenticated", "unauthorized",
  "not_found", "conflict", "rate_limited", "transport_failure",
  "provider_failure", "invalid_response", "unknown_outcome",
}
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_REQUIRED = {
  "capabilities": set(),
  "issue.update": {"number"},
  "issue.comment": {"number", "body"},
  "pull_request.create": {
    "source_ref", "target_ref", "expected_source_sha",
    "title", "body", "draft",
  },
  "pull_request.update": {"number", "expected_head_sha"},
  "pull_request.merge": {
    "number", "tested_head_sha", "expected_destination_sha",
    "eligibility_ref", "authorization_ref",
  },
  "check.publish": {
    "candidate_sha", "context", "verification_ref", "conclusion",
  },
}
_OPTIONAL = {
  "issue.update": {"title", "state"},
  "pull_request.update": {"title", "body", "draft", "state", "target_ref"},
}
_RESULTS = {
  "issue.update": {"number", "title", "state"},
  "issue.comment": {"number", "comment_id"},
  "pull_request.create": {
    "number", "source_ref", "target_ref", "head_sha", "draft",
  },
  "pull_request.update": {
    "number", "head_sha", "target_ref", "draft", "state",
  },
  "pull_request.merge": {
    "number", "merged_head_sha", "destination_sha",
  },
  "check.publish": {
    "candidate_sha", "context", "check_id", "conclusion",
  },
}


def _positive(value):
  return type(value) is int and value > 0


def _string(value, *, allow_empty=False):
  return isinstance(value, str) and (allow_empty or bool(value))


def _valid_fields(operation, fields):
  if type(fields) is not dict:
    return False
  required = _REQUIRED[operation]
  optional = _OPTIONAL.get(operation, set())
  if not required <= fields.keys() or not fields.keys() <= required | optional:
    return False
  if operation in ("issue.update", "pull_request.update"):
    if not (fields.keys() & optional):
      return False
  for key, value in fields.items():
    if key == "number":
      valid = _positive(value)
    elif key in (
      "expected_head_sha", "expected_source_sha",
      "expected_destination_sha", "tested_head_sha", "candidate_sha",
    ):
      valid = _string(value) and bool(_SHA.fullmatch(value))
    elif key == "draft":
      valid = type(value) is bool
    elif key == "state":
      valid = value in ("open", "closed") and type(value) is str
    elif key == "conclusion":
      valid = value in ("success", "failure") and type(value) is str
    else:
      valid = _string(value, allow_empty=key == "body" and operation in (
        "pull_request.create", "pull_request.update",
      ))
    if not valid:
      return False
  return True


def _validate_request(request):
  if type(request) is not dict or set(request) != {
    "schema_version", "operation", "repository", "request_id", "parameters",
  }:
    raise HostMutationError("invalid host mutation request", "invalid_request")
  if type(request["schema_version"]) is not int or request["schema_version"] != 1:
    raise HostMutationError("unsupported host mutation schema", "unsupported")
  operation = request["operation"]
  if type(operation) is not str or operation not in _REQUIRED:
    raise HostMutationError("unsupported host mutation operation", "unsupported")
  if not _string(request["repository"]) or not _REPOSITORY.fullmatch(
    request["repository"]
  ):
    raise HostMutationError("invalid repository identity", "invalid_request")
  if not _string(request["request_id"]) or not _ID.fullmatch(
    request["request_id"]
  ):
    raise HostMutationError("invalid request identity", "invalid_request")
  if not _valid_fields(operation, request["parameters"]):
    raise HostMutationError("invalid operation parameters", "invalid_request")


def _validate_result(reply, request):
  if type(reply) is not dict or set(reply) != {
    "schema_version", "operation", "repository", "request_id",
    "status", "result",
  }:
    raise HostMutationError("invalid provider response")
  for field in ("operation", "repository", "request_id"):
    if type(reply[field]) is not str or reply[field] != request[field]:
      raise HostMutationError("provider identity mismatch")
  if type(reply["schema_version"]) is not int or reply["schema_version"] != 1:
    raise HostMutationError("provider schema mismatch")
  status = reply["status"]
  operation = request["operation"]
  if status not in ("applied", "unchanged") or type(status) is not str:
    raise HostMutationError("invalid provider success status")
  if operation == "capabilities":
    if status != "unchanged" or type(reply["result"]) is not dict:
      raise HostMutationError("invalid capability response")
    if set(reply["result"]) != {"operations"}:
      raise HostMutationError("invalid capability response")
    ops = reply["result"]["operations"]
    if type(ops) is not dict or set(ops) != set(_OPERATIONS):
      raise HostMutationError("invalid capability map")
    if any(type(value) is not bool for value in ops.values()):
      raise HostMutationError("invalid capability values")
    return reply
  result = reply["result"]
  if type(result) is not dict or set(result) != _RESULTS[operation]:
    raise HostMutationError("invalid operation result")
  for key, value in result.items():
    if key == "number":
      good = _positive(value)
    elif key == "draft":
      good = type(value) is bool
    elif key == "state":
      good = type(value) is str and value in ("open", "closed")
    elif key == "conclusion":
      good = type(value) is str and value in ("success", "failure")
    elif key.endswith("_sha"):
      good = _string(value) and bool(_SHA.fullmatch(value))
    else:
      good = _string(value)
    if not good:
      raise HostMutationError("invalid operation result value")
  params = request["parameters"]
  for result_key, param_key in (
    ("number", "number"), ("context", "context"),
    ("candidate_sha", "candidate_sha"), ("source_ref", "source_ref"),
    ("target_ref", "target_ref"), ("head_sha", "expected_source_sha"),
    ("head_sha", "expected_head_sha"), ("conclusion", "conclusion"),
    ("title", "title"), ("state", "state"), ("draft", "draft"),
  ):
    if result_key in result and param_key in params:
      if result[result_key] != params[param_key]:
        raise HostMutationError("provider result contradicts request")
  return reply


def _invoke(command, request, timeout, cwd=None):
  try:
    run = subprocess.run(
      command, input=json.dumps(request, sort_keys=True) + "\n",
      capture_output=True, text=True, timeout=timeout, check=False,
      cwd=cwd,
    )
  except (OSError, subprocess.TimeoutExpired) as error:
    raise HostMutationError(
      "host mutation outcome unavailable", "unknown_outcome",
    ) from error
  if run.returncode:
    if run.stdout.strip():
      raise HostMutationError("provider failure stdout not empty")
    try:
      error = json.loads(run.stderr)
    except (ValueError, TypeError) as cause:
      raise HostMutationError(
        "malformed provider failure", "unknown_outcome",
      ) from cause
    if type(error) is not dict or set(error) != {
      "schema_version", "operation", "repository", "request_id",
      "error", "message",
    } or type(error["schema_version"]) is not int or error["schema_version"] != 1:
      raise HostMutationError("malformed provider failure")
    if any(error[field] != request[field] for field in (
      "operation", "repository", "request_id",
    )) or type(error["error"]) is not str or error["error"] not in _ERRORS or not _string(error["message"]):
      raise HostMutationError("malformed provider failure")
    raise HostMutationError(error["message"], error["error"])
  try:
    reply = json.loads(run.stdout)
  except (TypeError, ValueError) as error:
    raise HostMutationError("invalid successful response") from error
  return _validate_result(reply, request)


def dispatch(command, request, *, timeout=30, cwd=None):
  """Preserve semantic request and fail closed on provider errors."""
  _validate_request(request)
  if type(command) is not list or not command or any(
    not isinstance(arg, str) or not arg for arg in command
  ) or command[0].startswith("-"):
    raise HostMutationError("invalid configured adapter", "invalid_request")
  if request["operation"] != "capabilities":
    capability = dict(request, operation="capabilities", parameters={})
    _validate_request(capability)
    caps = _invoke(command, capability, timeout, cwd=cwd)["result"]["operations"]
    if not caps[request["operation"]]:
      raise HostMutationError("capability unavailable", "unsupported")
  return _invoke(command, request, timeout, cwd=cwd)


def dispatch_configured(root, request, *, timeout=30):
  """Invoke the repository-owned adapter selected by validated config."""
  from .config import ConfigError, load_config

  try:
    config = load_config(root)
  except ConfigError as error:
    raise HostMutationError(
      "repository-host configuration unavailable", "invalid_request",
    ) from error
  command = config.get("hostCommand")
  if command is None:
    raise HostMutationError(
      "repository-host adapter is not configured", "unsupported",
    )
  from .git import GitError, changed_files, repository_state

  try:
    before = repository_state(root)
    changes = changed_files(root)
  except GitError as error:
    raise HostMutationError(
      "cannot establish local repository state", "invalid_request",
    ) from error
  try:
    return dispatch(command, request, timeout=timeout, cwd=root)
  finally:
    try:
      after = repository_state(root)
      after_changes = changed_files(root)
    except GitError as error:
      raise HostMutationError(
        "cannot verify local repository state", "unknown_outcome",
      ) from error
    if before != after or changes != after_changes:
      raise HostMutationError(
        "host adapter changed local repository state", "unknown_outcome",
      )
