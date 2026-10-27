"""Candidate admission against an authoritative exact destination commit."""

import unittest

from repo_workflow.integration_admission import AdmissionError, decide_admission
from repo_workflow.prelim_queue import parse_ready_prelim


GUID = "11111111-1111-4111-8111-111111111111"
SOURCE = "a" * 40
TARGET = "b" * 40
REF = "refs/heads/PRELIM-issue-123/main-" + GUID


class IntegrationAdmissionTests(unittest.TestCase):
  def setUp(self):
    self.candidate = parse_ready_prelim(REF, SOURCE)
    self.parent = "main"
    self.policy = None
    self.reads = []

  def parent_lookup(self, issue):
    self.assertEqual(issue, 123)
    return self.parent

  def read_policy(self, sha, path):
    self.reads.append((sha, path))
    return self.policy

  def decide(self):
    return decide_admission(
      self.candidate, TARGET, resolve_parent=self.parent_lookup,
      read_policy=self.read_policy,
    )

  def test_absent_policy_has_no_added_restriction(self):
    self.assertTrue(self.decide().allowed)
    self.assertEqual(self.reads, [(TARGET,
      ".repoworkflow/allow-tickets/to-main")])

  def test_empty_policy_denies_all(self):
    self.policy = ""
    self.assertFalse(self.decide().allowed)

  def test_allow_only_explicit_immediate_child(self):
    self.policy = "123\n124\n"
    self.assertTrue(self.decide().allowed)
    self.policy = "124\n"
    self.assertFalse(self.decide().allowed)

  def test_parent_mismatch_denies_without_consulting_candidate_policy(self):
    self.parent = "issue-100"
    result = self.decide()
    self.assertFalse(result.allowed)
    self.assertEqual(self.reads, [])

  def test_recheck_policy_at_new_destination_revision(self):
    self.policy = "123\n"
    self.assertTrue(self.decide().allowed)
    self.policy = ""
    self.assertFalse(self.decide().allowed)

  def test_invalid_policy_fails_closed(self):
    for policy in ("0\n", "123\n123\n", "#123\n", "123\n\n"):
      self.policy = policy
      with self.subTest(policy=policy):
        with self.assertRaises(AdmissionError):
          self.decide()

  def test_missing_parent_is_not_assumed(self):
    def missing(issue):
      raise KeyError(issue)
    with self.assertRaises(AdmissionError):
      decide_admission(self.candidate, TARGET,
        resolve_parent=missing, read_policy=self.read_policy)

  def test_changed_commit_identity_is_rejected(self):
    with self.assertRaises(AdmissionError):
      decide_admission(self.candidate, "bad",
        resolve_parent=self.parent_lookup, read_policy=self.read_policy)

  def test_submitted_source_ref_is_not_policy_authority(self):
    self.policy = "123\n"
    result = self.decide()
    self.assertTrue(result.allowed)
    self.assertEqual(self.reads[0][0], TARGET)
    self.assertNotEqual(self.reads[0][0], SOURCE)


if __name__ == "__main__":
  unittest.main()
