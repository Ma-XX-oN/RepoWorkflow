"""Specification-based #110 evidence-aware provider planning acceptance."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.state_store import WriterIdentity
from repo_workflow.validation_coverage import Requirement
from repo_workflow.validation_import import ImportDecision
from repo_workflow.validation_plan import (
  ValidationPlanError, build_plan, dispatch_missing, execute_from_store,
  plan_from_store,
)
from repo_workflow.validation_store import (
  ValidationEvidenceStore, ValidationObservation, ValidationStoreError,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "a" * 40
OTHER = "b" * 40
FP = "c" * 64
CHANGED = "d" * 64


def requirement(unit="unit/a", fingerprint=FP, mode="automated"):
  return Requirement(unit, fingerprint, mode)


def observation(record_id="first", **overrides):
  values = dict(
    record_id=record_id, candidate_sha=CANDIDATE, version="0.1.1",
    branch="issue-110", unit="unit/a", fingerprint=FP, verdict="PASS",
    mode="automated", runner="python-3.13", platform="linux",
    provider_run="local/100",
  )
  values.update(overrides)
  return ValidationObservation(**values)


def envelope(candidate=CANDIDATE):
  return {
    "contract_version": 1, "operation": "execute",
    "invocation_id": "run-110",
    "candidate": {
      "repository": "owner/repo", "commit": candidate, "base": OTHER,
    },
    "requirements": {
      "stages": [], "capabilities": [], "artifacts": [],
    },
    "inputs": {"base": OTHER},
  }


def provider_observation(unit="unit/a", result="succeeded"):
  return {
    "stage": unit, "candidate": envelope()["candidate"],
    "complete": result != "unavailable", "outcome": result,
    "exit_code": 0 if result == "succeeded" else 1,
  }


class EvidenceAwarePlanTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.store = ValidationEvidenceStore(Path(self.temp.name))
    self.writer = WriterIdentity("agent", "session")

  def plan(self, requirements=None, candidate=CANDIDATE,
           trust=frozenset({"first"}), equivalents=frozenset()):
    return plan_from_store(
      self.store, [requirement()] if requirements is None else requirements,
      candidate, trusted_record_ids=trust,
      equivalent_candidate_shas=equivalents,
    )

  def test_zero_evidence_runs_each_required_automated_unit_once(self):
    requirements = [requirement("unit/z"), requirement("unit/a"),
                    requirement("unit/m")]
    result = self.plan(requirements=requirements, trust=frozenset())
    self.assertEqual(result.automated_units, ("unit/a", "unit/m", "unit/z"))
    self.assertFalse(result.complete)

  def test_reusable_durable_pass_suppresses_only_covered_unit(self):
    self.store.publish(observation(), self.writer)
    result = self.plan(requirements=[requirement("unit/b"), requirement()])
    self.assertEqual(result.automated_units, ("unit/b",))
    self.assertEqual(result.units[0].accepted_record_ids, ("first",))
    self.assertEqual(result.units[0].action, "reuse")

  def test_all_applicable_evidence_produces_no_automated_work(self):
    self.store.publish(observation(), self.writer)
    result = self.plan()
    self.assertTrue(result.complete)
    self.assertEqual(result.automated_units, ())
    with patch("repo_workflow.validation_plan.dispatch") as remote:
      actual = dispatch_missing(ROOT, result, envelope(), {})
    remote.assert_not_called()
    self.assertEqual(actual["reused"], ("unit/a",))
    self.assertEqual(actual["observations"], ())

  def test_untrusted_record_never_suppresses_execution(self):
    self.store.publish(observation(), self.writer)
    result = self.plan(trust=frozenset())
    self.assertEqual(result.automated_units, ("unit/a",))
    self.assertEqual(result.units[0].evidence_status, "unusable")

  def test_changed_candidate_and_fingerprint_never_suppress_without_proof(self):
    self.store.publish(observation(), self.writer)
    self.assertEqual(self.plan(candidate=OTHER).automated_units, ("unit/a",))
    proved = self.plan(candidate=OTHER, equivalents=frozenset({CANDIDATE}))
    self.assertTrue(proved.complete)
    changed = self.plan(
      candidate=OTHER, equivalents=frozenset({CANDIDATE}),
      requirements=[requirement(fingerprint=CHANGED)],
    )
    self.assertEqual(changed.automated_units, ("unit/a",))

  def test_nonpass_and_pending_never_suppress(self):
    for status in ("FAIL", "INCOMPLETE", "PENDING"):
      with self.subTest(status=status):
        with tempfile.TemporaryDirectory() as td:
          store = ValidationEvidenceStore(Path(td))
          store.publish(observation(verdict=status), self.writer)
          result = plan_from_store(
            store, [requirement()], CANDIDATE,
            trusted_record_ids=frozenset({"first"}),
            equivalent_candidate_shas=frozenset(),
          )
          self.assertEqual(result.automated_units, ("unit/a",))

  def test_manual_coverage_is_never_automated(self):
    manual = requirement(mode="manual")
    self.assertEqual(self.plan(requirements=[manual]).manual_units, ("unit/a",))
    self.store.publish(observation(), self.writer)
    plan = self.plan(requirements=[manual])
    self.assertEqual(plan.manual_units, ("unit/a",))
    self.assertEqual(plan.automated_units, ())
    self.assertFalse(plan.complete)
    with patch("repo_workflow.validation_plan.dispatch") as provider:
      result = dispatch_missing(ROOT, plan, envelope(), {})
    provider.assert_not_called()
    self.assertEqual(result["manual_pending"], ("unit/a",))

  def test_authenticated_manual_pass_reuses_without_executing(self):
    self.store.publish(observation(mode="manual"), self.writer)
    plan = self.plan(requirements=[requirement(mode="manual")])
    self.assertTrue(plan.complete)
    self.assertEqual(plan.automated_units, ())

  def test_store_tampering_fails_before_dispatch(self):
    self.store.publish(observation(), self.writer)
    p = Path(self.temp.name) / ".repoworkflow/validation/records/first.json"
    p.write_text(p.read_text().replace('"PASS"', '"FAIL"'), encoding="utf-8")
    with self.assertRaises(ValidationStoreError):
      self.plan()

  def test_missing_trust_proof_or_bad_target_fails_closed(self):
    self.store.publish(observation(), self.writer)
    with self.assertRaises(ValueError):
      self.plan(trust=None)
    with self.assertRaises(ValueError):
      self.plan(equivalents=None)
    with self.assertRaises(ValueError):
      self.plan(candidate="not-a-sha")

  def test_missing_duplicate_and_extra_import_decisions_are_rejected(self):
    decisions = (ImportDecision("unit/a", "missing", (), "no evidence"),)
    for required, imported in (
      ([requirement("unit/b")], decisions),
      ([requirement()], decisions + decisions),
      ([requirement(), requirement()], decisions),
    ):
      with self.subTest(required=required):
        with self.assertRaises(ValidationPlanError):
          build_plan(required, imported, CANDIDATE)

  def test_applicable_without_records_is_rejected(self):
    with self.assertRaises(ValidationPlanError):
      build_plan([requirement()], (
        ImportDecision("unit/a", "applicable", (), "unverified"),
      ), CANDIDATE)

  def test_only_missing_automated_groups_are_dispatched(self):
    self.store.publish(observation(), self.writer)
    plan = self.plan(requirements=[requirement(), requirement("unit/b")])
    outcome = {
      "status": "ok", "candidate": envelope()["candidate"],
      "observations": {"stages": [{
        "stage": "unit/b", "candidate": envelope()["candidate"],
        "complete": True, "outcome": "failed", "exit_code": 17,
      }]},
    }
    with patch("repo_workflow.validation_plan.dispatch", return_value=outcome) as remote:
      actual = dispatch_missing(
        ROOT, plan, envelope(), {"unit/b": "invariant-self-ci-contract"},
      )
    forwarded = remote.call_args.args
    import json
    payload = json.loads(forwarded[2])
    self.assertEqual(payload["requirements"]["stages"], ["unit/b"])
    self.assertEqual(payload["inputs"]["stage_groups"], {
      "unit/b": "invariant-self-ci-contract",
    })
    self.assertEqual(actual["executed"], ("unit/b",))
    self.assertEqual(actual["observations"][0]["outcome"], "failed")
    self.assertEqual(actual["reused"], ("unit/a",))

  def test_untrusted_group_or_candidate_is_rejected_before_provider(self):
    plan = self.plan()
    for groups, request_value in (
      ({"unit/a": "group", "unit/b": "extra"}, envelope()),
      ({}, envelope()),
      ({"unit/a": "group"}, envelope(OTHER)),
    ):
      with self.subTest(groups=groups), patch(
        "repo_workflow.validation_plan.dispatch"
      ) as remote:
        with self.assertRaises(ValidationPlanError):
          dispatch_missing(ROOT, plan, request_value, groups)
        remote.assert_not_called()

  def test_incomplete_or_conflicting_provider_observations_are_rejected(self):
    plan = self.plan()
    for stages in ([], [provider_observation("wrong")], [
      provider_observation(), provider_observation(),
    ], [{
      **provider_observation("unit/a", "unavailable"), "complete": True,
    }], [{
      **provider_observation("unit/a"), "candidate": envelope(OTHER)["candidate"],
    }]):
      with self.subTest(stages=stages):
        answer = {
          "status": "ok", "candidate": envelope()["candidate"],
          "observations": {"stages": stages},
        }
        with patch("repo_workflow.validation_plan.dispatch", return_value=answer):
          with self.assertRaises(ValidationPlanError):
            dispatch_missing(ROOT, plan, envelope(), {
              "unit/a": "invariant-self-ci-contract",
            })

  def test_genuine_provider_unavailable_is_not_translated_to_pass(self):
    plan = self.plan()
    answer = {
      "status": "ok", "candidate": envelope()["candidate"],
      "observations": {"stages": [provider_observation(
        result="unavailable",
      )]},
    }
    with patch("repo_workflow.validation_plan.dispatch", return_value=answer):
      observed = dispatch_missing(
        ROOT, plan, envelope(), {"unit/a": "invariant-self-ci-contract"},
      )
    self.assertEqual(observed["observations"][0]["outcome"], "unavailable")
    self.assertFalse(observed["observations"][0]["complete"])

  def test_plan_and_execute_refuses_untrusted_skips_without_dispatch(self):
    self.store.publish(observation(), self.writer)
    answer = {
      "status": "ok", "candidate": envelope()["candidate"],
      "observations": {"stages": [provider_observation()]},
    }
    with patch("repo_workflow.validation_plan.dispatch", return_value=answer) as provider:
      plan, execution = execute_from_store(
        ROOT, self.store, [requirement()], CANDIDATE, envelope(),
        {"unit/a": "invariant-self-ci-contract"},
        trusted_record_ids=frozenset(),
        equivalent_candidate_shas=frozenset(),
      )
      self.assertEqual(plan.automated_units, ("unit/a",))
      self.assertEqual(execution["executed"], ("unit/a",))
      self.assertEqual(provider.call_count, 1)

  def test_planner_exactly_skips_imported_units_in_one_execution(self):
    self.store.publish(observation(), self.writer)
    answer = {
      "status": "ok", "candidate": envelope()["candidate"],
      "observations": {"stages": [{
        "stage": "unit/b", "candidate": envelope()["candidate"],
        "complete": True, "outcome": "succeeded", "exit_code": 0,
      }]},
    }
    with patch("repo_workflow.validation_plan.dispatch", return_value=answer):
      plan, result = execute_from_store(
        ROOT, self.store, [requirement(), requirement("unit/b")],
        CANDIDATE, envelope(), {"unit/b": "invariant-self-ci-contract"},
        trusted_record_ids=frozenset({"first"}),
        equivalent_candidate_shas=frozenset(),
      )
    self.assertEqual(plan.automated_units, ("unit/b",))
    self.assertEqual(result["reused"], ("unit/a",))
    self.assertEqual(result["observations"][0]["stage"], "unit/b")

  def test_invalid_envelope_cannot_skip_when_evidence_complete(self):
    self.store.publish(observation(), self.writer)
    plan = self.plan()
    for replacement in (
      {"invocation_id": ""},
      {"contract_version": True},
      {"inputs": {"base": OTHER, "extra": "untrusted"}},
      {"requirements": {"stages": ["pretend-done"],
                        "capabilities": [], "artifacts": []}},
      {"candidate": {"repository": "", "commit": CANDIDATE, "base": OTHER}},
    ):
      with self.subTest(replacement=replacement):
        bad = {**envelope(), **replacement}
        with patch("repo_workflow.validation_plan.dispatch") as remote:
          with self.assertRaises(ValidationPlanError):
            dispatch_missing(ROOT, plan, bad, {})
          remote.assert_not_called()

  def test_real_configured_provider_executes_missing_stage(self):
    # This is provider-backed rather than a mock: the GitHub adapter runs the
    # selected immutable test-catalogue group from this checked-out HEAD.
    head = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=ROOT,
      capture_output=True, text=True, check=True,
    ).stdout.strip()
    plan = plan_from_store(
      self.store, [requirement()], head,
      trusted_record_ids=frozenset(),
      equivalent_candidate_shas=frozenset(),
    )
    request = envelope(head)
    response = dispatch_missing(
      ROOT, plan, request, {"unit/a": "invariant-self-ci-contract"},
    )
    self.assertEqual(response["executed"], ("unit/a",))
    self.assertEqual(response["observations"][0]["outcome"], "succeeded")
    self.assertTrue(response["observations"][0]["complete"])

  def test_provider_error_never_claims_success(self):
    plan = self.plan()
    with patch("repo_workflow.validation_plan.dispatch", return_value={
      "status": "error", "candidate": envelope()["candidate"],
      "observations": {},
    }):
      with self.assertRaises(ValidationPlanError):
        dispatch_missing(ROOT, plan, envelope(), {
          "unit/a": "invariant-self-ci-contract",
        })


if __name__ == "__main__":
  unittest.main()
