"""Immutable PRELIM to mutable INT-ATTEMPT provider boundary tests."""
import unittest

from repo_workflow.done_int_workspace import (
  IntPreparationError, publish_int_workspace,
)
from repo_workflow.prelim_queue import parse_ready_prelim


G = "11111111-1111-4111-8111-111111111111"
READY = f"refs/heads/PRELIM-issue-123/main-{G}"
A = "a" * 40
B = "b" * 40
C = "c" * 40


class Host:
  def __init__(self):
    self.refs = {READY: A}
    self.parent = B
    self.int_sha = None
    self.calls = []
    self.fail = None
    self.advance_during = None

  def request(self, operation, req, params):
    self.calls.append((operation, req, params))
    if self.fail == operation:
      raise TimeoutError("provider UNKNOWN")
    if operation == "refs.list":
      return {"refs": dict(self.refs)}
    if operation == "destination.read":
      return {"ref": "refs/heads/main", "sha": self.parent}
    if operation == "ref.create":
      assert self.int_sha is None
      self.int_sha = params["sha"]
      return {"ref": params["ref"], "sha": self.int_sha}
    if operation == "ref.cas":
      assert self.int_sha == params["expected_sha"]
      self.int_sha = params["sha"]
      if self.advance_during == "cas":
        self.parent = C
      if self.advance_during == "prelim":
        self.refs[READY] = B
      return {"ref": params["ref"], "sha": self.int_sha}
    raise AssertionError(operation)


class IntWorkspaceTests(unittest.TestCase):
  def setUp(self):
    self.host = Host()
    self.ready = parse_ready_prelim(READY, A)

  def publish(self, **overrides):
    args = dict(
      host=self.host, ready=self.ready, expected_parent_sha=B,
      accepted_sha=C, create_id="create-1", update_id="update-1")
    return publish_int_workspace(**{**args, **overrides})

  def test_create_once_and_update_only_int(self):
    result = self.publish()
    self.assertEqual(result.int_ref,
                     READY.replace("PRELIM-", "INT-ATTEMPT-"))
    self.assertEqual((result.prelim_sha, result.accepted_sha), (A, C))
    self.assertEqual(self.host.refs[READY], A)
    self.assertEqual(self.host.int_sha, C)
    self.assertEqual(
      [c[0] for c in self.host.calls],
      ["refs.list", "destination.read", "ref.create", "ref.cas",
       "refs.list", "destination.read"])
    self.assertEqual(len(set(c[1] for c in self.host.calls)), 6)

  def test_unchanged_candidate_skips_workspace_update(self):
    self.publish(accepted_sha=A)
    self.assertEqual(self.host.int_sha, A)
    self.assertNotIn("ref.cas", [c[0] for c in self.host.calls])

  def test_changed_original_ready_ref_denied_before_mutation(self):
    self.host.refs[READY] = C
    with self.assertRaisesRegex(IntPreparationError, "READY"):
      self.publish()
    self.assertIsNone(self.host.int_sha)

  def test_stale_destination_denied_before_mutation(self):
    self.host.parent = C
    with self.assertRaisesRegex(IntPreparationError, "destination moved"):
      self.publish()
    self.assertIsNone(self.host.int_sha)

  def test_parent_advanced_during_workspace_update_not_certified(self):
    self.host.advance_during = "cas"
    with self.assertRaisesRegex(IntPreparationError, "destination moved"):
      self.publish()
    self.assertEqual(self.host.int_sha, C)
    self.assertEqual(self.host.refs[READY], A)

  def test_prelim_moved_during_workspace_update_not_certified(self):
    self.host.advance_during = "prelim"
    with self.assertRaisesRegex(IntPreparationError, "READY"):
      self.publish()
    self.assertEqual(self.host.int_sha, C)

  def test_missing_provider_reply_never_claims_success(self):
    self.host.fail = "ref.cas"
    with self.assertRaises(TimeoutError):
      self.publish()
    self.assertEqual(self.host.refs[READY], A)

  def test_duplicate_request_identity_refused_before_mutation(self):
    with self.assertRaisesRegex(IntPreparationError, "identities"):
      self.publish(update_id="create-1")
    self.assertEqual(self.host.calls, [])


if __name__ == "__main__":
  unittest.main()
