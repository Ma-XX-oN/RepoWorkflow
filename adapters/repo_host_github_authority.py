"""Trusted #80 authorization decision consumer for GitHub host mutation.

The configured verifier is an independently protected deployment component.
It must resolve issuer, actor, grant scope, expiry and revocation against the
authoritative #80 state, and return exactly the #80 decision envelope.
Only non-consuming standing-policy decisions are requested by this adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
import subprocess

from repo_host_github_provider import ProviderError


FIELDS = {
  "schema_version", "request_id", "grant_id", "grant_revision",
  "actor_id", "capability", "scope_digest", "policy_revision",
  "evaluated_at", "decision", "reason",
}


def verifier_command() -> list[str] | None:
  raw = os.environ.get("RWF_REPO_HOST_AUTH_COMMAND")
  if not raw:
    return None
  try:
    command = json.loads(raw)
  except ValueError:
    return None
  if not isinstance(command, list) or not command or not all(
    isinstance(part, str) and part for part in command
  ):
    return None
  executable = command[0]
  if not (os.path.isabs(executable) or ntpath.isabs(executable)):
    return None
  if ".." in executable.replace("\\", "/").split("/"):
    return None
  return command


def _scope(request: dict) -> str:
  return hashlib.sha256(
    json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
  ).hexdigest()


def authorize(request: dict, backend) -> dict:
  command = verifier_command()
  if command is None:
    raise ProviderError("unauthorized", "trusted verifier not configured")
  evaluation = {
    "request": request,
    "require_non_consuming_policy": True,
  }
  try:
    result = subprocess.run(
      command, input=json.dumps(evaluation),
      capture_output=True, text=True, timeout=30, check=False,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    raise ProviderError("unauthorized", "trusted verifier unavailable") from exc
  if result.returncode or not result.stdout:
    raise ProviderError("unauthorized", "trusted verifier denied request")
  try:
    decision = json.loads(result.stdout)
  except ValueError as exc:
    raise ProviderError("unauthorized", "invalid verifier decision") from exc
  if not isinstance(decision, dict) or set(decision) != FIELDS:
    raise ProviderError("unauthorized", "invalid #80 decision envelope")
  expected = {
    "schema_version": 1,
    "request_id": request["request_id"],
    "capability": request["operation"],
    "scope_digest": _scope(request),
    "decision": "allow",
  }
  if any(type(decision[key]) is not type(value) or decision[key] != value
         for key, value in expected.items()):
    raise ProviderError("unauthorized", "decision identity or scope mismatch")
  for key in ("grant_id", "actor_id", "policy_revision", "reason"):
    if not isinstance(decision[key], str) or not decision[key]:
      raise ProviderError("unauthorized", "invalid decision proof: " + key)
  revision = decision["grant_revision"]
  if type(revision) is not int or revision < 0:
    raise ProviderError("unauthorized", "invalid grant revision")
  stamp = decision["evaluated_at"]
  if not isinstance(stamp, str):
    raise ProviderError("unauthorized", "missing decision evaluation time")
  try:
    evaluated = datetime.strptime(
      stamp, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
  except ValueError as exc:
    raise ProviderError("unauthorized", "invalid evaluation time") from exc
  delta = (datetime.now(timezone.utc) - evaluated).total_seconds()
  if delta < 0 or delta > 60:
    raise ProviderError("unauthorized", "authorization decision is stale")
  user = backend.identity()
  if not isinstance(user, dict) or user.get("login") != decision["actor_id"]:
    raise ProviderError("unauthorized", "provider actor identity mismatch")
  return decision
