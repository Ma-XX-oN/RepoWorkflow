"""READY submission contract tests independent of queue implementation."""
import unittest

from repo_workflow.prelim_ready import (
  ReadyPublicationError, publish_ready_prelim,
)

GUID = "11111111-1111-4111-8111-111111111111"
SHA = "a"*40


class ReadyPublicationTests(unittest.TestCase):
  def setUp(self):
    self.refs = {}
    self.created = []
    self.kw = {
      "ticket": 123, "destination": "main", "guid": GUID,
      "candidate_sha": SHA, "request_id": "ready-123-1",
      "read_remote": lambda name: self.refs.get(name),
      "create_if_absent": self.create,
    }

  def create(self, name, sha, request):
    self.created.append((name, sha, request))
    self.refs[name] = sha
    return True

  def publish(self, **changes):
    return publish_ready_prelim(**dict(self.kw, **changes))

  def test_first_publication_is_ready_without_queue_file(self):
    result = self.publish()
    self.assertEqual(result.ref, f"refs/heads/PRELIM-issue-123/main-{GUID}")
    self.assertEqual(result.sha, SHA)
    self.assertEqual(len(self.refs), 1)

  def test_published_ref_cannot_be_updated_or_adopted(self):
    self.publish()
    with self.assertRaisesRegex(ReadyPublicationError, "already exists"):
      self.publish()
    self.assertEqual(len(self.created), 1)

  def test_different_destination_and_guid(self):
    result = self.publish(destination="issue-100")
    self.assertIn("/issue-100-", result.ref)

  def test_invalid_destination_and_sha_fail_before_mutation(self):
    for changes in ({"destination": "../main"}, {"candidate_sha": "bad"},
                    {"ticket": 0}, {"guid": "not-a-guid"}):
      with self.subTest(changes=changes):
        with self.assertRaises(ReadyPublicationError):
          self.publish(**changes)
    self.assertEqual(self.created, [])

  def test_ambiguous_provider_outcome_not_reported_as_published(self):
    def unknown(name, sha, request):
      self.refs[name] = sha
      raise TimeoutError("response lost")
    with self.assertRaisesRegex(ReadyPublicationError, "UNKNOWN"):
      self.publish(create_if_absent=unknown)

  def test_exact_retry_uses_durable_idempotency_record(self):
    first = self.publish()
    record = {"ref": first.ref, "sha": first.sha,
              "request_id": first.request_id, "status": "published"}
    second = self.publish(
      read_publication_record=lambda request: record)
    self.assertEqual(second, first)
    self.assertEqual(len(self.created), 1)

  def test_wrong_request_proof_cannot_adopt_existing_ref(self):
    first = self.publish()
    record = {"ref": first.ref, "sha": first.sha,
              "request_id": "different", "status": "published"}
    with self.assertRaisesRegex(ReadyPublicationError, "already exists"):
      self.publish(read_publication_record=lambda request: record)

  def test_lost_response_requires_exact_durable_proof(self):
    expected_ref = f"refs/heads/PRELIM-issue-123/main-{GUID}"
    record = {"ref": expected_ref, "sha": SHA,
              "request_id": "ready-123-1", "status": "published"}
    def unknown(name, sha, request):
      self.refs[name] = sha
      raise TimeoutError("lost reply")
    result = self.publish(create_if_absent=unknown,
      read_publication_record=lambda request: record)
    self.assertEqual(result.sha, SHA)

  def test_wrong_published_sha_rejected(self):
    def wrong(name, sha, request):
      self.refs[name] = "b"*40
      return True
    with self.assertRaisesRegex(ReadyPublicationError, "readback"):
      self.publish(create_if_absent=wrong)


if __name__ == "__main__":
  unittest.main()
