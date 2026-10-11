import unittest
from dataclasses import replace

from repo_workflow.remote_stable_publisher import (
  PublicationIncomplete, PublicationRefused, PublicationRequest,
  publish_stable_tag,
)

SHA = "a" * 40
BASE = "b" * 40


class Provider:
  def __init__(self):
    self.tip = SHA
    self.base = BASE
    self.tags = {}
    self.identity = True
    self.fail_after_create = False
    self.creates = 0

  def authenticated_finalizer(self):
    return self.identity

  def main_tip(self, repository):
    return self.tip

  def accepted_base(self, repository, sha):
    return self.base

  def read_tag(self, repository, ref):
    return self.tags.get(ref)

  def create_tag_if_absent(self, repository, ref, sha):
    self.creates += 1
    if ref in self.tags:
      raise RuntimeError("already exists")
    self.tags[ref] = sha
    if self.fail_after_create:
      raise TimeoutError("response lost")


class Authority:
  def __init__(self):
    self.allowed = True
    self.accepted = "PASS"
    self.version_accepted = True
    self.consumption_accepted = True
    self.consumptions = []

  def authorize(self, request, ref):
    return self.allowed

  def certified(self, request, ref):
    return self.accepted

  def version_matches(self, request):
    return self.version_accepted

  def finalize_consumption(self, request, ref, observed_sha):
    self.consumptions.append((request.request_id, ref, observed_sha))
    return self.consumption_accepted


class PublisherTests(unittest.TestCase):
  def setUp(self):
    self.request = PublicationRequest(
      "owner/repo", "1.2.3", SHA, SHA, BASE, "request-1", "auth-1", "protection-1", "cert-1", "patch"
    )
    self.provider = Provider()
    self.authority = Authority()

  def publish(self, request=None):
    return publish_stable_tag(
      request or self.request, self.provider, self.authority
    )

  def test_success_idempotent(self):
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")
    self.assertEqual(self.provider.creates, 1)
    self.assertEqual(len(self.authority.consumptions), 2)

  def test_unsupported_protection_is_incomplete(self):
    self.authority.accepted = "INCOMPLETE"
    with self.assertRaises(PublicationIncomplete):
      self.publish()
    self.assertEqual(self.provider.creates, 0)

  def test_failed_consumption_is_incomplete_with_remote_tag_retained(self):
    self.authority.consumption_accepted = False
    with self.assertRaises(PublicationIncomplete):
      self.publish()
    self.assertEqual(self.provider.tags["refs/tags/v1.2.3"], SHA)
    self.authority.consumption_accepted = True
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")
    self.assertEqual(self.provider.creates, 1)

  def test_delayed_response(self):
    self.provider.fail_after_create = True
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")

  def test_invalid_requests(self):
    cases = [
      ("version", "1.2.3-CI-FAIL"),
      ("version", "PRELIM-1.2.3"),
      ("version", "v1.2.3"),
      ("landed_sha", "bad"),
      ("candidate_sha", BASE),
      ("expected_base_sha", "bad"),
      ("repository", ""),
      ("request_id", ""),
      ("authorization_ref", ""),
      ("protection_ref", ""),
      ("certification_ref", ""),
      ("release_class", ""),
    ]
    for field, value in cases:
      with self.subTest(field=field, value=value):
        with self.assertRaises(PublicationRefused):
          self.publish(replace(self.request, **{field: value}))
        self.assertEqual(self.provider.creates, 0)

  def test_authorization_and_freshness_fail_closed(self):
    cases = ["identity", "authority", "certification", "stale",
             "base", "conflict", "ci-fail", "version-mismatch"]
    for failure in cases:
      with self.subTest(failure=failure):
        self.setUp()
        if failure == "identity":
          self.provider.identity = False
        elif failure == "authority":
          self.authority.allowed = False
        elif failure == "certification":
          self.authority.accepted = "FAIL"
        elif failure == "stale":
          self.provider.tip = BASE
        elif failure == "base":
          self.provider.base = SHA
        elif failure == "conflict":
          self.provider.tags["refs/tags/v1.2.3"] = BASE
        elif failure == "version-mismatch":
          self.authority.version_accepted = False
        elif failure == "ci-fail":
          self.provider.tags["refs/tags/v1.2.3-CI-FAIL"] = SHA
        with self.assertRaises(PublicationRefused):
          self.publish()
        self.assertEqual(self.provider.creates, 0)

  def test_truthy_nonboolean_decisions_are_rejected(self):
    for case, value in (
      ("identity", "ALLOW"), ("authorization", "ALLOW"),
      ("version", "PASS"),
    ):
      with self.subTest(case=case):
        self.setUp()
        if case == "identity":
          self.provider.identity = value
        elif case == "authorization":
          self.authority.allowed = value
        else:
          self.authority.version_accepted = value
        with self.assertRaises(PublicationRefused):
          self.publish()
        self.assertEqual(self.provider.creates, 0)

  def test_authority_denial_preserves_tags(self):
    self.authority.allowed = False
    before = dict(self.provider.tags)
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertEqual(self.provider.tags, before)
    self.assertEqual(self.provider.creates, 0)

  def test_existing_terminal_ref_not_updated_or_deleted(self):
    self.provider.tags["refs/tags/v1.2.3"] = BASE
    before = dict(self.provider.tags)
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertEqual(self.provider.tags, before)
    self.assertEqual(self.provider.creates, 0)

  def test_failed_create(self):
    def fail(repository, ref, sha):
      raise ConnectionError("unavailable")
    self.provider.create_tag_if_absent = fail
    with self.assertRaises(PublicationRefused):
      self.publish()

  def test_competing_creators(self):
    for value in (SHA, BASE):
      with self.subTest(value=value):
        self.setUp()
        def race(repository, ref, sha):
          self.provider.tags[ref] = value
          raise RuntimeError("already created")
        self.provider.create_tag_if_absent = race
        if value == SHA:
          self.assertEqual(self.publish(), "refs/tags/v1.2.3")
        else:
          with self.assertRaises(PublicationRefused):
            self.publish()


if __name__ == "__main__":
  unittest.main()
