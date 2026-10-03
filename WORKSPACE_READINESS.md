# Workspace Readiness Projection

Status: authoritative semantic contract for deriving workspace eligibility from
the RWF issue graph.

This document defines the projection consumed by `rwf workspace ready` and by
workspace-creation eligibility checks.  It defines semantics only; storage and
command implementation are separate concerns.

## 1. Inputs and authority

Readiness is derived from canonical direct issue relationships and current
durable issue state.

For one candidate issue, the projection reads:

- the candidate's open/terminal state;
- its direct leaf dependencies;
- the current state of each direct dependency.

Umbrella membership, shared umbrella attachment, branch base, integration
target, Git ancestry, workspace existence, and local claim state are not
dependency edges.

The projection must consume normalized RWF relationship/state interfaces.  It
must not parse GitHub issue prose or infer relationships from Git history.

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

Two issues attached to the same umbrella remain independently ready when there
is no direct dependency path between them.

Umbrella membership is grouping, not ordering.

A shared prerequisite attached to multiple umbrellas blocks each consumer only
when an explicit direct dependency edge from that consumer requires it.

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

Readiness therefore distinguishes:

- ready: open and all direct dependencies resolved;
- blocked: open with unresolved direct dependencies;
- terminal: not eligible for new work.

## 9. Determinism and diagnostics

For identical canonical relationship and issue-state inputs, the projection
returns identical classifications and blocker identities.

A non-ready result must be actionable:

- blocked results identify unresolved direct dependency issue numbers;
- terminal results identify the terminal state;
- unavailable canonical state is an explicit error, not an assumed ready
  result.

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
9. a terminal issue is not returned as ready;
10. missing authoritative relationship/state input fails explicitly.

The implementation owned by #144 must preserve this contract rather than
embedding provider-specific scheduling rules.
