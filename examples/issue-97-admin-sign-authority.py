#!/usr/bin/env python3
"""OFFLINE security-admin utility for #97's disposable signed authority.

Run locally, NOT in GitHub Actions or in the untrusted PR checkout.
Do not commit the generated private key. It never prints secret bytes.
Operator approval and a protected key holder remain mandatory.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
  Ed25519PrivateKey,
)

REPOSITORY = "Ma-XX-oN/Disposable-000"
CAPABILITIES = [
  "issue.comment", "issue.update",
  "pull_request.create", "pull_request.update",
]


def canonical(value: dict) -> bytes:
  return json.dumps(
    value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
  ).encode("utf-8")


def utc(value: datetime) -> str:
  return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def secure_create(path: Path, data: bytes) -> None:
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  try:
    with os.fdopen(fd, "wb") as stream:
      stream.write(data)
  except BaseException:
    path.unlink(missing_ok=True)
    raise


def generate_key(path: Path) -> None:
  private = Ed25519PrivateKey.generate()
  secure_create(path, private.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
  ))
  key = private.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
  )
  public_path = path.with_suffix(".public.b64")
  secure_create(public_path, base64.b64encode(key) + b"\n")
  print("Created offline private key at " + str(path))
  print("Created non-secret public trust anchor at " + str(public_path))
  print("Never commit the private key or paste it into chat.")


def sign(payload: dict, private: Ed25519PrivateKey) -> dict:
  return {
    "payload": payload,
    "signature": base64.b64encode(
      private.sign(canonical(payload))
    ).decode("ascii"),
  }


def issue(args) -> None:
  if not re.fullmatch(r"[0-9a-f]{40}", args.candidate_sha) or (
    not re.fullmatch(r"[0-9a-f]{40}", args.source_sha)
  ):
    raise ValueError("full lowercase candidate/source SHAs required")
  if args.issue <= 0 or not args.issuer_id or args.hours <= 0 or (
    args.hours > 24
  ):
    raise ValueError("invalid issuer, issue or short grant lifetime")
  if args.source_ref == args.target_ref or not (
    args.source_ref.startswith("refs/heads/rwf97-sandbox-")
  ) or not args.target_ref.startswith("refs/heads/rwf97-sandbox-"):
    raise ValueError("unsafe sandbox branch scope")
  private = serialization.load_pem_private_key(
    args.private_key.read_bytes(), password=None
  )
  if not isinstance(private, Ed25519PrivateKey):
    raise ValueError("issuer key must be Ed25519")
  now = datetime.now(timezone.utc).replace(microsecond=0)
  expires = now + timedelta(hours=args.hours)
  scope = {
    "repository": REPOSITORY, "issue_numbers": [args.issue],
    "candidate_sha": args.candidate_sha,
    "integration_id": None, "destination_ref": None,
    "expected_destination_sha": None, "release_class": None,
  }
  scope_digest = hashlib.sha256(canonical(scope)).hexdigest()
  grant_id = "rwf97-" + hashlib.sha256(canonical({
    "issuer": args.issuer_id,
    "scope_digest": scope_digest,
    "issued_at": utc(now),
  })).hexdigest()[:32]
  grant = {
    "schema_version": 1, "grant_id": grant_id, "revision": 0,
    "issuer": {
      "authority_id": args.issuer_id,
      "subject_id": args.issuer_id,
      "authentication_ref": "offline-Ed25519-pinned-trust-anchor",
    },
    "subject": {
      "actor_id": "github-actions[bot]",
      "authentication_ref": "authenticated-GitHub-GraphQL-viewer",
    },
    "role": "ci_test_runner", "capabilities": CAPABILITIES,
    "scope": scope,
    "issued_at": utc(now), "not_before": utc(now),
    "expires_at": utc(expires), "status": "active",
    "revoked_at": None, "revocation_ref": None,
    "max_uses": None, "uses": 0,
    "binding": {
      "issuer_signature_ref": "offline-ed25519-" + args.issuer_id,
      "policy_revision": 0, "source_record_sha": scope_digest,
    },
    "provenance": {
      "writer_id": args.issuer_id,
      "session_id": "reviewed-rwf97-sandbox-acceptance",
      "expected_revision": 0,
    },
  }
  payload = {
    "grant": grant,
    "sandbox": {
      "repository": REPOSITORY,
      "candidate_sha": args.candidate_sha,
      "issue": args.issue,
      "source_ref": args.source_ref,
      "target_ref": args.target_ref,
      "source_sha": args.source_sha,
      "authorized_null_dimensions": [
        "destination_ref", "expected_destination_sha",
        "integration_id", "release_class",
      ],
    },
    "delegation": {
      "authority_id": args.issuer_id,
      "repository": REPOSITORY,
      "roles": ["ci_test_runner"],
      "capabilities": CAPABILITIES,
      "expires_at": utc(expires),
    },
  }
  revoked = {
    "schema_version": 1, "issuer": args.issuer_id,
    "revision": 0, "revoked_grants": [],
  }
  args.output.mkdir(parents=True, exist_ok=True)
  for name, signed in (
    ("grant.json", sign(payload, private)),
    ("revocations.json", sign(revoked, private)),
  ):
    secure_create(args.output / name, canonical(signed) + b"\n")
  print("Signed policy created for " + REPOSITORY)
  print("Grant ID: " + grant_id)
  print("Grant expires at " + utc(expires))
  print("Only the two signed JSON files may be committed to sandbox main.")
  print("Private signing key must stay offline.")


def main() -> None:
  parser = argparse.ArgumentParser()
  commands = parser.add_subparsers(dest="command", required=True)
  initialize = commands.add_parser("generate-key")
  initialize.add_argument("--private-key", type=Path, required=True)
  issue_command = commands.add_parser("issue")
  issue_command.add_argument("--private-key", type=Path, required=True)
  issue_command.add_argument("--issuer-id", required=True)
  issue_command.add_argument("--candidate-sha", required=True)
  issue_command.add_argument("--source-sha", required=True)
  issue_command.add_argument("--issue", type=int, default=1)
  issue_command.add_argument("--hours", type=int, default=2)
  issue_command.add_argument("--output", type=Path, required=True)
  issue_command.add_argument(
    "--source-ref", default="refs/heads/rwf97-sandbox-source"
  )
  issue_command.add_argument(
    "--target-ref", default="refs/heads/rwf97-sandbox-target"
  )
  args = parser.parse_args()
  if args.command == "generate-key":
    generate_key(args.private_key)
  else:
    issue(args)


if __name__ == "__main__":
  main()
