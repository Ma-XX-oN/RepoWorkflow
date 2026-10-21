"""Retirement/evidence/lifecycle completion ordering and refusal tests."""
from dataclasses import replace
from collections import namedtuple
import unittest

from repo_workflow.done_completion import (
  CompletionError, complete_accepted_provider_attempt,
)
from repo_workflow.done_evidence_promotion import Promotion
RefRetirement = namedtuple(
  'RefRetirement', 'ref previously_observed_sha absent_after')
from tests.test_done_provider_pipeline import PipelineTests, G, A, B, C, D


class CompletionTests(unittest.TestCase):
  def setUp(self):
    base=PipelineTests("test_one_ready_end_to_end_local_provider_simulation")
    base.setUp()
    self.accepted=base.invoke()
    self.host=base.host
    self.host.repository="Org/Repo"
    self.host.retirements={}
    self.events=[]
    self.fail=None
    initial=self.host.request

    def responder(operation,key,params):
      if operation=="retirement.record":
        self.events.append(("retirement.record",params["ref_kind"]))
        if self.fail=="retirement.record":
          raise TimeoutError("ack lost")
        self.host.retirements[params["ref_kind"]]=params["record"]
        return params
      if operation=="retirement.read":
        self.events.append(("retirement.read",params["ref_kind"]))
        return {"guid":G,"ref_kind":params["ref_kind"],
                "record":self.host.retirements.get(params["ref_kind"])}
      return initial(operation,key,params)
    self.host.request=responder
    self.lifecycle=None

  def retire(self,landed,read_terminal,kind):
    self.events.append(("retire",kind))
    read_terminal(landed.terminal_evidence_ref)
    ref=landed.prelim_ref if kind=="PRELIM" else landed.int_attempt_ref
    sha=landed.prelim_sha if kind=="PRELIM" else landed.accepted_sha
    if self.fail==kind:
      return RefRetirement(ref,sha,False)
    return RefRetirement(ref,sha,True)

  def promotion(self,accepted):
    self.events.append(("promote",accepted.accepted.operation_id))
    if self.fail=="promotion":
      raise TimeoutError("hosted stage unknown")
    return Promotion("op-1",C,C,B,D,A,A,"context",())

  def persist_lifecycle(self,accepted,proof,retirements):
    assert len(retirements)==2 and all(r.absent_after for r in retirements)
    self.events.append(("lifecycle.record",G))
    if self.fail=="lifecycle.record":
      raise TimeoutError("write lost")
    self.lifecycle={
      "guid":G,"operation_id":"op-1","landed_sha":D,
      "result":"done","revision":3,
    }

  def read_lifecycle(self,accepted,proof,retirements):
    assert len(retirements)==2
    self.events.append(("lifecycle.read",G))
    return self.lifecycle

  def invoke(self,**changes):
    args={
      "host":self.host,"accepted":self.accepted,
      "retire_ref":self.retire,"promote":self.promotion,
      "persist_lifecycle":self.persist_lifecycle,
      "read_lifecycle":self.read_lifecycle,
      "retirement_id_prefix":"retirement-1",
    }
    return complete_accepted_provider_attempt(**{**args,**changes})

  def test_done_only_after_both_refs_and_provenance(self):
    final=self.invoke()
    self.assertEqual(final.operation_id,"op-1")
    self.assertEqual(len(final.retired),2)
    self.assertEqual(final.lifecycle["result"],"done")
    self.assertEqual([kind for op,kind in self.events if op=="retire"],
                     ["PRELIM","INT-ATTEMPT"])
    self.assertLess(
      self.events.index(("retirement.read","INT-ATTEMPT")),
      self.events.index(("promote","op-1")))
    self.assertLess(
      self.events.index(("promote","op-1")),
      self.events.index(("lifecycle.record",G)))

  def test_incomplete_retirement_never_promotes(self):
    for failed in ("PRELIM","INT-ATTEMPT"):
      self.events=[]
      self.host.retirements={}
      self.fail=failed
      with self.subTest(kind=failed):
        with self.assertRaisesRegex(CompletionError,"unverified"):
          self.invoke()
      self.assertFalse(any(op=="promote" for op,_ in self.events))

  def test_missing_retirement_history_cannot_complete(self):
    self.fail="retirement.record"
    with self.assertRaisesRegex(CompletionError,"history absent"):
      self.invoke()
    self.assertIsNone(self.lifecycle)

  def test_foreign_tested_source_cannot_be_promoted_as_done(self):
    old=self.promotion
    self.promotion=lambda accepted:Promotion(
      "op-1",A,C,B,D,A,A,"context",())
    with self.assertRaisesRegex(CompletionError,"promotion provenance"):
      self.invoke()
    self.assertIsNone(self.lifecycle)

  def test_foreign_old_parent_is_not_completion(self):
    self.promotion=lambda accepted:Promotion(
      "op-1",C,C,A,D,A,A,"context",())
    with self.assertRaisesRegex(CompletionError,"promotion provenance"):
      self.invoke()
    self.assertIsNone(self.lifecycle)

  def test_missing_promotion_cannot_complete(self):
    self.fail="promotion"
    with self.assertRaisesRegex(CompletionError,"promotion UNKNOWN"):
      self.invoke()
    self.assertIsNone(self.lifecycle)

  def test_missing_lifecycle_readback_never_returns_done(self):
    self.fail="lifecycle.record"
    with self.assertRaisesRegex(CompletionError,"lifecycle history"):
      self.invoke()

  def test_foreign_landing_rejected_before_retirement(self):
    changed=replace(self.accepted.accepted,operation_id="other")
    with self.assertRaisesRegex(CompletionError,"terminal disagrees"):
      self.invoke(accepted=replace(self.accepted,accepted=changed))
    self.assertFalse(self.events)


if __name__=="__main__":
  unittest.main()
