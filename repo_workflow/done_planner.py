"""Pure, read-only plan for a canonical parent-directed done request.

Inputs must be observations from the existing lifecycle, relationship,
validation, authorization and provider adapters; this module does not confer
trust on asserted observations or perform the #109 executor's mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASES = frozenset({"patch", "minor", "major"})
GATE_NAMES = ("regression", "integration", "release")
MIT_STATES = frozenset({"not-required", "pending", "passed", "failed", "timeout"})


@dataclass(frozen=True)
class GateObservation:
  name: str
  candidate_sha: str
  parent_sha: str
  status: str
  authenticated: bool
  evidence_ref: str


@dataclass(frozen=True)
class AuthorizationDecision:
  decision: str
  authenticated: bool
  evidence_ref: str
  issue: str
  candidate_sha: str
  destination_ref: str
  expected_destination_sha: str
  release: str
  role: str
  capability: str


@dataclass(frozen=True)
class DoneSnapshot:
  issue: str
  release: str
  candidate_sha: str
  version: str
  parent_branch: str | None
  recorded_parent_sha: str
  current_parent_sha: str
  lifecycle_state: str
  relationship_revision: int | None
  current_relationship_revision: int | None
  source_branch: str
  source_tip_sha: str
  validation: tuple[GateObservation, ...]
  authorization: AuthorizationDecision | None
  dependencies_complete: bool
  mit: str
  mit_tester: str | None = None
  mit_deadline: str | None = None
  mit_candidate_sha: str | None = None
  mit_policy_verified: bool = False
  mit_authenticated: bool = False
  mit_evidence_ref: str | None = None
  mit_schedule_authorized: bool = False
  contenders: int = 1
  coordination_authority: bool = False


@dataclass(frozen=True)
class DonePlan:
  issue: str
  release: str
  target: str | None
  candidate_sha: str
  expected_parent_sha: str
  disposition: str
  allowed: bool
  queue_eligible: bool
  queue_track: str | None
  missing_gates: tuple[str, ...]
  next_transitions: tuple[str, ...]

  def to_json_value(self) -> dict:
    return {
      "issue": self.issue,
      "release": self.release,
      "target": self.target,
      "candidate_sha": self.candidate_sha,
      "expected_parent_sha": self.expected_parent_sha,
      "disposition": self.disposition,
      "allowed": self.allowed,
      "queue_eligible": self.queue_eligible,
      "queue_track": self.queue_track,
      "missing_gates": list(self.missing_gates),
      "next_transitions": list(self.next_transitions),
    }


def _valid_sha(value: str) -> bool:
  return isinstance(value, str) and SHA.fullmatch(value) is not None


def _gate_matches(
  gate: GateObservation | None, name: str, facts: DoneSnapshot,
) -> bool:
  return (
    isinstance(gate, GateObservation)
    and gate.name == name
    and gate.status == "PASS"
    and gate.authenticated is True
    and isinstance(gate.evidence_ref, str)
    and bool(gate.evidence_ref.strip())
    and gate.candidate_sha == facts.candidate_sha
    and gate.parent_sha == facts.current_parent_sha
  )


def _authorization_matches(
  auth: AuthorizationDecision | None, facts: DoneSnapshot,
) -> bool:
  return (
    isinstance(auth, AuthorizationDecision)
    and auth.decision == "allow"
    and auth.authenticated is True
    and isinstance(auth.evidence_ref, str)
    and bool(auth.evidence_ref.strip())
    and auth.issue == str(facts.issue)
    and auth.candidate_sha == facts.candidate_sha
    and auth.destination_ref == facts.parent_branch
    and auth.expected_destination_sha == facts.current_parent_sha
    and auth.release == facts.release
    and auth.role == "remote_finalizer"
    and auth.capability == "pull_request.merge"
  )


def plan_done(facts: DoneSnapshot) -> DonePlan:
  """Project readiness only; all provider observations must be verified upstream.

  A returned allowed plan is not a merge permit. The #109 executor must
  reauthenticate the exact source, approvals and live destination using CAS.
  """
  if not isinstance(facts, DoneSnapshot):
    raise TypeError("facts must be a DoneSnapshot")
  if facts.release not in RELEASES:
    raise ValueError("release must be patch, minor or major")
  if not re.fullmatch(r"[1-9][0-9]*", str(facts.issue)):
    raise ValueError("invalid issue number")
  if not isinstance(facts.version, str) or not facts.version.strip():
    raise ValueError("exact version is required")
  if not isinstance(facts.source_branch, str) or not facts.source_branch.strip():
    raise ValueError("source branch is required")
  if facts.mit not in MIT_STATES:
    raise ValueError("invalid MIT status")
  if isinstance(facts.contenders, bool) or not isinstance(facts.contenders, int) or facts.contenders < 0:
    raise ValueError("invalid contender count")

  missing: list[str] = []
  next_steps: list[str] = []

  def block(reason: str, step: str) -> None:
    missing.append(reason)
    if step not in next_steps:
      next_steps.append(step)

  target = facts.parent_branch
  if not isinstance(target, str) or not target or target.startswith("refs/"):
    block("explicit-parent-relationship", "register-parent-relationship")
    target = None
  if not _valid_sha(facts.candidate_sha) or not _valid_sha(facts.source_tip_sha):
    block("exact-candidate", "resolve-candidate")
  elif facts.candidate_sha != facts.source_tip_sha:
    block("changed-source-tip", "recertify-source")
  if not _valid_sha(facts.recorded_parent_sha) or not _valid_sha(facts.current_parent_sha):
    block("authoritative-parent-tip", "refresh-parent-tip")
  if facts.lifecycle_state != "accepted":
    block("accepted-lifecycle", "complete-review-and-accept")
  if (
    isinstance(facts.relationship_revision, bool)
    or not isinstance(facts.relationship_revision, int)
    or facts.relationship_revision < 0
    or facts.relationship_revision != facts.current_relationship_revision
  ):
    block("current-relationship-revision", "refresh-relationships")
  if not facts.dependencies_complete:
    block("completed-dependencies", "complete-dependencies")

  observed = {name: [] for name in GATE_NAMES}
  for gate in facts.validation:
    if isinstance(gate, GateObservation) and gate.name in observed:
      observed[gate.name].append(gate)
  for name in GATE_NAMES:
    if len(observed[name]) != 1 or not _gate_matches(observed[name][0], name, facts):
      block(f"{name}-exact-current-PASS", f"validate-{name}")
  if not _authorization_matches(facts.authorization, facts):
    block("current-authorization", "obtain-authorization")

  stale = (
    _valid_sha(facts.recorded_parent_sha)
    and _valid_sha(facts.current_parent_sha)
    and facts.recorded_parent_sha != facts.current_parent_sha
  )
  if stale:
    block("stale-parent-tip", "rebuild-and-revalidate-on-current-parent")

  if facts.mit_policy_verified is not True:
    block("verified-mit-applicability", "resolve-mit-policy")
  if facts.mit == "failed":
    block("mit-reported-FAIL", "handoff-manual-test-repair")
  elif facts.mit == "timeout":
    if facts.mit_candidate_sha != facts.candidate_sha:
      block("stale-mit-candidate", "reschedule-mit-current-candidate")
    next_steps.append("retain-deferred-mit-request")
  elif facts.mit == "pending":
    if facts.mit_candidate_sha != facts.candidate_sha:
      block("unpinned-mit-candidate", "pin-mit-candidate")
    if (not facts.mit_tester or not facts.mit_deadline
        or facts.mit_schedule_authorized is not True):
      block("mit-scheduling-obligation", "schedule-mit-with-authorized-deadline")
    next_steps.append("await-manual-tester-result")
  elif facts.mit == "passed":
    if facts.mit_candidate_sha != facts.candidate_sha:
      block("stale-mit-PASS", "rerun-mit-for-current-candidate")
    if (facts.mit_authenticated is not True
        or not isinstance(facts.mit_evidence_ref, str)
        or not facts.mit_evidence_ref.strip()):
      block("unauthenticated-mit-PASS", "verify-manual-test-result")

  if facts.contenders >= 2 and facts.coordination_authority is not True:
    block("queue-coordination-authority", "obtain-queue-coordinator")

  hard_blocks = tuple(x for x in missing if x not in {"mit-scheduling-obligation"})
  if stale:
    disposition = "STALE_BASE"
  elif missing:
    disposition = "BLOCKED"
  elif facts.mit == "pending":
    disposition = "MIT_REQUIRED"
  elif facts.mit == "timeout":
    disposition = "DEFERRED_MIT"
  elif facts.contenders >= 2:
    disposition = "QUEUE_ELIGIBLE"
  else:
    disposition = "ALLOWED"

  # An MIT timeout is never a passing integration, even with no other blocks.
  allowed = disposition in {"ALLOWED", "QUEUE_ELIGIBLE"}
  queue_eligible = (
    not hard_blocks and facts.contenders >= 2
    and facts.coordination_authority is True
    and facts.mit in {"not-required", "passed", "pending"}
  )
  queue_track = None
  if facts.mit == "timeout":
    queue_track = "deferred-mit"
  elif queue_eligible:
    queue_track = "manual-scheduling" if facts.mit == "pending" else "runnable"
  if allowed:
    next_steps.append("recheck-current-parent-and-source-at-acceptance")
    next_steps.append("submit-to-109-executor")
  elif queue_eligible:
    next_steps.append("coordinate-ephemeral-parent-queue")
  if facts.mit == "timeout":
    disposition = "DEFERRED_MIT" if not hard_blocks else disposition

  return DonePlan(
    issue=str(facts.issue),
    release=facts.release,
    target=target,
    candidate_sha=facts.candidate_sha,
    expected_parent_sha=facts.current_parent_sha,
    disposition=disposition,
    allowed=allowed and facts.mit in {"not-required", "passed"},
    queue_eligible=queue_eligible,
    queue_track=queue_track,
    missing_gates=tuple(missing),
    next_transitions=tuple(dict.fromkeys(next_steps)),
  )
