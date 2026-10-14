# Read-only done planner (#108)

Status: V3 candidate, not merged.  No mutating done executor is enabled.

## Boundary

`repo_workflow.done_planner.plan_done` computes a deterministic plan for
patch, minor or major release intent.  It does not create a queue, change a
ref, write workflow records, grant permissions, run tests, merge or tag.

`DoneSnapshot` is a typed envelope of *already verified observations*.
Its source must be the canonical existing workflow interfaces:

- #64/#117: clone-local current work and canonical lifecycle revision;
- #227/#230: explicit branch-to-parent identity, never ancestry inference;
- #145/#164: direct dependency and accepted lifecycle state;
- #69/#95/#104: exact-source and current-parent validation coverage;
- #80: trusted actor, issuer, capability, destination and release grant;
- #542: authoritative tip/readbacks and final remote acceptance CAS;
- MIT scheduling: authenticated policy and pinned human-test outcome.

A `GateObservation.authenticated=True` field is **not a signature**.
The source adapter must verify the backing evidence independently before
constructing a positive observation.  This module cannot prove provenance
of caller-supplied data.  An unverified caller must pass missing/false facts;
it must not claim provider authentication through a self-asserted Boolean.

The #104 implementation is currently in its own draft PR #622, and the #80
schema in PR #614.  This planner does not copy either module or create an
alternative lifecycle/provider store.  #109 must consume their authoritative
readers when assembling the command and must reject missing upstream proof.

## Semantics

`ALLOWED` indicates a read-time eligible, uncontended candidate.
`QUEUE_ELIGIBLE` indicates a contested candidate can be considered for the
ephemeral per-destination queue.  Neither means executable merge authority.
`STALE_BASE` requires rebuilding and fresh validation against the new tip.
`BLOCKED` includes missing/failed/unsigned evidence, stale authorization,
incomplete dependencies or lifecycle, and malformed relationship identity.
`MIT_REQUIRED` is a pinned, scheduled, unanswered human-test obligation.
`DEFERRED_MIT` represents TIMEOUT with **unknown outcome**, never PASS/FAIL.

An active queue requires two or more contenders for the *same destination*,
a separately authenticated coordination authority and an eligible request.
Unrelated destinations are never serialized by the planner.  The caller
supplies authoritative contention observations; a guessed count is not proof.
A timeout is recorded under `deferred-mit`, not a runnable merge queue.
An automated ART/AIT failure is handed back to its ticket's worker by the
executor; this planner does not dispatch agents or mutate the active queue.

Missing MIT scheduling policy, invalid deadline, absent tested SHA binding,
unverified MIT PASS or absent tester acknowledgement blocks advancement.
The caller must resolve configuration via accepted policy; no default
deadline, arbitrary timeout or local pseudo-approval is manufactured here.

## Executor boundary

#109 owns request creation, queue state/history, CAS coordination, fairness,
conflict attribution, tester scheduling, timeout transitions, worker handoff,
candidate integration, evidence promotion, verified readback and cleanup.
It must re-query **all** authoritative facts immediately before mutation.
A stale plan, stale main/parent tip or changed material source cannot execute,
even when content is textually mergeable.  No rollback is a normal CAS repair.

`rwf done patch|minor|major` mutation and CLI wiring remain #109's
responsibility.  The existing `rwf what-next` projection is unchanged.

## Verification

`tests.test_done_planner` is registered under
`issue-108-done-readiness` in the canonical .ci test catalogue.
Cases cover each release class, explicit target, source/base freshness,
stale/failed/duplicate evidence, scoped authorization and role separation,
immutable snapshots, concurrent candidates, zero/one/many contenders,
independent destinations, MIT-required, no-answer TIMEOUT, reported FAIL,
late/mismatched SHA, deadline/authority, and denial of unverified results.
Hosted testing must run on the exact final candidate, not only an earlier
commit or the disposable invocation-marker commit.
