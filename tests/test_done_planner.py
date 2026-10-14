"""Independent #108 acceptance and denial cases; planner has no writes."""

from dataclasses import replace
import unittest

from repo_workflow.done_planner import (
  AuthorizationDecision, DoneSnapshot, GateObservation, plan_done,
)


SOURCE = "a" * 40
PARENT = "b" * 40
ADVANCED = "c" * 40


def gate(name, *, sha=SOURCE, parent=PARENT, passed=True, authenticated=True):
  return GateObservation(
    name, sha, parent, "PASS" if passed else "FAIL",
    authenticated, "provider:run-123",
  )


def authorization(**overrides):
  auth = AuthorizationDecision(
    decision="allow",
    authenticated=True,
    evidence_ref="trusted-grant:1",
    issue="108",
    candidate_sha=SOURCE,
    destination_ref="parent/56",
    expected_destination_sha=PARENT,
    release="patch",
    role="remote_finalizer",
    capability="pull_request.merge",
  )
  return replace(auth, **overrides)


def snapshot(**overrides):
  facts = DoneSnapshot(
    issue="108",
    release="patch",
    candidate_sha=SOURCE,
    version="1.0.0-issue.108",
    parent_branch="parent/56",
    recorded_parent_sha=PARENT,
    current_parent_sha=PARENT,
    lifecycle_state="accepted",
    relationship_revision=9,
    current_relationship_revision=9,
    source_branch="issue-108",
    source_tip_sha=SOURCE,
    validation=tuple(gate(name) for name in ("regression", "integration", "release")),
    authorization=authorization(),
    dependencies_complete=True,
    mit="not-required",
    mit_policy_verified=True,
  )
  return replace(facts, **overrides)


