"""Independent negative tests for failed-provider terminal persistence."""
from dataclasses import replace
import unittest

from repo_workflow.done_failed_attempt import (
  FailedIntegrationEvidence, FailureRecordError, record_failed_attempt,
)
from repo_workflow.done_host_coordinator import IntegrationHostCoordinator
from repo_workflow.integration_coordination import claim_prelim
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_host_coordinator import FakeHost, GUID, REF, A


B="b"*40


class FailedHost(FakeHost):
  def __init__(self):
    super().__init__()
    self.ack_lost=False
    self.absent_write=False
    self.forge=False

  def request(self,op,key,params):
    if op == "attempt.record":
      self.requests.append((op,key,params))
      if self.absent_write:
        raise ConnectionError("write absent")
      self.terminal=dict(params["record"])
      if self.ack_lost:
        raise TimeoutError("lost ACK")
      return dict(params)
    if op=="attempt.read" and self.forge:
      return {"guid":GUID,"record":{"status":"integrated"}}
    return super().request(op,key,params)


class FailedTerminalTests(unittest.TestCase):
  def setUp(self):
    self.host=FailedHost()
    self.ready=parse_ready_prelim(REF,A)
    self.coord=IntegrationHostCoordinator(self.host)
    self.lease=claim_prelim(self.coord,self.ready,"worker-A")
    self.evidence=FailedIntegrationEvidence(
      GUID,A,B,B,"integration-1","operation-1","auth-failure-1",True)

  def invoke(self,**changed):
    args={
      "host":self.host,
      "ready":self.ready,"lease":self.lease,"holder":"worker-A",
      "evidence":self.evidence,
      "terminal_request_id":"terminal-1",
      "read_request_id":"terminal-read-1",
    }
    return record_failed_attempt(**{**args,**changed})

  def test_failed_terminal_persists_and_releases_without_merge(self):
    record,released=self.invoke()
    self.assertEqual(record["status"],"failed")
    self.assertIsNone(record["landed_sha"])
    self.assertEqual(released.generation,2)
    self.assertIsNone(self.host.lease["holder"])
    self.assertEqual(self.host.refs[REF],A)

  def test_lost_ack_independent_exact_readback_recovers(self):
    self.host.ack_lost=True
    record,released=self.invoke()
    self.assertEqual(self.host.terminal,record)
    self.assertEqual(released.generation,2)
    self.assertEqual(len([x for x in self.host.requests
                          if x[0]=="attempt.record"]),1)

  def test_no_persisted_failure_never_releases(self):
    self.host.absent_write=True
    with self.assertRaisesRegex(FailureRecordError,"missing"):
      self.invoke()
    self.assertEqual(self.host.lease["generation"],1)

  def test_forged_terminal_never_releases(self):
    self.host.forge=True
    with self.assertRaisesRegex(FailureRecordError,"mismatched"):
      self.invoke()
    self.assertEqual(self.host.lease["generation"],1)

  def test_missing_authenticated_failure_refused(self):
    altered=replace(self.evidence,authenticated=False)
    with self.assertRaisesRegex(FailureRecordError,"identity"):
      self.invoke(evidence=altered)
    self.assertIsNone(self.host.terminal)

  def test_foreign_guid_refused_before_write(self):
    altered=replace(
      self.evidence,guid="22222222-2222-4222-8222-222222222222")
    with self.assertRaises(FailureRecordError):
      self.invoke(evidence=altered)
    self.assertIsNone(self.host.terminal)

  def test_stale_lease_requires_readback_reconciliation(self):
    self.host.lease["generation"]=2
    with self.assertRaisesRegex(FailureRecordError,"lease changed"):
      self.invoke()
    self.assertIsNone(self.host.terminal)


if __name__=="__main__":
  unittest.main()
