#!/usr/bin/env python3
"""GitHub repository-host mutation adapter, fail-closed bootstrap.

Operations are deliberately unavailable until provider-enforced authorization,
idempotency and atomic acceptance have been implemented and certified.
"""
from __future__ import annotations

import json
import re
import sys


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


def _parse(raw: str) -> dict:
  try:
    value = json.loads(raw)
  except (json.JSONDecodeError, ValueError) as exc:
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
  return value


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
    result = {
      "schema_version": 1,
      "operation": request["operation"] if request else None,
      "repository": request["repository"] if request else None,
      "request_id": request["request_id"] if request else None,
      "error": exc.category,
      "message": str(exc),
    }
    return 2, "", json.dumps(result, separators=(",", ":")) + "\n"


def main() -> int:
  status, stdout, stderr = run(sys.stdin.read())
  sys.stdout.write(stdout)
  sys.stderr.write(stderr)
  return status


if __name__ == "__main__":
  raise SystemExit(main())
