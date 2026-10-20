"""Contract tests for the #109 to #681 destination.accept bridge."""
from dataclasses import replace
import unittest

from repo_workflow.done_executor import DoneExecutionError
from repo_workflow.done_provider_acceptance import (
  DestinationAcceptanceFacts, bind_v2_destination_accept,
)


A = "a" * 40
B = "b" * 40
C = "c" * 40
G = "11111111-1111-4111-8111-111111111111"
INT = f"refs/heads/INT-ATTEMPT-issue-123/main-{G}"


class Host:
  repository = "owner/repo"

  def __init__(self):
    self.calls = []
    self.reply = {
      "destination": "main", "expected_sha": B,
      "landed_sha": C, "operation_id": "op-1",
    }

  def request(self, operation, key, parameters):
    self.calls.append((operation, key, parameters))
    return self.reply


class ProviderAcceptTests(unittest.TestCase):
  def setUp(self):
    self.host = Host()
    self.facts = DestinationAcceptanceFacts(
      "owner/repo", 123, "main", G, 1, "coordinator-A", C,
    )

  def invoke(self, *, facts=None, ref=INT, source=A, destination="main",
             old=B, evidence="evidence-1", authorization="grant-1",
             operation="op-1"):
    bound = bind_v2_destination_accept(
      self.host, self.facts if facts is None else facts)
    return bound(ref, source, destination, old, evidence,
                 authorization, operation)

  def test_exact_record_and_receipt(self):
    receipt = self.invoke()
    self.assertEqual((receipt.landed_sha, receipt.operation_id), (C, "op-1"))
    self.assertTrue(receipt.verified)
    self.assertEqual(len(self.host.calls), 1)
    operation, key, params = self.host.calls[0]
    self.assertEqual((operation, key), ("destination.accept", "op-1"))
    self.assertEqual(params["record"], {
      "repository": "owner/repo", "destination": "main",
      "int_attempt_ref": INT, "accepted_sha": A,
      "expected_destination_sha": B, "proposed_sha": C,
      "guid": G, "lease_generation": 1, "holder": "coordinator-A",
      "authorization_ref": "grant-1", "evidence_ref": "evidence-1",
      "operation_id": "op-1",
    })

  def test_wrong_workspace_and_destination_refused_before_provider(self):
    for ref, destination in (
      (INT.replace("issue-123", "issue-124"), "main"),
      (INT.replace("/main-", "/issue-9-"), "main"),
      (INT[:-36] + "forged", "main"),
      (INT, "issue-9"),
    ):
      with self.subTest(ref=ref, destination=destination):
        with self.assertRaisesRegex(DoneExecutionError, "identity"):
          self.invoke(ref=ref, destination=destination)
    self.assertEqual(self.host.calls, [])

  def test_missing_or_changed_authority_refused(self):
    for settings in (
      {"source": "z" * 40},
      {"old": "missing"},
      {"old": C},
      {"operation": ""},
      {"authorization": ""},
      {"evidence": ""},
    ):
      with self.subTest(settings=settings):
        with self.assertRaises(DoneExecutionError):
          self.invoke(**settings)
    self.assertEqual(self.host.calls, [])

  def test_foreign_provider_identity_refused_before_mutation(self):
    self.host.repository = "attacker/other"
    with self.assertRaisesRegex(DoneExecutionError, "host binding"):
      self.invoke()
    self.assertEqual(self.host.calls, [])

  def test_wrong_lease_generation_and_ticket_refused(self):
    for facts in (
      replace(self.facts, lease_generation=0),
      replace(self.facts, lease_generation=True),
      replace(self.facts, ticket=0),
      replace(self.facts, guid="not-a-guid"),
    ):
      with self.subTest(facts=facts):
        with self.assertRaisesRegex(DoneExecutionError, "facts"):
          self.invoke(facts=facts)
    self.assertEqual(self.host.calls, [])

  def test_foreign_or_missing_receipt_denied(self):
    for wrong in (
      None, True, {},
      {**self.host.reply, "landed_sha": A},
      {**self.host.reply, "operation_id": "other"},
      {**self.host.reply, "expected_sha": A},
    ):
      self.host.reply = wrong
      with self.subTest(reply=wrong):
        with self.assertRaisesRegex(DoneExecutionError, "receipt"):
          self.invoke()


if __name__ == "__main__":
  unittest.main()
