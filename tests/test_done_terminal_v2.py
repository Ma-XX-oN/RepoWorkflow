"""Terminal v2 positive, lost-ACK and forged record refusal tests."""
import unittest

from repo_workflow.done_executor import AcceptedIntegration
from repo_workflow.done_terminal_v2 import (
  TerminalPublicationError, publish_integrated_terminal,
)
from repo_workflow.prelim_queue import parse_ready_prelim


G = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/PRELIM-issue-123/main-{G}"
INT = REF.replace("PRELIM-", "INT-ATTEMPT-")
A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)


class Host:
  repository = "Org/Repo"

  def __init__(self):
    self.destination = D
    self.persisted = None
    self.calls = []
    self.lost_ack = False
    self.forger = None

  def request(self, operation, key, params):
    self.calls.append((operation, key))
    if operation == "destination.read":
      return {"ref": "refs/heads/main", "sha": self.destination}
    if operation == "attempt.record":
      self.persisted = dict(params["record"])
      if self.lost_ack:
        raise TimeoutError("lost ACK")
      return dict(params)
    if operation == "attempt.read":
      record = self.persisted
      if self.forger is not None:
        record = self.forger
      return {"guid": G, "record": record}
    raise AssertionError(operation)


class TerminalV2Tests(unittest.TestCase):
  def setUp(self):
    self.host = Host()
    self.ready = parse_ready_prelim(REF, A)
    self.params = {
      "host": self.host, "ready": self.ready, "int_attempt_ref": INT,
      "accepted_sha": C, "old_destination_sha": B, "landed_sha": D,
      "operation_id": "op-1", "integration_id": "integration-1",
      "terminal_evidence_ref": "provider-verified-terminal-1",
      "record_request_id": "terminal-1",
      "accepted_integration": AcceptedIntegration(D, True, "op-1"),
    }

  def publish(self, **changes):
    return publish_integrated_terminal(**{**self.params, **changes})

  def test_persist_exact_authenticated_provenance(self):
    terminal = self.publish()
    self.assertEqual(terminal.guid, G)
    self.assertEqual(terminal.record["prelim_sha"], A)
    self.assertEqual(terminal.record["accepted_sha"], C)
    self.assertEqual(terminal.record["landed_sha"], D)
    self.assertEqual(terminal.record["provider_operation_id"], "op-1")
    self.assertEqual([op for op, _ in self.host.calls],
                     ["destination.read", "attempt.record", "attempt.read"])

  def test_lost_ack_exact_persisted_record_recovered(self):
    self.host.lost_ack = True
    terminal = self.publish()
    self.assertEqual(terminal.record, self.host.persisted)
    self.assertEqual(len([op for op, _ in self.host.calls
                          if op == "attempt.record"]), 1)

  def test_lost_ack_without_record_never_counts_as_integrated(self):
    self.host.lost_ack = True
    self.host.forger = None
    self.host.persisted = None
    original = self.host.request
    def no_publication(op, key, params):
      if op == "attempt.record":
        raise TimeoutError("server did not persist")
      return original(op, key, params)
    self.host.request = no_publication
    with self.assertRaisesRegex(TerminalPublicationError, "missing"):
      self.publish()

  def test_foreign_cas_receipt_denied_before_persist(self):
    for receipt in (
      None, AcceptedIntegration(A, True, "op-1"),
      AcceptedIntegration(D, False, "op-1"),
      AcceptedIntegration(D, True, "other-operation"),
    ):
      with self.subTest(receipt=receipt):
        with self.assertRaisesRegex(TerminalPublicationError, "CAS receipt"):
          self.publish(accepted_integration=receipt)
    self.assertEqual(self.host.calls, [])

  def test_wrong_landed_tip_denied_before_publish(self):
    self.host.destination = A
    with self.assertRaisesRegex(TerminalPublicationError,"not current"):
      self.publish()
    self.assertIsNone(self.host.persisted)

  def test_cross_submission_workspace_denied(self):
    with self.assertRaisesRegex(TerminalPublicationError,"scope"):
      self.publish(int_attempt_ref=INT.replace("issue-123", "issue-124"))
    self.assertEqual(self.host.calls, [])

  def test_foreign_terminal_readback_refused(self):
    self.host.forger = {"guid": G, "repository": "Other/Repo",
                        "status": "integrated"}
    with self.assertRaisesRegex(TerminalPublicationError,"foreign"):
      self.publish()

  def test_missing_terminal_verifier_ref_denied(self):
    with self.assertRaisesRegex(TerminalPublicationError,"provenance"):
      self.publish(terminal_evidence_ref="")
    self.assertEqual(self.host.calls, [])

  def test_distinct_read_request_keys(self):
    self.publish()
    ids = [key for _, key in self.host.calls]
    self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
  unittest.main()
