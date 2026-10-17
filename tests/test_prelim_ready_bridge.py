"""Independent-authority bridge between #82 attempt and READY ref."""
import unittest

from repo_workflow.prelim_attempt import PrelimAttempt
from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_bridge import publish_verified_attempt

G = "11111111-1111-4111-8111-111111111111"
S = "a"*40
B = "b"*40
C = "c"*40


class BridgeTests(unittest.TestCase):
  def setUp(self):
    self.attempt = PrelimAttempt(
      G, "ready", "prelim-main-"+G, B, S, C, "1.2.3", 2)
    self.refs = {}
    self.authorized = True
    self.seen = []

  def verify(self, identity):
    self.seen.append(identity)
    return self.authorized

  def publish(self, attempt=None, **overrides):
    def create(ref, sha, key):
      self.refs[ref] = sha
      return True
    arguments = dict(
      ticket=123, destination="main", request_id="publish-"+G,
      verify_authoritative=self.verify,
      read_remote=lambda ref:self.refs.get(ref),
      create_if_absent=create,
    )
    arguments.update(overrides)
    return publish_verified_attempt(
      self.attempt if attempt is None else attempt, **arguments)

  def test_ready_ref_is_exact_candidate(self):
    result = self.publish()
    self.assertEqual(result.sha, C)
    self.assertEqual(result.ref, "refs/heads/PRELIM-issue-123/main-"+G)
    self.assertEqual(self.seen[0].source_sha, S)
    self.assertEqual(self.seen[0].base_sha, B)

  def test_destination_must_be_verified(self):
    self.authorized = False
    with self.assertRaisesRegex(ReadyPublicationError, "not applicable"):
      self.publish(destination="issue-100")
    self.assertFalse(self.refs)

  def test_unfinished_legacy_candidate_rejected(self):
    from dataclasses import replace
    with self.assertRaisesRegex(ReadyPublicationError, "not ready"):
      self.publish(replace(self.attempt, state="conflict"))
    self.assertFalse(self.seen)

  def test_legacy_name_mismatch_rejected(self):
    from dataclasses import replace
    with self.assertRaisesRegex(ReadyPublicationError, "identity"):
      self.publish(replace(self.attempt, branch="some-other-branch"))
    self.assertFalse(self.refs)

  def test_verification_exception_fails_without_publication(self):
    def deny(identity):
      raise TimeoutError("authority missing")
    with self.assertRaisesRegex(ReadyPublicationError, "unavailable"):
      self.publish(verify_authoritative=deny)
    self.assertFalse(self.refs)

  def test_existing_ref_must_not_be_adopted_without_proof(self):
    self.publish()
    with self.assertRaisesRegex(ReadyPublicationError, "already exists"):
      self.publish()

  def test_non_main_requires_explicit_authority(self):
    result = self.publish(destination="issue-100")
    self.assertIn("/issue-100-", result.ref)
    self.assertEqual(self.seen[-1].destination, "issue-100")


if __name__ == "__main__":
  unittest.main()
