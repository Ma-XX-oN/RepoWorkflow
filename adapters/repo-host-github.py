#!/usr/bin/env python3
"""GitHub repository-host mutation adapter, fail-closed bootstrap.

Operations are deliberately unavailable until provider-enforced authorization,
idempotency and atomic acceptance have been implemented and certified.
"""
from __future__ import annotations

import json
import re
import sys


MAX_REQUEST_CHARS = 1048576

OPERATIONS = (
  "issue.update",
  "issue.comment",
  "pull_request.create",
  "pull_request.update",
  "pull_request.merge",
  "check.publish",
)
REQUEST_FIELDS = {
  "schema_version", "operation", "repository", "request_id", "parameters",
}
REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class ProtocolError(Exception):
  def __init__(self, category: str, message: str):
    super().__init__(message)
    self.category = category



SHA = re.compile(r"[0-9a-f]{40}\Z")
PARAMETERS = {
  "issue.update": (
    {"number"}, {"title", "state"},
  ),
  "issue.comment": (
    {"number", "body"}, set(),
  ),
  "pull_request.create": (
    {"source_ref", "target_ref", "expected_source_sha",
     "title", "body", "draft"}, set(),
  ),
  "pull_request.update": (
    {"number", "expected_head_sha"},
    {"title", "body", "draft", "state", "target_ref"},
  ),
  "pull_request.merge": (
    {"number", "tested_head_sha", "expected_destination_sha",
     "eligibility_ref", "authorization_ref"}, set(),
  ),
  "check.publish": (
    {"candidate_sha", "context", "verification_ref", "conclusion"}, set(),
  ),
}



def _branch_ref(value: object) -> bool:
  if not isinstance(value, str) or not value.startswith("refs/heads/"):
    return False
  name = value[len("refs/heads/"):]
  return (
    bool(name)
    and bool(re.fullmatch(r"[A-Za-z0-9._/-]+", name))
    and not name.startswith("/")
    and not name.endswith("/")
    and "//" not in name
    and ".." not in name
    and not name.endswith(".lock")
  )


def _valid_parameters(operation: str, params: dict) -> None:
  if operation == "capabilities":
    return
  required, optional = PARAMETERS[operation]
  fields = set(params)
  if not required <= fields or fields - required - optional:
    raise ProtocolError("invalid_request", "invalid operation parameters")
  if operation in {"issue.update", "pull_request.update"}:
    if not fields.intersection(optional):
      raise ProtocolError("invalid_request", "missing requested change")
  for key, value in params.items():
    if key == "number":
      valid = type(value) is int and value > 0
    elif key in {
      "expected_source_sha", "expected_head_sha", "tested_head_sha",
      "expected_destination_sha", "candidate_sha",
    }:
      valid = isinstance(value, str) and bool(SHA.fullmatch(value))
    elif key in {"source_ref", "target_ref"}:
      valid = _branch_ref(value)
    elif key == "draft":
      valid = type(value) is bool
    elif key == "state":
      valid = isinstance(value, str) and value in (
        {"open", "closed"} if operation == "issue.update" else {"open"}
      )
    elif key == "conclusion":
      valid = isinstance(value, str) and value in {"success", "failure"}
    elif key == "body":
      valid = isinstance(value, str) and (
        bool(value) if operation == "issue.comment" else True
      )
    else:
      valid = isinstance(value, str) and bool(value)
    if not valid:
      raise ProtocolError("invalid_request", f"invalid parameter: {key}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
  result = {}
  for name, value in pairs:
    if name in result:
      raise ProtocolError("invalid_request", "duplicate JSON object key")
    result[name] = value
  return result


def _parse(raw: str) -> dict:
  if len(raw) > MAX_REQUEST_CHARS:
    raise ProtocolError("invalid_request", "request exceeds size limit")
  try:
    value = json.loads(raw, object_pairs_hook=_unique_object)
  except (json.JSONDecodeError, ValueError, RecursionError) as exc:
    raise ProtocolError("invalid_request", "invalid JSON request") from exc
  if not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
    raise ProtocolError("invalid_request", "invalid request envelope")
  if type(value["schema_version"]) is not int or value["schema_version"] != 1:
    raise ProtocolError("invalid_request", "unsupported request schema")
  if value["operation"] not in (*OPERATIONS, "capabilities"):
    raise ProtocolError("unsupported", "unsupported operation")
  if not isinstance(value["repository"], str) or not REPOSITORY.fullmatch(
    value["repository"]
  ):
    raise ProtocolError("invalid_request", "invalid repository identity")
  if not isinstance(value["request_id"], str) or not REQUEST_ID.fullmatch(
    value["request_id"]
  ):
    raise ProtocolError("invalid_request", "invalid request identity")
  if not isinstance(value["parameters"], dict):
    raise ProtocolError("invalid_request", "invalid parameters object")
  if value["operation"] == "capabilities" and value["parameters"]:
    raise ProtocolError("invalid_request", "capabilities takes no parameters")
  _valid_parameters(value["operation"], value["parameters"])
  if any(part in {".", ".."} for part in value["repository"].split("/")):
    raise ProtocolError("invalid_request", "invalid repository component")
  return value



def _recovered_identities(raw: str) -> dict:
  try:
    value = json.loads(raw, object_pairs_hook=_unique_object)
  except (json.JSONDecodeError, ValueError, RecursionError, ProtocolError):
    value = {}
  if not isinstance(value, dict):
    value = {}
  operation = value.get("operation")
  repository = value.get("repository")
  request_id = value.get("request_id")
  return {
    "operation": operation if isinstance(operation, str) else None,
    "repository": repository if isinstance(repository, str) and (
      bool(REPOSITORY.fullmatch(repository))
    ) else None,
    "request_id": request_id if isinstance(request_id, str) and (
      bool(REQUEST_ID.fullmatch(request_id))
    ) else None,
  }


def run(raw: str) -> tuple[int, str, str]:
  request = None
  try:
    request = _parse(raw)
    operation = request["operation"]
    if operation != "capabilities":
      raise ProtocolError(
        "unsupported",
        "mutation disabled pending independent authorization and "
        "provider-backed idempotency enforcement",
      )
    result = {
      "schema_version": 1,
      "operation": operation,
      "repository": request["repository"],
      "request_id": request["request_id"],
      "status": "unchanged",
      "result": {"operations": {name: False for name in OPERATIONS}},
    }
    return 0, json.dumps(result, separators=(",", ":")) + "\n", ""
  except ProtocolError as exc:
    identity = request if request is not None else _recovered_identities(raw)
    result = {
      "schema_version": 1,
      "operation": identity["operation"],
      "repository": identity["repository"],
      "request_id": identity["request_id"],
      "error": exc.category,
      "message": str(exc),
    }
    return 2, "", json.dumps(result, separators=(",", ":")) + "\n"


def main() -> int:
  status, stdout, stderr = run(sys.stdin.read(MAX_REQUEST_CHARS + 1))
  sys.stdout.write(stdout)
  sys.stderr.write(stderr)
  return status


if __name__ == "__main__":
  raise SystemExit(main())
