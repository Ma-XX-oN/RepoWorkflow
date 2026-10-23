"""Independent #703 claimed-MIT timeout recovery contracts.

Unit fixtures only: these are not authenticated production-provider results.
Never replay claim_prelim after an externally committed lease-CAS ACK loss.
"""
import unittest

from repo_workflow.done_host_coordinator import IntegrationHostCoordinator
from repo_workflow.done_mit_defer_v2 import MitDeferError, defer_mit_with_provider
from repo_workflow.integration_coordination import (
  CoordinationError, DestinationLease, claim_prelim, release_prelim,
)
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_provider_pipeline import Provider, A, B, G, P


class LostAcknowledgementHost(Provider):
  """Write succeeded remotely before the client's ACK was lost."""

  def __init__(self):
    super().__init__()
    self.lose_deferred_ack = False
    self.lose_read = False
    self.publish_count = 0

  def request(self, operation, request_id, params):
    if operation == "mit.deferred.read" and self.lose_read:
      self.calls.append(operation)
      return {"guid": G, "destination": "main", "event": None}
    result = super().request(operation, request_id, params)
    if operation == "mit.deferred.record":
      self.publish_count += 1
      if self.lose_deferred_ack:
        raise ConnectionError("provider persisted event; response lost")
    return result


class ClaimedTimeoutRecoveryTests(unittest.TestCase):
  def setUp(self):
    self.host = LostAcknowledgementHost()
    self.ready = parse_ready_prelim(P, A)
    self.host.lease = {
      "destination": "main", "generation": 1,
      "guid": G, "holder": "worker-A",
    }
    self.claim = DestinationLease("main", 1, G, "worker-A")
    self.provider = IntegrationHostCoordinator(self.host)

  def defer(self):
    return defer_mit_with_provider(
      host=self.host, ready=self.ready, lease=self.claim,
      holder="worker-A", reason="timeout",
      evidence_ref="github-actions-real-timeout-job-124",
      event_request_id="rwf703-recovery-event-1",
      read_request_id="rwf703-recovery-independent-read-2",
    )

  def test_claimed_lease_resumed_without_second_claim(self):
    outcome = self.defer()
    self.assertEqual(outcome.released_generation, 2)
    self.assertEqual(self.host.lease["generation"], 2)
    self.assertIsNone(self.host.lease["guid"])
    self.assertIsNone(self.host.lease["holder"])
    self.assertEqual(self.host.deferred["reason"], "timeout")
    self.assertEqual(self.host.deferred["prelim_sha"], A)
    self.assertEqual(self.host.deferred["lease_generation"], 1)
    self.assertEqual(self.host.deferred["evidence_ref"],
                     "github-actions-real-timeout-job-124")
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.main, B)
    self.assertNotIn("destination.accept", self.host.calls)
    self.assertEqual(self.host.calls.count("lease.cas"), 1)

  def test_persisted_event_lost_ack_reconciles_without_double_append(self):
    self.host.lose_deferred_ack = True
    outcome = self.defer()
    self.assertEqual(outcome.released_generation, 2)
    self.assertEqual(self.host.publish_count, 1)
    self.assertEqual(self.host.deferred["reason"], "timeout")
    self.assertEqual(self.host.main, B)
    self.assertIsNone(self.host.terminal)

  def test_unknown_readback_retains_claim_then_read_only_recovers(self):
    self.host.lose_read = True
    with self.assertRaisesRegex(MitDeferError, "absent"):
      self.defer()
    self.assertEqual(self.host.publish_count, 1)
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertEqual(self.host.lease["holder"], "worker-A")
    self.assertIsNotNone(self.host.deferred)
    self.assertEqual(self.host.main, B)
    self.host.lose_read = False
    # The write was already durable; a second POST would be a bug.
    released = release_prelim(
      self.provider, self.claim, "worker-A",
      terminal_result="deferred-mit", submission=self.ready,
    )
    self.assertEqual(released.generation, 2)
    self.assertEqual(self.host.publish_count, 1)

  def test_deferred_attempt_denies_reclaim_without_exact_approval(self):
    self.defer()
    with self.assertRaisesRegex(CoordinationError, "approved"):
      claim_prelim(self.provider, self.ready, "worker-B")
    self.assertEqual(self.host.lease["generation"], 2)
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.main, B)

  def test_wrong_or_foreign_claim_fails_without_provider_mutation(self):
    other = DestinationLease("main", 1, G, "other-holder")
    with self.assertRaises(MitDeferError):
      defer_mit_with_provider(
        host=self.host, ready=self.ready, lease=other,
        holder="other-holder", reason="timeout",
        evidence_ref="real-artifact-124", event_request_id="x",
        read_request_id="y",
      )
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertIsNone(self.host.deferred)
    self.assertEqual(self.host.main, B)

  def test_terminal_failed_attempt_is_not_misclassified_as_timeout(self):
    self.host.terminal = {
      "guid": G, "repository": self.host.repository, "status": "failed"
    }
    with self.assertRaisesRegex(MitDeferError, "terminal"):
      self.defer()
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertIsNone(self.host.deferred)
    self.assertEqual(self.host.main, B)


if __name__ == "__main__":
  unittest.main()
