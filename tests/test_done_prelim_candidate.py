"""One immutable PRELIM is the only physical execution candidate."""
import unittest

from repo_workflow.done_prelim_candidate import PrelimCandidateError, verify_prelim_candidate
from repo_workflow.prelim_queue import parse_ready_prelim


READY = "refs/heads/PRELIM-issue-123.0.1"
A, B, C = ("a"*40, "b"*40, "c"*40)


class Host:
  def __init__(self):
    self.refs, self.parent = {READY:A}, B
    self.calls, self.fail, self.advance_during = [], None, None

  def request(self, operation, request_id, params):
    self.calls.append((operation, request_id, params))
    if self.fail == operation:
      raise TimeoutError("provider UNKNOWN")
    if operation == "refs.list":
      return {"refs":dict(self.refs)}
    if operation == "destination.read":
      response = {"ref":"refs/heads/main", "sha":self.parent}
      if self.advance_during == "parent":
        self.parent = C
      if self.advance_during == "prelim":
        self.refs[READY] = C
      return response
    raise AssertionError("candidate verification attempted a mutation: " + operation)


class PrelimCandidateTests(unittest.TestCase):
  def setUp(self):
    self.host = Host()
    self.ready = parse_ready_prelim(READY, A, destination="main")

  def verify(self, **overrides):
    args = dict(host=self.host, ready=self.ready, expected_parent_sha=B, accepted_sha=A)
    return verify_prelim_candidate(**{**args, **overrides})

  def test_current_candidate_needs_no_execution_branch(self):
    result = self.verify()
    self.assertEqual((result.prelim_ref, result.prelim_sha, result.accepted_sha), (READY,A,A))
    self.assertEqual(self.host.refs, {READY:A})
    self.assertEqual({call[0] for call in self.host.calls}, {"refs.list","destination.read"})

  def test_changed_source_requires_a_new_generation_before_verification(self):
    with self.assertRaisesRegex(PrelimCandidateError, "new PRELIM"):
      self.verify(accepted_sha=C)
    self.assertEqual(self.host.calls, [])

  def test_changed_ready_ref_rejects(self):
    self.host.refs[READY] = C
    with self.assertRaisesRegex(PrelimCandidateError, "READY"):
      self.verify()

  def test_stale_parent_rejects(self):
    self.host.parent = C
    with self.assertRaisesRegex(PrelimCandidateError, "destination moved"):
      self.verify()

  def test_parent_advancing_during_read_is_not_certified(self):
    self.host.advance_during = "parent"
    with self.assertRaisesRegex(PrelimCandidateError, "destination moved"):
      self.verify()

  def test_prelim_advancing_during_read_is_not_certified(self):
    self.host.advance_during = "prelim"
    with self.assertRaisesRegex(PrelimCandidateError, "READY"):
      self.verify()

  def test_unknown_provider_reply_cannot_certify_candidate(self):
    self.host.fail = "destination.read"
    with self.assertRaises(TimeoutError):
      self.verify()
    self.assertEqual(self.host.refs, {READY:A})

  def test_resuming_uses_fresh_read_request_identities(self):
    self.verify()
    self.verify()
    self.assertEqual(len({call[1] for call in self.host.calls}), len(self.host.calls))
    self.assertEqual(self.host.refs, {READY:A})


if __name__ == "__main__":
  unittest.main()
