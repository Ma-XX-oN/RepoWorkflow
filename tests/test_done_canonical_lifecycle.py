"""Exact provider completion against real authoritative Git-backed lifecycle."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.done_canonical_lifecycle import (
  CanonicalLifecycleCompletion, CanonicalLifecycleError,
)
from repo_workflow.done_completion import CompletionError
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.state_store import WriterIdentity
from tests.test_done_completion import CompletionTests, RefRetirement


class CanonicalLifecycleTests(unittest.TestCase):
  def setUp(self):
    self.fixture=CompletionTests("test_done_only_after_both_refs_and_provenance")
    self.fixture.setUp()
    self.temp=tempfile.TemporaryDirectory()
    self.root=Path(self.temp.name)
    subprocess.run(["git","init","-q"],cwd=self.root,check=True)
    self.store=LifecycleStore(self.root)
    self.writer=WriterIdentity("rwf109","canonical-fixture")
    candidate=self.fixture.accepted.terminal.accepted_sha
    active=self.store.transition(123,"start",None,3,self.writer,None)
    review=self.store.transition(
      123,"submit-review",candidate,3,self.writer,active.revision)
    accepted=self.store.transition(
      123,"accept",candidate,3,self.writer,review.revision)
    self.assertEqual(accepted.revision,2)
    self.proof=self.fixture.promotion(self.fixture.accepted)
    self.terminal=self.fixture.accepted.terminal
    self.bridge=self.make_bridge()

  def tearDown(self):
    self.temp.cleanup()

  def make_bridge(self,**changes):
    args={
      "store":self.store,"issue":123,
      "expected_revision":2,"relationship_revision":3,
      "writer":self.writer,
      "reread_terminal":lambda guid:self.terminal.record,
      "reread_promotion":lambda op:self.proof,
    }
    return CanonicalLifecycleCompletion(**{**args,**changes})

  def invoke(self,**changes):
    kwargs={
      "persist_lifecycle":self.bridge.persist_lifecycle,
      "read_lifecycle":self.bridge.read_lifecycle,
    }
    return self.fixture.invoke(**{**kwargs,**changes})

  def retirements(self):
    t=self.terminal
    return (
      RefRetirement(t.record["prelim_ref"],t.record["prelim_sha"],True),
      RefRetirement(t.record["int_attempt_ref"],t.accepted_sha,True),
    )

  def test_real_canonical_store_completed_after_retirement_promotion(self):
    result=self.invoke()
    reread=LifecycleStore(self.root).read(123)
    self.assertEqual(result.lifecycle["revision"],3)
    self.assertEqual(reread.revision,3)
    self.assertEqual(reread.lifecycle.state,"completed")
    self.assertTrue(reread.lifecycle.dependency_satisfied)
    self.assertEqual(
      [e.transition for e in reread.lifecycle.history],
      ["start","submit-review","accept","complete"])
    self.assertEqual(result.lifecycle["landed_sha"],self.terminal.landed_sha)

  def test_stable_repeated_command_does_not_append_completion_twice(self):
    first=self.invoke()
    second=self.invoke()
    self.assertEqual(first.lifecycle,second.lifecycle)
    self.assertEqual(LifecycleStore(self.root).read(123).revision,3)

  def test_ambiguous_ack_after_durable_transition_is_recovered(self):
    original=self.store.transition
    def commit_then_timeout(*args):
      original(*args)
      raise TimeoutError("committed completion ACK lost")
    self.store.transition=commit_then_timeout
    result=self.invoke()
    self.assertEqual(result.lifecycle["revision"],3)
    self.assertEqual(LifecycleStore(self.root).read(123).revision,3)

  def test_uncommitted_lifecycle_cannot_be_inferred_from_provider(self):
    def timeout(*args):
      raise TimeoutError("completion never committed")
    self.store.transition=timeout
    with self.assertRaisesRegex(CompletionError,"lifecycle"):
      self.invoke()
    snapshot=LifecycleStore(self.root).read(123)
    self.assertEqual(snapshot.revision,2)
    self.assertEqual(snapshot.lifecycle.state,"accepted")

  def test_read_method_does_not_create_missing_completion(self):
    with self.assertRaisesRegex(
        CanonicalLifecycleError,"completed revision"):
      self.bridge.read_lifecycle(
        self.fixture.accepted,self.proof,self.retirements())
    self.assertEqual(self.store.read(123).revision,2)

  def test_failed_retirement_prevents_canonical_state_change(self):
    self.fixture.fail="PRELIM"
    with self.assertRaisesRegex(CompletionError,"retirement"):
      self.invoke()
    self.assertEqual(self.store.read(123).lifecycle.state,"accepted")

  def test_missing_provider_provenance_does_not_complete_review(self):
    self.bridge=self.make_bridge(reread_terminal=lambda guid:None)
    with self.assertRaises(CompletionError):
      self.invoke()
    self.assertEqual(self.store.read(123).revision,2)

  def test_wrong_issue_fails_before_lifecycle_transition(self):
    self.bridge=self.make_bridge(issue=124)
    with self.assertRaisesRegex(CompletionError,"lifecycle"):
      self.invoke()
    self.assertEqual(self.store.read(123).revision,2)

  def test_unauthenticated_revised_retirement_refused(self):
    altered=list(self.retirements())
    altered[1]=replace(altered[1],absent_after=False)
    with self.assertRaisesRegex(CanonicalLifecycleError,"retirements"):
      self.bridge.persist_lifecycle(
        self.fixture.accepted,self.proof,tuple(altered))
    self.assertEqual(self.store.read(123).revision,2)

  def test_external_lifecycle_revision_change_rejected_on_readback(self):
    self.invoke()
    wrong=self.make_bridge(expected_revision=1)
    with self.assertRaisesRegex(CanonicalLifecycleError,"revision"):
      wrong.read_lifecycle(
        self.fixture.accepted,self.proof,self.retirements())


if __name__=="__main__":
  unittest.main()
