"""Portable repository-host mutation dispatcher.  Provider syntax is opaque."""
from __future__ import annotations

import json
import re
import subprocess


class HostMutationError(RuntimeError):
  pass


_OPERATIONS = {
  "capabilities", "issue.update", "issue.comment",
  "pull_request.create", "pull_request.update",
  "pull_request.merge", "check.publish",
}
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def _validate_request(request: dict) -> None:
  if not isinstance(request, dict) or set(request) != {
    "schema_version", "operation", "repository", "request_id",
    "parameters",
  }:
    raise HostMutationError("invalid host mutation request")
  if (
    request["schema_version"] != 1
    or type(request["schema_version"]) is not int
  ):
    raise HostMutationError("unsupported host mutation schema")
  if (
    not isinstance(request["operation"], str)
    or request["operation"] not in _OPERATIONS
  ):
    raise HostMutationError("unsupported host mutation operation")
  if not isinstance(request["repository"], str) or not _REPOSITORY.fullmatch(
    request["repository"]
  ):
    raise HostMutationError("invalid host repository identity")
  if (not isinstance(request["request_id"], str) or not re.fullmatch(
    r"[A-Za-z0-9._:-]{1,128}", request["request_id"]
  )):
    raise HostMutationError("invalid idempotency identity")
  if not isinstance(request["parameters"], dict):
    raise HostMutationError("invalid semantic mutation parameters")


def dispatch(
  command: list[str], request: dict, *, timeout: float = 30,
) -> dict:
  """Forward unchanged semantic JSON, normalize failures without retrying."""
  _validate_request(request)
  if (
    not isinstance(command, list) or not command
    or any(not isinstance(arg, str) or not arg for arg in command)
    or command[0].startswith("-")
  ):
    raise HostMutationError("invalid configured host adapter command")
  try:
    result = subprocess.run(
      command,
      input=json.dumps(request, separators=(",", ":"), sort_keys=True) + "\n",
      capture_output=True, text=True, timeout=timeout, check=False,
    )
  except (OSError, subprocess.TimeoutExpired) as error:
    raise HostMutationError("host mutation outcome unavailable") from error
  if result.returncode:
    raise HostMutationError("host mutation failed or outcome unknown")
  try:
    reply = json.loads(result.stdout)
  except (ValueError, TypeError) as error:
    raise HostMutationError("invalid successful host response") from error
  if (
    not isinstance(reply, dict)
    or set(reply) != {
      "schema_version", "operation", "repository", "request_id",
      "status", "result",
    }
    or type(reply.get("schema_version")) is not int
    or reply["schema_version"] != 1
    or reply.get("operation") != request["operation"]
    or reply.get("repository") != request["repository"]
    or reply.get("request_id") != request["request_id"]
    or not isinstance(reply.get("status"), str)
    or reply["status"] not in {"applied", "unchanged"}
    or not isinstance(reply.get("result"), dict)
  ):
    raise HostMutationError("invalid successful host response")
  return reply
