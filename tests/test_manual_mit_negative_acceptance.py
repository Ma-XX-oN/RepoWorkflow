"""Independent RED oracle for RWF #703 (#699). Simulation is not provider proof."""
import unittest

from repo_workflow.done_executor import DoneExecutionError
from repo_workflow.done_provider_pipeline import (
  DeferredProviderAttempt, FailedProviderAttempt,
)
from repo_workflow.done_stage_certification import (
  CertifiedStages, MitTimedOut, StageFailed, VerifiedMitPolicy, VerifiedStage,
)
from repo_workflow.done_provider_acceptance import DestinationAcceptanceFacts
from tests import test_done_provider_pipeline as fixture_module
from repo_workflow.integration_coordination import CoordinationError


class ManualMitNegativeAcceptanceTests(unittest.TestCase):
  def setUp(self):
    self.fixture = fixture_module.PipelineTests(
      "test_one_ready_end_to_end_local_provider_simulation")
    self.fixture.setUp()
    self.host = self.fixture.host
    self.initial_tip = self.host.main

  @staticmethod
  def stage(name, source, parent, status="PASS", evidence=None):
    return VerifiedStage(
      name, source, parent, status, "run-" + name,
      evidence or "evidence-" + name, "catalogue-v1",
      "config-v1", "inputs-v1", "2027-01-01T00:00:00Z", True)

  def pass_required(self, source, parent):
    return CertifiedStages(
      source, parent,
      tuple(self.stage(stage, source, parent)
            for stage in ("ART", "AIT", "release", "MIT")),
      VerifiedMitPolicy(source, parent, True, "policy-required", True))

  def fail_mit(self, source, parent, evidence="mit-fail-actual"):
    raise StageFailed(
      "MIT", self.stage("MIT", source, parent, "FAIL", evidence))

  def assert_no_landing(self):
    self.assertEqual(self.host.main, self.initial_tip)
    self.assertNotIn("destination.accept", self.host.calls)
    self.assertFalse(self.host.terminal and
                     self.host.terminal.get("status") == "integrated")

  def test_fail_before_int_is_durable_and_denies_cas(self):
    result = self.fixture.invoke(stage_certify=self.fail_mit)
    self.assertIsInstance(result, FailedProviderAttempt)
    self.assertEqual(result.failed_stage, "MIT")
    self.assertEqual(result.evidence_ref, "mit-fail-actual")
    self.assertEqual(self.host.terminal["status"], "failed")
    self.assertEqual(self.host.terminal["accepted_sha"], "c" * 40)
    self.assertEqual(self.host.terminal["expected_destination_sha"], fixture_module.B)
    self.assertIsNone(self.host.terminal["landed_sha"])
    self.assertIsNone(self.host.int_sha)
    self.assertIsNone(self.host.lease["holder"])
    self.assert_no_landing()

  def test_fail_after_int_preparation_denies_cas(self):
    calls = []
    def stage_certify(source, parent):
      calls.append((source, parent))
      if len(calls) == 1:
        return self.pass_required(source, parent)
      self.fail_mit(source, parent, "mit-fail-after-preparation")
    result = self.fixture.invoke(stage_certify=stage_certify)
    self.assertEqual(len(calls), 2)
    self.assertIsInstance(result, FailedProviderAttempt)
    self.assertEqual(result.failed_stage, "MIT")
    self.assertEqual(result.evidence_ref, "mit-fail-after-preparation")
    self.assertEqual(self.host.terminal["status"], "failed")
    self.assertEqual(self.host.int_sha, "c" * 40)
    self.assert_no_landing()

  def test_foreign_failure_provenance_rejects_without_terminal(self):
    def foreign(source, parent):
      raise StageFailed(
        "MIT", self.stage("MIT", "f" * 40, parent, "FAIL"))
    with self.assertRaisesRegex(DoneExecutionError, "unverified"):
      self.fixture.invoke(stage_certify=foreign)
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertIsNone(self.host.terminal)
    self.assert_no_landing()

  def test_lost_ack_reconciles_exactly_one_failure_record(self):
    original = self.host.request
    posted = []
    def lose_ack(operation, request_id, params):
      response = original(operation, request_id, params)
      if operation == "attempt.record":
        posted.append(request_id)
        raise ConnectionError("ACK lost after durable append")
      return response
    self.host.request = lose_ack
    result = self.fixture.invoke(stage_certify=self.fail_mit)
    self.assertIsInstance(result, FailedProviderAttempt)
    self.assertEqual(len(posted), 1)
    self.assertEqual(self.host.terminal["status"], "failed")
    self.assert_no_landing()

  def test_required_mit_without_receipt_does_not_pass(self):
    def omit(source, parent):
      stages = tuple(self.stage(s, source, parent)
                     for s in ("ART", "AIT", "release"))
      return CertifiedStages(
        source, parent, stages,
        VerifiedMitPolicy(source, parent, True, "policy-required", True))
    with self.assertRaisesRegex(DoneExecutionError, "stage identity"):
      self.fixture.invoke(stage_certify=omit)
    self.assertIsNone(self.host.terminal)
    self.assertIsNone(self.host.int_sha)
    self.assert_no_landing()

  def test_timeout_is_deferred_not_failed(self):
    def timeout(_source, _parent):
      raise MitTimedOut("mit-timeout-evidence")
    result = self.fixture.invoke(
      stage_certify=timeout,
      mit_event_request_id="issue-703-timeout-event-1",
      mit_read_request_id="issue-703-timeout-read-1")
    self.assertIsInstance(result, DeferredProviderAttempt)
    self.assertEqual(self.host.deferred["reason"], "timeout")
    self.assertIsNone(self.host.terminal)
    self.assertIsNone(self.host.lease["holder"])
    self.assert_no_landing()

  def test_stale_mit_pass_after_preparation_denies_cas(self):
    calls = []
    def drift(source, parent):
      calls.append(1)
      prior = self.pass_required(source, parent)
      if len(calls) == 1:
        return prior
      changed = tuple(self.stage(
        receipt.stage, source, parent, evidence=receipt.evidence_ref + "-new")
        for receipt in prior.stages)
      return CertifiedStages(source, parent, changed, prior.mit_policy)
    with self.assertRaisesRegex(
        DoneExecutionError, "stages changed before integration CAS"):
      self.fixture.invoke(stage_certify=drift)
    self.assertEqual(len(calls), 2)
    self.assert_no_landing()

  def test_failed_exact_candidate_cannot_replay_as_pass(self):
    first = self.fixture.invoke(stage_certify=self.fail_mit)
    self.assertIsInstance(first, FailedProviderAttempt)
    facts = DestinationAcceptanceFacts(
      self.host.repository, 123, "main", self.fixture.ready.guid,
      self.host.lease["generation"] + 1, "worker-A", "d" * 40)
    # RED guard. A failed immutable READY cannot later be accepted under
    # the same identity when the mocked stage oracle changes to PASS.
    with self.assertRaisesRegex(
        CoordinationError, "persisted terminal result"):
      self.fixture.invoke(
        stage_certify=self.pass_required, provider_facts=facts)
    self.assert_no_landing()


  def test_failed_write_unknown_never_lands_and_retains_claim(self):
    from repo_workflow.done_failed_attempt import FailureRecordError
    original = self.host.request
    def fail_before_write(operation, request_id, params):
      if operation == "attempt.record":
        raise ConnectionError("provider inaccessible before append")
      return original(operation, request_id, params)
    self.host.request = fail_before_write
    with self.assertRaisesRegex(FailureRecordError, "missing or mismatched"):
      self.fixture.invoke(stage_certify=self.fail_mit)
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertEqual(self.host.lease["holder"], "worker-A")
    self.assert_no_landing()

  def test_mit_failed_outcome_requires_handoff_and_never_completes(self):
    from repo_workflow.done_runtime import VerifiedFailedDone
    from repo_workflow.done_failure_handoff import (
      FailureHandoff, PersistedFailureHandoff,
    )
    from repo_workflow.done_provider_pipeline import FailedProviderAttempt
    from tests import test_done_runtime as runtime_fixture
    from tests.test_done_provider_pipeline import A, B, C, G
    fixture = runtime_fixture.RuntimeTests(
      "test_failed_stage_requires_durable_issue_handoff")
    fixture.setUp()
    failed = FailedProviderAttempt(fixture.ready, "MIT", "mit-failure-proof", 2)
    handoff = FailureHandoff(
      G, 123, "main", A, B, C, "MIT_FAIL", "mit-failure-proof",
      (123,), "operator-proof", (), "not-a-conflict", "operation-1")
    persisted = PersistedFailureHandoff(
      handoff, ((123, "issue-comment-703"),))
    completion_calls = []
    handoff_calls = []
    def never_complete(result):
      completion_calls.append(result)
      raise AssertionError("completion forbidden after MIT FAIL")
    def record_handoff(result):
      handoff_calls.append(result)
      return persisted
    result = fixture.invoke(
      execute_provider_attempt=lambda *args:failed,
      complete_accepted=never_complete,
      publish_failure_handoff=record_handoff)
    self.assertIsInstance(result, VerifiedFailedDone)
    self.assertEqual(result.attempt, failed)
    self.assertEqual(result.persisted_handoff, persisted)
    self.assertEqual(completion_calls, [])
    self.assertEqual(handoff_calls, [failed])

  def test_missing_mit_failure_handoff_cannot_claim_done(self):
    from repo_workflow.done_runtime import DoneRuntimeError
    from repo_workflow.done_provider_pipeline import FailedProviderAttempt
    from tests import test_done_runtime as runtime_fixture
    fixture = runtime_fixture.RuntimeTests(
      "test_failed_stage_requires_durable_issue_handoff")
    fixture.setUp()
    failed = FailedProviderAttempt(fixture.ready, "MIT", "mit-failure-proof", 2)
    completion_calls = []
    with self.assertRaisesRegex(DoneRuntimeError, "durable owner handoff"):
      fixture.invoke(
        execute_provider_attempt=lambda *args:failed,
        complete_accepted=lambda result:completion_calls.append(result),
        publish_failure_handoff=lambda result:None)
    self.assertEqual(completion_calls, [])


if __name__ == "__main__":
  unittest.main()
