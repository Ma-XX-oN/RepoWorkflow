"""Specification tests for independently signed #80 sandbox authority."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
  Ed25519PrivateKey,
)
from cryptography.hazmat.primitives import serialization


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/issue-97-verify-authority.py"
spec = importlib.util.spec_from_file_location("issue97_signed_authority",
                                              SOURCE)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
REPOSITORY = "Ma-XX-oN/Disposable-000"
CANDIDATE = "a" * 40
SOURCE_SHA = "b" * 40
NOW = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)


def evidence():
  policy = {
    "schema_version": 1, "grant_id": "issuer-test-01",
    "revision": 0,
    "issuer": {
      "authority_id": "owner-approved-issuer",
      "subject_id": "security-administrator",
      "authentication_ref": "trusted-admin-provider",
    },
    "subject": {
      "actor_id": "github-actions[bot]",
      "authentication_ref": "live-provider-token",
    },
    "role": "ci_test_runner",
    "capabilities": [
      "issue.comment", "issue.update",
      "pull_request.create", "pull_request.update",
    ],
    "scope": {
      "repository": REPOSITORY, "issue_numbers": [1],
      "candidate_sha": CANDIDATE, "integration_id": None,
      "destination_ref": None, "expected_destination_sha": None,
      "release_class": None,
    },
    "issued_at": "2026-10-10T21:00:00Z",
    "not_before": "2026-10-10T21:00:00Z",
    "expires_at": "2026-10-11T21:00:00Z",
    "status": "active", "revoked_at": None, "revocation_ref": None,
    "max_uses": None, "uses": 0,
    "binding": {
      "issuer_signature_ref": "signed-test-fixture",
      "policy_revision": 0, "source_record_sha": "c" * 64,
    },
    "provenance": {
      "writer_id": "admin", "session_id": "fixture",
      "expected_revision": 0,
    },
  }
  signed = {
    "grant": policy,
    "sandbox": {
      "repository": REPOSITORY, "candidate_sha": CANDIDATE,
      "issue": 1,
      "source_ref": "refs/heads/rwf97-sandbox-source",
      "target_ref": "refs/heads/rwf97-sandbox-target",
      "source_sha": SOURCE_SHA,
      "authorized_null_dimensions": [
        "destination_ref", "expected_destination_sha",
        "integration_id", "release_class",
      ],
    },
    "delegation": {
      "authority_id": "owner-approved-issuer",
      "repository": REPOSITORY,
      "roles": ["ci_test_runner"],
      "capabilities": policy["capabilities"],
      "expires_at": "2026-10-11T21:00:00Z",
    },
  }
  revocations = {
    "schema_version": 1,
    "issuer": "owner-approved-issuer",
    "revision": 0,
    "revoked_grants": [],
  }
  request = {
    "schema_version": 1, "operation": "issue.comment",
    "repository": REPOSITORY, "request_id": "private-sandbox-001",
    "parameters": {"number": 1, "body": "sandbox evidence"},
  }
  return signed, revocations, {
    "request": request, "require_non_consuming_policy": True,
  }


class SignedPolicyTests(TestCase):
  def test_offline_issuer_generates_real_signed_policy(self):
    from argparse import Namespace
    import tempfile

    signer_path = ROOT / "examples/issue-97-admin-sign-authority.py"
    signer_spec = importlib.util.spec_from_file_location(
      "issue97_offline_issuer", signer_path
    )
    signer = importlib.util.module_from_spec(signer_spec)
    signer_spec.loader.exec_module(signer)
    with tempfile.TemporaryDirectory() as temp:
      home = Path(temp)
      key_path = home / "issuer.pem"
      signer.generate_key(key_path)
      self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
      output = home / "signed"
      signer.issue(Namespace(
        private_key=key_path, issuer_id="owner-approved-issuer",
        candidate_sha=CANDIDATE, source_sha=SOURCE_SHA, issue=1,
        hours=2, output=output,
        source_ref="refs/heads/rwf97-sandbox-source",
        target_ref="refs/heads/rwf97-sandbox-target",
      ))
      key = Ed25519PrivateKey.from_private_bytes(
        serialization.load_pem_private_key(
          key_path.read_bytes(), password=None
        ).private_bytes(
          encoding=serialization.Encoding.Raw,
          format=serialization.PrivateFormat.Raw,
          encryption_algorithm=serialization.NoEncryption(),
        )
      ).public_key()
      document = verifier.verify_document(
        json.loads((output / "grant.json").read_text()), key
      )
      revocations = verifier.verify_document(
        json.loads((output / "revocations.json").read_text()), key
      )
      self.assertEqual(
        set(document["grant"]), verifier.GRANT_FIELDS
      )
      with patch.dict(os.environ, {
        "RWF97_ISSUER_AUTHORITY": "owner-approved-issuer",
        "RWF97_APPROVED_SHA": CANDIDATE,
        "RWF97_APPROVED_GRANT_ID": document["grant"]["grant_id"],
      }):
        decision = verifier.evaluate(
          evidence()[2], document, revocations, REPOSITORY,
          "github-actions[bot]", datetime.now(timezone.utc),
        )
      self.assertEqual(decision["decision"], "allow")
      revocation_path = home / "revoked.json"
      signer.revoke(Namespace(
        private_key=key_path, issuer_id="owner-approved-issuer",
        grant_id=document["grant"]["grant_id"],
        revision=1, output=revocation_path,
      ))
      revoked = verifier.verify_document(
        json.loads(revocation_path.read_text()), key
      )
      with patch.dict(os.environ, {
        "RWF97_ISSUER_AUTHORITY": "owner-approved-issuer",
        "RWF97_APPROVED_SHA": CANDIDATE,
        "RWF97_APPROVED_GRANT_ID": document["grant"]["grant_id"],
      }):
        with self.assertRaisesRegex(ValueError, "revoked grant"):
          verifier.evaluate(
            evidence()[2], document, revoked, REPOSITORY,
            "github-actions[bot]", datetime.now(timezone.utc),
          )
      with self.assertRaises(FileExistsError):
        signer.issue(Namespace(
          private_key=key_path, issuer_id="owner-approved-issuer",
          candidate_sha=CANDIDATE, source_sha=SOURCE_SHA, issue=1,
          hours=2, output=output,
          source_ref="refs/heads/rwf97-sandbox-source",
          target_ref="refs/heads/rwf97-sandbox-target",
        ))

  def test_signed_grant_and_revocations_cryptographically_verified(self):
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    signed, revocations, evaluation = evidence()
    for payload in (signed, revocations):
      envelope = {
        "payload": payload,
        "signature": base64.b64encode(
          private.sign(verifier.canonical(payload))
        ).decode("ascii"),
      }
      self.assertEqual(verifier.verify_document(envelope, public),
                       payload)
      bad = {**envelope, "payload": {**payload, "tampered": True}}
      with self.assertRaises(ValueError):
        verifier.verify_document(bad, public)
    other = Ed25519PrivateKey.generate().public_key()
    with self.assertRaises(ValueError):
      verifier.verify_document(envelope, other)

  def test_standing_policy_positive_and_negative_matrix(self):
    signed, revocations, evaluation = evidence()
    variables = {
      "RWF97_ISSUER_AUTHORITY": "owner-approved-issuer",
      "RWF97_APPROVED_SHA": CANDIDATE,
      "RWF97_APPROVED_GRANT_ID": "issuer-test-01",
    }

    def check(payload=signed, state=revocations, query=evaluation,
              actor="github-actions[bot]", clock=NOW):
      with patch.dict(os.environ, variables):
        return verifier.evaluate(query, payload, state, REPOSITORY,
                                 actor, clock)

    response = check()
    self.assertEqual(response["decision"], "allow")
    self.assertEqual(response["capability"], "issue.comment")
    self.assertEqual(response["actor_id"], "github-actions[bot]")
    self.assertEqual(response["request_id"], "private-sandbox-001")
    self.assertEqual(
      response["scope_digest"],
      __import__("hashlib").sha256(verifier.canonical(
        evaluation["request"]
      )).hexdigest(),
    )
    for name, change in [
      ("revoked", lambda g, r, e: r["revoked_grants"].append(
        g["grant"]["grant_id"]
      )),
      ("expired", lambda g, r, e: g["grant"].update({
        "expires_at": "2026-10-10T21:59:00Z",
      })),
      ("one use", lambda g, r, e: g["grant"].update({
        "max_uses": 1,
      })),
      ("wrong issue", lambda g, r, e: e["request"][
        "parameters"
      ].update({"number": 2})),
      ("changed sha", lambda g, r, e: g["grant"]["scope"].update({
        "candidate_sha": "0" * 40,
      })),
      ("wrong issuer", lambda g, r, e: g["grant"]["issuer"].update({
        "authority_id": "rogue",
      })),
      ("stale revision", lambda g, r, e: r.update({
        "revision": 1,
      })),
      ("widen null scope", lambda g, r, e: g["sandbox"].update({
        "authorized_null_dimensions": [],
      })),
      ("unknown field", lambda g, r, e: g["grant"].update({
        "allow_all": True,
      })),
      ("bad delegation", lambda g, r, e: g["delegation"].update({
        "roles": ["remote_finalizer"],
      })),
      ("missing actor proof", lambda g, r, e: g["grant"][
        "subject"
      ].update({"authentication_ref": ""})),
      ("incorrect capability", lambda g, r, e: e["request"].update({
        "operation": "pull_request.merge",
      })),
      ("boolean uses", lambda g, r, e: g["grant"].update({
        "uses": False,
      })),
    ]:
      with self.subTest(case=name):
        g, r, e = evidence()
        change(g, r, e)
        with self.assertRaises(ValueError):
          check(g, r, e)
    with self.assertRaises(ValueError):
      check(actor="some-other-user")
    with self.assertRaises(ValueError):
      check(clock=datetime(2026, 10, 10, 20, 0,
                           tzinfo=timezone.utc))

  def test_pr_update_requires_real_exact_open_draft_sandbox_pr(self):
    from types import SimpleNamespace

    good = {
      "state": "open", "draft": True,
      "head": {
        "sha": SOURCE_SHA, "ref": "rwf97-sandbox-source",
      },
      "base": {"ref": "rwf97-sandbox-target"},
    }
    sandbox = evidence()[0]["sandbox"]

    def verify(payload):
      response = SimpleNamespace(
        returncode=0, stdout=json.dumps(payload), stderr="",
      )
      with patch.object(verifier.subprocess, "run",
                        return_value=response) as backend:
        verifier.require_provider_pr_scope(
          REPOSITORY, 2, sandbox, SOURCE_SHA
        )
      self.assertIn("/pulls/2", backend.call_args.args[0][-1])

    verify(good)
    for bad in (
      {**good, "state": "closed"},
      {**good, "draft": False},
      {**good, "head": {**good["head"], "sha": "0" * 40}},
      {**good, "head": {**good["head"], "ref": "main"}},
      {**good, "base": {"ref": "main"}},
    ):
      with self.subTest(bad=bad):
        with self.assertRaises(ValueError):
          verify(bad)

  def test_authorization_requires_current_authenticated_provider_reads(self):
    source = SOURCE.read_text(encoding="utf-8")
    self.assertIn('"gh", "api", "--method", "GET"', source)
    self.assertIn('"?ref=main"', source)
    self.assertIn('"gh", "api", "graphql"', source)
    self.assertIn("revocations.json", source)
    self.assertIn('Ed25519PublicKey.from_public_bytes', source)
    self.assertNotIn('decision": "allow-all"', source)
