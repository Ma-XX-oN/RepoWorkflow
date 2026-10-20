"""MIT TIMEOUT and resumable READY chronology at provider v2 boundary."""
import unittest

from repo_workflow.done_mit_defer_v2 import (
  MitDeferError, defer_mit_with_provider,
)
from repo_workflow.done_host_coordinator import IntegrationHostCoordinator
from repo_workflow.integration_coordination import (
  CoordinationError, claim_prelim,
)
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_host_coordinator import FakeHost, GUID, REF, A


class DeferredHost(FakeHost):
  def __init__(self):
    super().__init__()
    self.lost_ack = False
    self.no_write = False
    self.foreign_record = False

  def request(self,operation,request_id,params):
    if operation == "mit.deferred.record":
      self.requests.append((operation,request_id,params))
      if self.no_write:
        raise TimeoutError("write never landed")
      self.defer = dict(params["event"])
      if self.foreign_record:
        self.defer["repository"] = "foreign/Repo"
      if self.lost_ack:
        raise TimeoutError("ACK lost after append")
      return {
        "guid":GUID,"destination":"main","event":dict(params["event"])}
    return super().request(operation,request_id,params)


class MitDeferTests(unittest.TestCase):
  def setUp(self):
    self.host = DeferredHost()
    self.ready = parse_ready_prelim(REF,A)
    self.provider = IntegrationHostCoordinator(self.host)
    self.claim = claim_prelim(self.provider,self.ready,"worker-A")

  def invoke(self,**options):
    args=dict(
      host=self.host,ready=self.ready,lease=self.claim,holder="worker-A",
      reason="timeout",evidence_ref="authenticated-mit-timeout-1",
      event_request_id="mit-event-1",read_request_id="mit-read-1",
    )
    return defer_mit_with_provider(**{**args,**options})

  def test_timeout_is_durable_deferred_not_terminal_fail(self):
    result=self.invoke()
    self.assertEqual(result.event.reason,"timeout")
    self.assertEqual(result.released_generation,2)
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.lease["generation"],2)
    self.assertIsNone(self.host.lease["holder"])
    self.assertEqual(self.host.refs[REF],A)
    with self.assertRaisesRegex(CoordinationError,"approved"):
      claim_prelim(self.provider,self.ready,"worker-B")

  def test_ack_lost_after_durable_append_still_deferred_once(self):
    self.host.lost_ack=True
    result=self.invoke()
    self.assertEqual(result.event.evidence_ref,
                     "authenticated-mit-timeout-1")
    self.assertEqual(self.host.lease["generation"],2)
    self.assertEqual(len([op for op,*_ in self.host.requests
                          if op=="mit.deferred.record"]),1)

  def test_no_durable_event_does_not_release_lease(self):
    self.host.no_write=True
    with self.assertRaisesRegex(MitDeferError,"absent"):
      self.invoke()
    self.assertEqual(self.host.lease["generation"],1)
    self.assertEqual(self.host.lease["holder"],"worker-A")

  def test_foreign_provider_event_does_not_release_lease(self):
    self.host.foreign_record=True
    with self.assertRaisesRegex(MitDeferError,"foreign"):
      self.invoke()
    self.assertEqual(self.host.lease["generation"],1)

  def test_stale_lease_denied_before_publish(self):
    self.host.lease["generation"]=2
    with self.assertRaisesRegex(MitDeferError,"lease changed"):
      self.invoke()
    self.assertFalse(any(op=="mit.deferred.record"
                         for op,*_ in self.host.requests))

  def test_normal_mit_fail_cannot_be_disguised_as_timeout(self):
    with self.assertRaisesRegex(MitDeferError,"provenance absent"):
      self.invoke(reason="failed")
    self.assertEqual(self.host.lease["generation"],1)

  def test_resume_requires_authoritative_fresh_generation(self):
    self.invoke()
    self.host.resume={
      "repository":"Org/Repo","guid":GUID,"destination":"main",
      "prelim_sha":A,"expected_generation":2,
      "deferred_evidence_ref":"authenticated-mit-timeout-1",
      "evidence_ref":"independent-human-approval-1","approved":True}
    resumed=claim_prelim(self.provider,self.ready,"worker-B")
    self.assertEqual((resumed.generation,resumed.holder),(3,"worker-B"))


if __name__=="__main__":
  unittest.main()
