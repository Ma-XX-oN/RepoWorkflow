"""#638 specification-based publication authorization boundary matrix.

The grant verifier below is deliberately independent of the publisher.
It models the already-frozen #80 decision semantics; it is not a production
issuer, token authenticator, or authorization service.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from repo_workflow.remote_stable_publisher import (
  PublicationRequest, PublicationRefused, publish_stable_tag,
)

SHA = "a" * 40
BASE = "b" * 40
NOW = datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)


class SimulatedRemote:
  def __init__(self):
    self.tags = {}
    self.creations = 0

  def authenticated_finalizer(self):
    return True

  def main_tip(self, repository):
    return SHA

  def accepted_base(self, repository, sha):
    return BASE

  def read_tag(self, repository, ref):
    return self.tags.get(ref)

  def create_tag_if_absent(self, repository, ref, sha):
    self.creations += 1
    if ref in self.tags:
      raise RuntimeError("immutable tag exists")
    self.tags[ref] = sha


class SpecGrantVerifier:
  def __init__(self, request):
    self.repository = request.repository
    self.actor_authenticated = True
    self.issuer_authenticated = True
    self.signature_verified = True
    self.role = "remote_finalizer"
    self.destination = "refs/tags/v" + request.version
    self.candidate = request.landed_sha
    self.release_class = request.release_class
    self.not_before = NOW - timedelta(hours=1)
    self.expires_at = NOW + timedelta(hours=1)
    self.status = "active"
    self.remaining = 1
    self.consumed = {}
    self.certification = "PASS"

  def authorize(self, request, ref):
    return all((
      self.actor_authenticated,
      self.issuer_authenticated,
      self.signature_verified,
      self.role == "remote_finalizer",
      self.status == "active",
      self.not_before <= NOW < self.expires_at,
      self.repository == request.repository,
      self.destination == ref,
      self.candidate == request.landed_sha,
      self.release_class == request.release_class,
      self.remaining > 0 or request.request_id in self.consumed,
      request.authorization_ref != "",
    ))

  def certified(self, request, ref):
    return self.certification

  def version_matches(self, request):
    return request.version == "0.0.638"

  def finalize_consumption(self, request, ref, sha):
    record = (request, ref, sha)
    if request.request_id in self.consumed:
      return self.consumed[request.request_id] == record
    if self.remaining <= 0:
      return False
    self.remaining -= 1
    self.consumed[request.request_id] = record
    return True


class AuthorizationBoundaryTests(unittest.TestCase):
  def setUp(self):
    self.request = PublicationRequest(
      "owner/repo", "0.0.638", SHA, SHA, BASE,
      "req-1", "verified-grant", "verified-protection",
      "verified-certification", "patch",
    )
    self.remote = SimulatedRemote()
    self.grant = SpecGrantVerifier(self.request)

  def publish(self, request=None):
    return publish_stable_tag(
      request or self.request, self.remote, self.grant
    )

  def test_valid_exact_scope_consumes_once(self):
    self.assertEqual(self.publish(), "refs/tags/v0.0.638")
    self.assertEqual(self.publish(), "refs/tags/v0.0.638")
    self.assertEqual(self.remote.creations, 1)
    self.assertEqual(self.grant.remaining, 0)
    self.assertEqual(len(self.grant.consumed), 1)

  def test_independent_denial_dimensions(self):
    cases = (
      ("actor_authenticated", False),
      ("issuer_authenticated", False),
      ("signature_verified", False),
      ("role", "security_administrator"),
      ("role", "ci_test_runner"),
      ("role", "developer"),
      ("repository", "other/repo"),
      ("destination", "refs/tags/v0.0.639"),
      ("candidate", BASE),
      ("release_class", "major"),
      ("not_before", NOW + timedelta(seconds=1)),
      ("expires_at", NOW),
      ("status", "revoked"),
      ("remaining", 0),
    )
    for field, value in cases:
      with self.subTest(field=field, value=value):
        self.setUp()
        setattr(self.grant, field, value)
        with self.assertRaises(PublicationRefused):
          self.publish()
        self.assertEqual(self.remote.tags, {})
        self.assertEqual(self.remote.creations, 0)

  def test_changed_request_cannot_reuse_consumed_grant(self):
    self.publish()
    changed = replace(self.request, release_class="minor")
    with self.assertRaises(PublicationRefused):
      self.publish(changed)
    self.assertEqual(self.remote.creations, 1)
    self.assertEqual(self.remote.tags["refs/tags/v0.0.638"], SHA)

  def test_revocation_after_creation_blocks_replay(self):
    self.publish()
    self.grant.status = "revoked"
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertEqual(self.remote.creations, 1)

  def test_expired_grant_after_creation_blocks_replay(self):
    self.publish()
    self.grant.expires_at = NOW
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertEqual(self.remote.creations, 1)

  def test_authorization_refs_never_substitute_verified_grant(self):
    self.grant.issuer_authenticated = False
    self.assertNotEqual(self.request.authorization_ref, "")
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertEqual(self.remote.creations, 0)


if __name__ == "__main__":
  unittest.main()
