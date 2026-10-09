# Workspace Readiness Projection

Status: authoritative semantic contract for deriving workspace eligibility from
the RWF ticket dependency graph.

## 1. Inputs and authority

Readiness is derived from canonical direct ticket dependencies and current
durable issue lifecycle state.

For one candidate issue, the projection reads:

- the candidate lifecycle state;
- its direct dependencies;
- the current lifecycle state of each direct dependency.

Ticket title prefixes, ticket-body grouping, Git branch parent/history,
workspace existence, and local claim state are not dependency edges.

The projection consumes normalized RWF ticket/state interfaces. It does not
parse ticket prose or infer relationships from Git history.

## 2. Ready

An issue is ready when its lifecycle permits entry and every direct dependency
is satisfied.

An issue with no direct dependencies is therefore ready when its lifecycle
permits entry.

Dependency satisfaction comes from canonical durable lifecycle state. Local
workspace state cannot substitute for that durable fact.

## 3. Blocked

An issue is blocked when its lifecycle permits entry but at least one direct
dependency is unresolved.

The result identifies the exact unresolved direct dependencies. It does not
replace them with transitive prerequisites or descriptive container tickets.

For the same canonical ticket graph and lifecycle state, blocker output is
deterministic.

## 4. Independent work

Two issues with no dependency path between them are independently ready when
their own direct dependencies are satisfied.

A shared prerequisite affects a consumer only through an explicit direct
dependency edge from that consumer.

## 5. Direct edges are authoritative

Scheduling uses direct dependency edges.

If A depends on B and B depends on C, A's direct blocker is B. C explains why
B is blocked but does not become an inferred direct A -> C edge.

The readiness layer never changes decomposition semantics by manufacturing
additional dependencies.

## 6. Non-dependency facts

The following never block readiness by themselves:

- descriptive ticket title prefixes;
- ticket-body grouping prose;
- Git branch parent or ancestry;
- another ready issue having an active workspace.

These facts are not coerced into dependency ordering.

## 7. Workspace creation

`rwf workspace ready` reports issues eligible to begin work.

A normal start-capable workspace creation path uses this same projection before
starting issue work.

If a command explicitly supports provisioning local context before an issue is
ready, it must not present that issue as ready and must not perform canonical
issue-start semantics.

## 8. Lifecycle classification

Lifecycle classification precedes dependency classification:

- `ready`: lifecycle is `not_started` or `aborted`, and all direct
  dependencies are satisfied;
- `blocked`: lifecycle is `not_started` or `aborted`, with one or more
  unresolved direct dependencies;
- `active`: work is already in progress and is not a new allocation
  candidate;
- `accepted`: task acceptance is complete but durable completion/integration
  has not occurred, so it is not a new allocation candidate;
- `terminal`: lifecycle is `completed`; it is not eligible for new work and
  its dependency edge is satisfied.

An aborted issue is eligible for re-entry when its direct dependencies are
satisfied.

A local worker claim is not reconstructed from durable lifecycle state.

## 9. Determinism and diagnostics

For identical canonical ticket and lifecycle inputs, the projection returns
identical classifications and blocker identities.

A non-ready result must be actionable:

- blocked results identify unresolved direct dependency issue numbers;
- active results identify that durable work is already in progress;
- accepted results identify that the issue awaits durable completion rather
  than new work;
- terminal results identify the terminal state;
- unavailable canonical state is an explicit error, not an assumed ready
  result.

An active, accepted, or completed issue is not reported as dependency-blocked
merely because contradictory dependency state exists. Such a contradiction is
a workflow-state diagnostic rather than an invitation to allocate the issue
again.

The projection fails closed when required authoritative state cannot be read.

## 10. Required semantic tests

Implementation must prove at least:

1. an not_started issue with no dependencies is ready;
2. one unresolved direct dependency makes it blocked;
3. resolving that dependency makes it ready;
4. independent issues with no dependency path can both be ready;
5. descriptive title/grouping information alone creates no blocker;
6. Git branch parent and ancestry create no blocker;
7. transitive dependencies are not rewritten as direct edges;
8. blocker output contains exact unresolved direct dependencies;
9. active and accepted issues are not returned as ready;
10. an aborted issue with satisfied dependencies is eligible for re-entry;
11. a completed issue is terminal and satisfies dependency edges;
12. unavailable or malformed canonical state fails closed.

TEST_ADEQUACY.md applies.
