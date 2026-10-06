# Workspace Readiness Projection

Status: authoritative semantic contract for deriving workspace eligibility from
the RWF issue graph.

This document defines the projection consumed by `rwf workspace ready` and by
workspace-creation eligibility checks.  It defines semantics only; storage and
command implementation are separate concerns.

## 1. Inputs and authority

Readiness is derived from canonical direct ticket dependencies and current
durable issue state.

For one candidate issue, the projection reads:

- the candidate's lifecycle/terminal state;
- its direct dependencies;
- the current state of each direct dependency.

Ticket title prefixes, Git branch parent/history, workspace existence, and
local claim state are not dependency edges.

The projection consumes normalized RWF ticket/state interfaces. It does not
parse ticket prose or infer relationships from Git history.

## 2. Ready

An open issue is ready when every direct leaf dependency is resolved.

An issue with no direct leaf dependencies is therefore ready.

Resolved means the canonical durable issue state says the dependency has
reached the workflow condition that satisfies its dependency edge.  The
projection does not substitute local workspace state for that durable fact.

## 3. Blocked

An open issue is blocked when at least one direct leaf dependency is unresolved.

The result must identify the unresolved direct blockers.  It must not replace
them with transitive ancestors or an umbrella that merely contains them.

For the same canonical graph and issue state, blocker output is deterministic.

## 4. Independent siblings

Two issues with no dependency path between them are independently ready.

A shared prerequisite blocks a consumer only when an explicit direct dependency edge from that consumer requires it.

## 5. Direct edges are authoritative

Scheduling uses direct dependency edges.

If A depends on B and B depends on C, A's direct blocker is B.  C explains why
B is blocked but does not become an inferred direct A -> C edge.

This preserves the graph as authored and prevents the readiness layer from
silently changing decomposition semantics.

## 6. Non-dependency relationships

The following never block readiness by themselves:

- child ownership by an umbrella;
- shared umbrella attachment;
- branch base;
- integration target;
- branch ancestry;
- another ready sibling having an active workspace.

These relationships remain queryable for their own purposes but are not
coerced into dependency ordering.

## 7. Workspace creation

`rwf workspace ready` reports issues eligible to begin work.

A normal start-capable workspace creation path uses this same projection before
starting issue work.

Provision-only behaviour is separate.  If a command explicitly supports
creating local workspace context before an issue is ready, it must not present
that issue as ready and must not perform canonical issue-start semantics.

## 8. Terminal candidates

A terminal issue is not returned as ready for new work.

Its terminal state can satisfy dependency edges from other issues according to
the canonical durable workflow-state contract.

Readiness therefore distinguishes durable lifecycle before dependency
eligibility:

- ready: lifecycle is `unstarted` or `aborted`, and all direct dependencies
  are resolved;
- blocked: lifecycle is `unstarted` or `aborted`, with one or more unresolved
  direct dependencies;
- active: lifecycle is `active`; work is already in progress and is not a new
  allocation candidate;
- accepted: lifecycle is `accepted`; task acceptance is complete but durable
  completion/integration has not occurred, so it is not a new allocation
  candidate;
- terminal: lifecycle is `completed`; it is not eligible for new work and its
  dependency edge is satisfied.

`aborted` is eligible for re-entry when its direct dependencies are resolved.
The durable lifecycle state does not recreate or imply a local worker claim.

## 9. Determinism and diagnostics

For identical canonical relationship and issue-state inputs, the projection
returns identical classifications and blocker identities.

A non-ready result must be actionable:

- blocked results identify unresolved direct dependency issue numbers;
- active results identify that durable work is already in progress;
- accepted results identify that the issue awaits durable completion rather
  than new work;
- terminal results identify the terminal state;
- unavailable canonical state is an explicit error, not an assumed ready
  result.

Lifecycle classification precedes dependency classification.  An `active`,
`accepted`, or `completed` issue is not reported as dependency-blocked merely
because its graph still contains an unresolved edge.  Such a contradiction is a
workflow-state diagnostic for the owning transition rather than an invitation
to allocate the issue again.

The projection fails closed when required authoritative state cannot be read.

## 10. Required semantic tests

Implementation must prove at least:

1. an open leaf with no dependencies is ready;
2. an open leaf with one unresolved direct dependency is blocked;
3. resolving that dependency makes the leaf ready;
4. independent siblings under one umbrella can both be ready;
5. shared umbrella attachment alone creates no blocker;
6. branch base and Git ancestry create no blocker;
7. transitive dependencies are not rewritten as direct edges;
8. blocker output contains the exact unresolved direct dependencies;
9. `active` and `accepted` issues are not returned as ready;
10. an `aborted` issue with resolved dependencies is eligible for re-entry;
11. a `completed` issue is terminal, not ready, and satisfies dependency
    edges;
12. lifecycle classification is not replaced by clone-local claim state;
13. missing authoritative relationship/state input fails explicitly.

The implementation owned by #144 must preserve this contract rather than
embedding provider-specific scheduling rules.