class DonePlannerAcceptance(unittest.TestCase):
  def test_readiness_has_explicit_parent_and_release(self):
    for release in ("patch", "minor", "major"):
      plan = plan_done(snapshot(release=release, authorization=authorization(release=release)))
      self.assertEqual(plan.disposition, "ALLOWED")
      self.assertTrue(plan.allowed)
      self.assertEqual(plan.target, "parent/56")
      self.assertEqual(plan.release, release)
      self.assertFalse(plan.queue_eligible)
      self.assertEqual(plan.expected_parent_sha, PARENT)
      self.assertIn("submit-to-109-executor", plan.next_transitions)

  def test_no_implicit_parent_from_source_or_git_ancestry(self):
    plan = plan_done(snapshot(parent_branch=None))
    self.assertEqual(plan.disposition, "BLOCKED")
    self.assertIn("explicit-parent-relationship", plan.missing_gates)
    self.assertIsNone(plan.target)

  def test_denies_each_required_gate_independently(self):
    for name in ("regression", "integration", "release"):
      with self.subTest(name=name):
        obs = tuple(gate(n, passed=n != name) for n in (
          "regression", "integration", "release"
        ))
        result = plan_done(snapshot(validation=obs))
        self.assertFalse(result.allowed)
        self.assertIn(f"{name}-exact-current-PASS", result.missing_gates)

  def test_missing_and_duplicate_evidence_denied(self):
    for obs in ((), (gate("regression"),), (
      gate("regression"), gate("regression"), gate("integration"), gate("release"),
    )):
      self.assertFalse(plan_done(snapshot(validation=obs)).allowed)

  def test_stale_or_unauthenticated_validation_denied(self):
    for bad in (
      gate("integration", sha=ADVANCED),
      gate("integration", parent=ADVANCED),
      gate("integration", authenticated=False),
    ):
      obs = (gate("regression"), bad, gate("release"))
      self.assertIn("integration-exact-current-PASS", plan_done(
        snapshot(validation=obs)
      ).missing_gates)

  def test_stale_authorization_denied(self):
    for invalid in (
      None, authorization(candidate_sha=ADVANCED),
      authorization(expected_destination_sha=ADVANCED),
      authorization(authenticated=False),
      authorization(role="security_administrator"),
      authorization(release="minor"),
      authorization(decision="deny"),
    ):
      self.assertIn("current-authorization", plan_done(
        snapshot(authorization=invalid)
      ).missing_gates)

  def test_changed_source_does_not_inherit_green(self):
    p = plan_done(snapshot(source_tip_sha=ADVANCED))
    self.assertEqual(p.disposition, "BLOCKED")
    self.assertIn("changed-source-tip", p.missing_gates)

  def test_parent_tip_race_requires_revalidation(self):
    p = plan_done(snapshot(current_parent_sha=ADVANCED))
    self.assertEqual(p.disposition, "STALE_BASE")
    self.assertFalse(p.allowed)
    self.assertFalse(p.queue_eligible)
    self.assertIn("stale-parent-tip", p.missing_gates)

  def test_no_inferred_lifecycle_or_dependencies(self):
    for changed in (
      {"lifecycle_state": "active"},
      {"lifecycle_state": "in_review"},
      {"dependencies_complete": False},
      {"current_relationship_revision": 10},
    ):
      self.assertFalse(plan_done(snapshot(**changed)).allowed)

  def test_contenders_on_same_parent_enter_ephemeral_queue_only_if_authorized(self):
    for count in (0, 1):
      plan = plan_done(snapshot(contenders=count, coordination_authority=True))
      self.assertFalse(plan.queue_eligible)
      self.assertEqual(plan.disposition, "ALLOWED")
    for count in (2, 3, 8):
      plan = plan_done(snapshot(contenders=count, coordination_authority=True))
      self.assertEqual(plan.disposition, "QUEUE_ELIGIBLE")
      self.assertTrue(plan.queue_eligible)
      self.assertEqual(plan.queue_track, "runnable")

  def test_competing_destination_does_not_count_as_same_parent(self):
    other = plan_done(snapshot(parent_branch="umbrella/56", contenders=1))
    self.assertFalse(other.queue_eligible)
    self.assertEqual(other.target, "umbrella/56")

  def test_no_queue_authority_fails_closed(self):
    plan = plan_done(snapshot(contenders=2))
    self.assertFalse(plan.queue_eligible)
    self.assertIsNone(plan.queue_track)

  def test_mit_requires_pinned_tester_and_deadline(self):
    base = snapshot(mit="pending", mit_candidate_sha=SOURCE, contenders=2,
                    coordination_authority=True)
    missing = plan_done(base)
    self.assertFalse(missing.allowed)
    self.assertFalse(missing.queue_eligible)
    self.assertIn("mit-scheduling-obligation", missing.missing_gates)
    ready = plan_done(replace(
      base, mit_tester="tester-9", mit_deadline="2026-10-15T15:00:00Z",
      mit_schedule_authorized=True
    ))
    self.assertEqual(ready.disposition, "MIT_REQUIRED")
    self.assertFalse(ready.allowed)
    self.assertTrue(ready.queue_eligible)
    self.assertEqual(ready.queue_track, "manual-scheduling")

  def test_mit_pass_not_reused_for_changed_source(self):
    p = plan_done(snapshot(mit="passed", mit_candidate_sha=ADVANCED))
    self.assertFalse(p.allowed)
    self.assertIn("stale-mit-PASS", p.missing_gates)

  def test_timeout_distinct_from_tester_failure(self):
    p = plan_done(snapshot(mit="timeout", mit_candidate_sha=SOURCE))
    self.assertEqual(p.disposition, "DEFERRED_MIT")
    self.assertEqual(p.queue_track, "deferred-mit")
    self.assertFalse(p.allowed)
    self.assertFalse(p.queue_eligible)
    self.assertNotIn("mit-reported-FAIL", p.missing_gates)
    failure = plan_done(snapshot(mit="failed", mit_candidate_sha=SOURCE))
    self.assertEqual(failure.disposition, "BLOCKED")
    self.assertIn("mit-reported-FAIL", failure.missing_gates)

  def test_failed_mit_does_not_hold_other_queue_candidates(self):
    failed = plan_done(snapshot(mit="failed", contenders=3,
                                coordination_authority=True))
    other = plan_done(snapshot(contenders=2, coordination_authority=True))
    self.assertFalse(failed.queue_eligible)
    self.assertTrue(other.queue_eligible)

  def test_stale_mit_timeout_retains_identified_obligation(self):
    p = plan_done(snapshot(mit="timeout", mit_candidate_sha=ADVANCED))
    self.assertFalse(p.allowed)
    self.assertIn("stale-mit-candidate", p.missing_gates)
    self.assertIn("retain-deferred-mit-request", p.next_transitions)

  def test_two_actors_using_same_parent_tip_need_executor_cas(self):
    original = snapshot(contenders=2, coordination_authority=True)
    self.assertEqual(plan_done(original), plan_done(original))
    after_first = replace(original, current_parent_sha=ADVANCED)
    losing_plan = plan_done(after_first)
    self.assertEqual(losing_plan.disposition, "STALE_BASE")
    self.assertFalse(losing_plan.queue_eligible)

  def test_invalid_inputs_rejected(self):
    for invalid in (
      {"release": "stable"}, {"issue": "0"}, {"mit": "success"},
      {"contenders": -1}, {"contenders": True},
    ):
      with self.assertRaises(ValueError):
        plan_done(snapshot(**invalid))

  def test_unverified_mit_applicability_denies_integration(self):
    p = plan_done(snapshot(mit_policy_verified=False))
    self.assertFalse(p.allowed)
    self.assertIn("verified-mit-applicability", p.missing_gates)

  def test_mit_pass_requires_authenticated_test_result(self):
    pending = plan_done(snapshot(mit="passed", mit_candidate_sha=SOURCE))
    self.assertFalse(pending.allowed)
    self.assertIn("unauthenticated-mit-PASS", pending.missing_gates)
    verified = plan_done(snapshot(
      mit="passed", mit_candidate_sha=SOURCE, mit_authenticated=True,
      mit_evidence_ref="manual-test:trusted:124",
    ))
    self.assertTrue(verified.allowed)

  def test_major_release_requires_matching_authorization_class(self):
    not_major = plan_done(snapshot(release="major"))
    self.assertFalse(not_major.allowed)
    self.assertIn("current-authorization", not_major.missing_gates)
    permitted = plan_done(snapshot(
      release="major", authorization=authorization(release="major"),
    ))
    self.assertTrue(permitted.allowed)

  def test_unauthorized_mit_scheduling_cannot_join_queue(self):
    p = plan_done(snapshot(
      mit="pending", mit_candidate_sha=SOURCE, mit_tester="tester-9",
      mit_deadline="2026-10-15T15:00:00Z", contenders=2,
      coordination_authority=True,
    ))
    self.assertFalse(p.queue_eligible)
    self.assertIn("mit-scheduling-obligation", p.missing_gates)

  def test_sha256_candidate_identity_is_supported_exactly(self):
    sha64 = "a" * 64
    base64 = "b" * 64
    gates = tuple(
      gate(name, sha=sha64, parent=base64)
      for name in ("regression", "integration", "release")
    )
    auth = authorization(candidate_sha=sha64, expected_destination_sha=base64)
    valid = snapshot(
      candidate_sha=sha64, source_tip_sha=sha64,
      recorded_parent_sha=base64, current_parent_sha=base64,
      validation=gates, authorization=auth,
    )
    self.assertTrue(plan_done(valid).allowed)
    invalid = replace(valid, source_tip_sha=SOURCE)
    self.assertFalse(plan_done(invalid).allowed)

  def test_invalid_explicit_parent_is_never_inferred(self):
    for value in ("../main", "refs/heads/main", "a//b", "issue-108"):
      p = plan_done(snapshot(parent_branch=value))
      self.assertFalse(p.allowed)
      self.assertIn("explicit-parent-relationship", p.missing_gates)

  def test_invalid_mit_deadline_is_not_schedule_ready(self):
    base = snapshot(
      mit="pending", mit_candidate_sha=SOURCE, mit_tester="tester-9",
      mit_schedule_authorized=True, contenders=2,
      coordination_authority=True,
    )
    for value in ("tomorrow", "2026-13-15T15:00:00Z",
                  "2026-10-15T15:00:00", ""):
      p = plan_done(replace(base, mit_deadline=value))
      self.assertIn("mit-scheduling-obligation", p.missing_gates)
      self.assertFalse(p.queue_eligible)

  def test_invalid_boolean_or_revision_cannot_grant_completion(self):
    for changes in (
      {"dependencies_complete": 1},
      {"current_relationship_revision": True, "relationship_revision": 1},
      {"mit_policy_verified": 1},
    ):
      self.assertFalse(plan_done(snapshot(**changes)).allowed)

  def test_pure_projection_does_not_mutate_inputs(self):
    old = snapshot(contenders=3, coordination_authority=True)
    before = repr(old)
    p1, p2 = plan_done(old), plan_done(old)
    self.assertEqual(repr(old), before)
    self.assertEqual(p1, p2)
    self.assertEqual(p1.to_json_value()["target"], "parent/56")


if __name__ == "__main__":
  unittest.main()
