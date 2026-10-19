"""Cross-branch #681 provider terminal to #103 retirement integration tests."""
from unittest import TestCase

from repo_workflow.integration_host_v2 import IntegrationHost
from repo_workflow.integration_terminal_bridge import VerifiedTerminalReader
from repo_workflow.prelim_retirement import LandedIntegration, PrelimRetirementError
from repo_workflow.prelim_retirement_evidence import verify_retirement_evidence


G = "11111111-1111-4111-8111-111111111111"
P = "refs/heads/PRELIM-issue-123/main-" + G
I = "refs/heads/INT-ATTEMPT-issue-123/main-" + G
S, A, B, L, D = ("a"*40, "b"*40, "c"*40, "d"*40, "e"*40)


class TerminalProjectionTests(TestCase):
  def setUp(self):
    self.landed = LandedIntegration(
      P, S, I, A, "refs/heads/main", L, "integration-123", "terminal-123")
    self.record = {
      "repository": "Org/Repo", "guid": G, "status": "integrated",
      "prelim_ref": P, "prelim_sha": S, "int_attempt_ref": I,
      "accepted_sha": A, "destination_ref": "refs/heads/main",
      "expected_destination_sha": B, "observed_destination_sha": D,
      "landed_sha": L, "integration_id": "integration-123",
      "provider_operation_id": "provider-123", "umbrella": "issue-123",
      "terminal_evidence_ref": "terminal-123",
    }
    self.unavailable = False

  def reader(self):
    def provider(request):
      if self.unavailable:
        raise TimeoutError("provider timeout")
      return {
        "schema_version": 2,
        "repository": request["repository"],
        "operation": request["operation"],
        "request_id": request["request_id"],
        "status": "unchanged",
        "result": {"guid": request["parameters"]["guid"],
                   "record": self.record},
      }
    return VerifiedTerminalReader(
      IntegrationHost("Org/Repo", provider), self.landed, "read-123")

  def test_full_record_projects_exact_verified_retirement_evidence(self):
    result = self.reader()("terminal-123")
    self.assertEqual(set(result), {
      "status", "prelim_ref", "prelim_sha", "int_attempt_ref",
      "accepted_sha", "destination_ref", "landed_sha",
      "integration_id", "terminal_evidence_ref"})
    self.assertEqual(result["landed_sha"], L)

  def test_real_retirement_verifier_consumes_verified_projection(self):
    refs = {P: S, I: A, "refs/heads/main": L}
    def compare(base, head):
      if (base, head) not in {(A, L), (L, L)}:
        raise AssertionError("unexpected ancestry")
      return {"base_sha": base, "head_sha": head,
              "status": "identical" if base == head else "ahead",
              "behind_by": 0}
    result = verify_retirement_evidence(
      self.landed, read_ref=lambda ref: refs.get(ref),
      compare_commits=compare, read_terminal=self.reader())
    self.assertTrue(result.eligible_for_ref_retirement)

  def test_untrusted_or_changed_provider_fields_fail_closed(self):
    changes = [
      ("repository", "Foreign/Repo"),
      ("guid", "22222222-2222-4222-8222-222222222222"),
      ("prelim_ref", P.replace("issue-123", "issue-999")),
      ("int_attempt_ref", I.replace("issue-123", "issue-999")),
      ("umbrella", "issue-999"),
      ("accepted_sha", "9"*40),
      ("observed_destination_sha", "invalid"),
      ("provider_operation_id", ""),
      ("terminal_evidence_ref", "other"),
      ("integration_id", "other"),
      ("status", "failed"),
    ]
    for key, value in changes:
      with self.subTest(key=key):
        original = self.record[key]
        self.record[key] = value
        with self.assertRaises(PrelimRetirementError):
          self.reader()("terminal-123")
        self.record[key] = original

  def test_missing_full_record_or_unexpected_field_denied(self):
    original = self.record
    for invalid in [None, {"status": "integrated"}, dict(original, extra=True)]:
      with self.subTest(invalid=invalid is None):
        self.record = invalid
        with self.assertRaises(PrelimRetirementError):
          self.reader()("terminal-123")
    self.record = original

  def test_wrong_requested_evidence_ref_denied(self):
    with self.assertRaisesRegex(PrelimRetirementError, "request differs"):
      self.reader()("foreign-terminal")

  def test_provider_unknown_denied(self):
    self.unavailable = True
    with self.assertRaisesRegex(PrelimRetirementError, "UNKNOWN"):
      self.reader()("terminal-123")

  def test_same_guid_different_destination_scope_denied(self):
    self.landed = LandedIntegration(
      P, S, I.replace("/main-", "/issue-222-"), A,
      "refs/heads/main", L, "integration-123", "terminal-123")
    with self.assertRaises(PrelimRetirementError):
      self.reader()("terminal-123")
