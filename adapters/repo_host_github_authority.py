"""Trusted-authorization bridge for the GitHub host mutation adapter.

Deployment must supply an independently secured verifier executable.  No
caller-supplied grant/role, Git author, or GitHub token alone grants authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

from repo_host_github_provider import ProviderError


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
  # A relative executable may resolve to attacker-controlled worktree files.
  if not command[0].startswith("/") or ".." in command[0].split("/"):
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
  try:
    result = subprocess.run(
      command, input=json.dumps(request), capture_output=True, text=True,
      timeout=30, check=False,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    raise ProviderError("unauthorized", "trusted verifier unavailable") from exc
  if result.returncode or not result.stdout:
    raise ProviderError("unauthorized", "trusted verifier denied request")
  try:
    decision = json.loads(result.stdout)
  except ValueError as exc:
    raise ProviderError("unauthorized", "invalid verifier decision") from exc
  if not isinstance(decision, dict) or set(decision) != {
    "schema_version", "operation", "repository", "request_id",
    "scope_digest", "actor_id", "decision", "authority_ref",
    "grant_kind", "max_uses",
  }:
    raise ProviderError("unauthorized", "invalid verifier envelope")
  expected = {
    "schema_version": 1,
    "operation": request["operation"],
    "repository": request["repository"],
    "request_id": request["request_id"],
    "scope_digest": _scope(request),
    "decision": "allow",
    "grant_kind": "standing",
    "max_uses": None,
  }
  if any(type(decision[key]) is not type(value) or decision[key] != value
         for key, value in expected.items()):
    raise ProviderError("unauthorized", "verifier identity or scope mismatch")
  if not all(isinstance(decision[k], str) and decision[k]
             for k in ("actor_id", "authority_ref")):
    raise ProviderError("unauthorized", "missing verified actor or grant")
  # Identity is observed independently from the provider's authenticated
  # principal.  The verifier's actor proof must bind to this identity.
  user = backend.identity()
  if not isinstance(user, dict) or user.get("login") != decision["actor_id"]:
    raise ProviderError("unauthorized", "provider actor identity mismatch")
  return decision
