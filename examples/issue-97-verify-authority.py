#!/usr/bin/env python3
"""Fail-closed #97 test-only #80 standing-grant verifier.

TRUST ROOT: environment-protected RWF97_ISSUER_PUBLIC_KEY and pinned
issuer ID. A signed grant and signed current revocation state are read
from the independently protected sandbox main ref for EVERY decision.
Does not issue grants, accept local claims, or consume one-time grants.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature


OPERATIONS = frozenset((
  "issue.update", "issue.comment",
  "pull_request.create", "pull_request.update",
))


def canonical(value: object) -> bytes:
  return json.dumps(
    value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
  ).encode("utf-8")


def now_utc() -> datetime:
  return datetime.now(timezone.utc)


def instant(value: object) -> datetime:
  if not isinstance(value, str):
    raise ValueError("invalid timestamp")
  try:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
  except ValueError as exc:
    raise ValueError("invalid timestamp") from exc
  return parsed.replace(tzinfo=timezone.utc)


def fetch_json(repository: str, path: str) -> dict:
  response = subprocess.run([
    "gh", "api", "--method", "GET",
    "repos/" + repository + "/contents/" + path + "?ref=main",
  ], capture_output=True, text=True, timeout=30, check=False)
  if response.returncode:
    raise ValueError("authoritative policy unavailable")
  entry = json.loads(response.stdout)
  if not isinstance(entry, dict) or entry.get("encoding") != "base64":
    raise ValueError("invalid authoritative policy source")
  raw = base64.b64decode(entry["content"], validate=False)
  doc = json.loads(raw)
  if not isinstance(doc, dict):
    raise ValueError("invalid signed document")
  return doc


def verify_document(document: dict, pubkey: Ed25519PublicKey) -> dict:
  if set(document) != {"payload", "signature"}:
    raise ValueError("unexpected signed document fields")
  payload = document["payload"]
  if not isinstance(payload, dict):
    raise ValueError("invalid signed payload")
  signature = document["signature"]
  if not isinstance(signature, str):
    raise ValueError("invalid signature")
  try:
    pubkey.verify(
      base64.b64decode(signature, validate=True), canonical(payload)
    )
  except (InvalidSignature, ValueError) as exc:
    raise ValueError("untrusted issuer signature") from exc
  return payload


def principal() -> str:
  # Resolves identity using the very provider token doing the mutation;
  # workflow actor name, Git author and environment claims are ignored.
  result = subprocess.run(
    ["gh", "api", "graphql", "-f", "query={viewer{login}}"],
    capture_output=True, text=True, timeout=30, check=False,
  )
  if result.returncode:
    raise ValueError("provider principal unavailable")
  payload = json.loads(result.stdout)
  login = payload.get("data", {}).get("viewer", {}).get("login")
  if not isinstance(login, str) or not login:
    raise ValueError("provider identity missing")
  return login


GRANT_FIELDS = {
  "schema_version", "grant_id", "revision", "issuer",
  "subject", "role", "capabilities", "scope", "issued_at",
  "not_before", "expires_at", "status", "revoked_at",
  "revocation_ref", "max_uses", "uses", "binding", "provenance",
}
SCOPE_FIELDS = {
  "repository", "issue_numbers", "candidate_sha",
  "integration_id", "destination_ref",
  "expected_destination_sha", "release_class",
}


def evaluate(evaluation: dict, document: dict, revocations: dict,
             repository: str, actor: str, clock: datetime) -> dict:
  if set(evaluation) != {"request", "require_non_consuming_policy"} or (
    evaluation["require_non_consuming_policy"] is not True
  ):
    raise ValueError("unsupported or consuming authorization query")
  request = evaluation["request"]
  if not isinstance(request, dict) or set(request) != {
    "schema_version", "operation", "repository",
    "request_id", "parameters",
  }:
    raise ValueError("invalid exact mutation request")
  if type(request["schema_version"]) is not int or (
    request["schema_version"] != 1
  ):
    raise ValueError("unsupported mutation schema")
  operation = request["operation"]
  if operation not in OPERATIONS or request["repository"] != repository:
    raise ValueError("capability or sandbox repository mismatch")
  if not isinstance(request["request_id"], str) or not (
    request["request_id"]
  ) or not isinstance(request["parameters"], dict):
    raise ValueError("invalid mutation identity")

  # The grant itself exactly follows #80. The signed envelope supplies
  # explicit trusted sandbox constraints, never implicit null wildcards.
  if not isinstance(document, dict) or set(document) != {
    "grant", "sandbox", "delegation",
  }:
    raise ValueError("invalid standing-policy evidence envelope")
  grant = document["grant"]
  sandbox = document["sandbox"]
  delegation = document["delegation"]
  if not isinstance(grant, dict) or set(grant) != GRANT_FIELDS or (
    grant["schema_version"] != 1
  ):
    raise ValueError("noncanonical #80 grant")
  if not isinstance(sandbox, dict) or not isinstance(delegation, dict):
    raise ValueError("invalid signed authority facts")
  if grant["max_uses"] is not None or type(grant["uses"]) is not int or (
    grant["uses"] != 0
  ):
    raise ValueError("one-time grant is unsupported")
  if grant["status"] != "active" or (
    grant["revoked_at"] is not None
  ) or grant["revocation_ref"] is not None:
    raise ValueError("inactive standing grant")
  if grant["role"] != "ci_test_runner":
    raise ValueError("unauthorized role")
  if not isinstance(grant["subject"], dict) or set(
    grant["subject"]
  ) != {"actor_id", "authentication_ref"} or (
    grant["subject"]["actor_id"] != actor
  ) or not grant["subject"]["authentication_ref"]:
    raise ValueError("provider actor proof mismatch")
  issuer = grant["issuer"]
  issuer_id = os.environ.get("RWF97_ISSUER_AUTHORITY")
  if not isinstance(issuer, dict) or set(issuer) != {
    "authority_id", "subject_id", "authentication_ref",
  } or not issuer_id or issuer["authority_id"] != issuer_id or not (
    issuer["authentication_ref"]
  ):
    raise ValueError("untrusted grant issuer")
  if delegation.get("authority_id") != issuer_id or (
    delegation.get("repository") != repository
  ) or "ci_test_runner" not in delegation.get("roles", []) or (
    operation not in delegation.get("capabilities", [])
  ) or clock >= instant(delegation.get("expires_at")):
    raise ValueError("insufficient authenticated issuer delegation")
  capabilities = grant["capabilities"]
  if not isinstance(capabilities, list) or not capabilities or (
    capabilities != sorted(set(capabilities))
  ) or operation not in capabilities or not set(capabilities) <= OPERATIONS:
    raise ValueError("invalid/unauthorized capability")
  scope = grant["scope"]
  if not isinstance(scope, dict) or set(scope) != SCOPE_FIELDS or (
    scope["repository"] != repository
  ) or scope["candidate_sha"] != os.environ.get(
    "RWF97_APPROVED_SHA"
  ) or not re.fullmatch(
    r"[0-9a-f]{40}", str(scope["candidate_sha"])
  ):
    raise ValueError("candidate or repository scope mismatch")
  if scope["release_class"] is not None or (
    scope["integration_id"] is not None
  ) or scope["destination_ref"] is not None or (
    scope["expected_destination_sha"] is not None
  ):
    raise ValueError("unsupported scope extension")
  if sandbox.get("repository") != repository or sandbox.get(
    "candidate_sha"
  ) != scope["candidate_sha"]:
    raise ValueError("signed sandbox scope mismatch")
  number = sandbox.get("issue")
  if type(number) is not int or number <= 0 or (
    scope["issue_numbers"] != [number]
  ):
    raise ValueError("sandbox issue scope mismatch")
  if operation.startswith("issue.") and (
    request["parameters"].get("number") != number
  ):
    raise ValueError("issue scope mismatch")
  if operation == "pull_request.create" and (
    request["parameters"].get("source_ref") != sandbox.get("source_ref")
    or request["parameters"].get("target_ref") != sandbox.get("target_ref")
    or request["parameters"].get("expected_source_sha")
      != sandbox.get("source_sha")
  ):
    raise ValueError("PR branch or candidate scope mismatch")
  if operation == "pull_request.update" and (
    type(request["parameters"].get("number")) is not int
    or request["parameters"]["number"] <= 0
  ):
    raise ValueError("invalid PR identity")
  if not (instant(grant["not_before"]) <= clock
          < instant(grant["expires_at"])):
    raise ValueError("grant not yet valid or expired")
  if now := instant(grant["issued_at"]):
    if now > clock:
      raise ValueError("grant issued in future")
  if revocations.get("issuer") != issuer_id or (
    revocations.get("schema_version") != 1
  ):
    raise ValueError("untrusted revocation authority")
  revision = revocations.get("revision")
  if type(revision) is not int or revision < 0:
    raise ValueError("invalid policy revision")
  binding = grant["binding"]
  if not isinstance(binding, dict) or (
    binding.get("policy_revision") != revision
  ) or not binding.get("issuer_signature_ref") or not (
    binding.get("source_record_sha")
  ):
    raise ValueError("stale or unbound standing policy")
  revoked = revocations.get("revoked_grants")
  if not isinstance(revoked, list) or not all(
    isinstance(item, str) for item in revoked
  ):
    raise ValueError("invalid revocation facts")
  if grant["grant_id"] in revoked:
    raise ValueError("revoked grant")
  if not isinstance(grant["grant_id"], str) or not (
    grant["grant_id"]
  ) or type(grant["revision"]) is not int or grant["revision"] < 0:
    raise ValueError("invalid grant identity or revision")
  request_digest = hashlib.sha256(canonical(request)).hexdigest()
  return {
    "schema_version": 1,
    "request_id": request["request_id"],
    "grant_id": grant["grant_id"],
    "grant_revision": grant["revision"],
    "actor_id": actor,
    "capability": operation,
    "scope_digest": request_digest,
    "policy_revision": str(revision),
    "evaluated_at": clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "decision": "allow",
    "reason": "signed standing policy and fresh revocation verified",
  }


def main() -> int:
  try:
    evaluation = json.load(sys.stdin)
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo.lower() != "ma-xx-on/disposable-000":
      raise ValueError("unexpected sandbox authority domain")
    key_data = os.environ["RWF97_ISSUER_PUBLIC_KEY"]
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", key_data):
      raise ValueError("invalid issuer trust anchor")
    pubkey = Ed25519PublicKey.from_public_bytes(
      base64.b64decode(key_data, validate=True)
    )
    grant = verify_document(fetch_json(
      repo, "trusted/rwf97/grant.json"
    ), pubkey)
    revocations = verify_document(fetch_json(
      repo, "trusted/rwf97/revocations.json"
    ), pubkey)
    result = evaluate(
      evaluation, grant, revocations, repo, principal(), now_utc()
    )
    print(json.dumps(result, sort_keys=True))
    return 0
  except (KeyError, TypeError, ValueError, OSError,
          subprocess.TimeoutExpired) as exc:
    # Never log tokens, signatures, grant contents or user secrets.
    print("trusted #80 authority denied: " + type(exc).__name__,
          file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
