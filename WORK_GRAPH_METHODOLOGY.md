# Work Graph Methodology

Status: authoritative repository-neutral methodology for decomposing and
structuring work in RepoWorkflow-managed repositories.

This document defines how to turn a set of issues into a testable, schedulable
work graph.  It is intentionally independent of RepoWorkflow's own backlog.
The same rules apply to product repositories, libraries, infrastructure,
documentation projects, and other repositories that use RWF.

## 1. Purpose

Issue decomposition is not merely project-management cleanup.  A well-formed
issue graph is a high-level architecture model.

Good decomposition should make it possible to answer, mechanically:

- what outcome each human-facing container represents;
- what exact interface or transition each leaf owns;
- what must be true before a leaf starts;
- what must be true after it succeeds;
- what invariants may never be violated;
- what failure or rollback means;
- what exact prerequisite blocks a leaf;
- what work is ready now;
- what work may proceed in parallel;
- what reusable subsystem owns cross-cutting capabilities.

The graph should expose architecture problems before production code is
written.

Cross-repository managers can consume the same model.  WorkStack
(https://github.com/Ma-XX-oN/WorkStack) coordinates multiple repositories;
this remains the source for repository-neutral decomposition and graph semantics.

## 2. Decompose by contract boundary, not task size

"Too large" is not the primary test for whether an issue should be split.

A leaf is well-formed when it owns one coherent contract or state transition
with a clear completion boundary.

A leaf may contain substantial implementation work and still be valid if its
interface remains singular.  A small issue may still be poorly decomposed when
it mixes several independently testable responsibilities.

Useful split boundaries include:

- semantic contract versus implementation;
- dispatcher/invocation layer versus provider implementation;
- provider-neutral semantics versus provider-specific mechanics;
- read-only resolution versus mutating execution;
- planning versus execution;
- persistence versus domain behaviour;
- state ownership versus concurrency behaviour;
- concurrency behaviour versus recovery/reconstruction;
- presentation/rendering versus semantic projection;
- candidate preparation versus result finalization;
- creation versus later cleanup/reconciliation.

When two responsibilities have different preconditions, postconditions,
failure behaviour, or independent consumers, they are strong candidates for
separate leaves.

## 3. The leaf contract

Each implementation leaf should normally be expressible using the following
shape:

```text
Interface
  What operation, contract, transition, or artifact does this leaf own?

Preconditions
  What must already be true before it may run?

Postconditions
  What new facts are true after successful completion?

Invariants
  What must remain true before, during, and after the operation?

Failure / rollback
  What happens if the operation cannot complete?

Direct blockers
  Which exact prerequisite interfaces must already exist?
```

Not every issue body needs these exact headings, but the information should be
unambiguous.

### 3.1 Preconditions

Preconditions should name authoritative facts or interfaces, not vague project
states.

Prefer:

```text
The state-store write primitive is available.
The exact candidate evidence record exists.
The provider adapter contract is frozen.
```

Avoid:

```text
The backend stuff is mostly done.
The workflow is ready.
Dependencies are handled.
```

### 3.2 Postconditions

A postcondition describes observable completion, not implementation activity.

Prefer:

```text
A normalized result is returned.
The exact candidate has one immutable terminal identity.
The local current-work record points to issue N.
```

Avoid:

```text
Code has been written.
Tests have been added.
The helper was refactored.
```

### 3.3 Invariants

Invariants define the safety envelope.

Examples:

- a read-only operation never mutates workflow state;
- a provider adapter never changes semantic PASS/FAIL meaning;
- a changed candidate never inherits GREEN evidence;
- clone-local state never becomes authoritative shared state;
- a failed transactional mutation leaves the prior authoritative state intact;
- branch ancestry never creates a semantic dependency implicitly.

Strong invariants make RED tests straightforward.

### 3.4 Failure and rollback

Mutation leaves should define what partial failure means.

A workflow that can leave half-created state without a specified recovery
contract is not fully decomposed.

Transactional operations should normally state one of:

- failure leaves no mutation;
- failure leaves an explicit recoverable intermediate state;
- failure records an immutable unsuccessful attempt and stops.

## 4. Dependency analysis is a decomposition tool

Dependencies should be explicit and direct.

If issue B cannot proceed until issue A produces a required result, B directly
depends on A.

Do not store "indirect dependency" as a relationship type.  If ordering can
only be explained indirectly, inspect the decomposition.

For example:

```text
A needs something from B, which sort of comes through C.
```

often indicates one of:

- the required interface should be extracted;
- a shared prerequisite is missing;
- one issue combines contract and implementation;
- one container is incorrectly treated as owning reusable infrastructure.

A useful rule is:

> If explaining one dependency requires a paragraph, look for a missing
> interface boundary.

## 5. Human-facing containers and executable dependencies

RepoWorkflow stores one executable graph relationship: the direct ticket
dependency.

Ticket titles may use descriptive container prefixes:

```text
Initiative: ...
Epic: ...
Feature: ...
```

These prefixes help humans navigate and review decomposition. They do not create
ownership, membership, readiness, or ordering semantics.

Corrective and structural work may instead use:

```text
Bug: ...
Refactor: ...
```

Those are also descriptive classifications only and do not change graph
traversal or dependency semantics.

An ordinary implementation/certification ticket normally has no such prefix.

### 5.1 Direct dependency

A ticket depends on another ticket only when it requires that ticket's exact
result before it can proceed.

```text
S1 -> S2 -> A2
```

Direct dependencies are authoritative for executable readiness.

### 5.2 Container decomposition

An Initiative, Epic, or Feature may describe a larger outcome implemented by
several tickets. The provider issue body may list or explain that decomposition,
but RWF does not persist a second container relationship graph.

Scheduling still comes only from explicit direct dependencies among the actual
tickets.

## 5.3 Ticket-creation dependency requirement

Updating the canonical dependency graph is a required part of ticket creation
and decomposition, not optional follow-up bookkeeping.

When creating a ticket, splitting an existing task, or discovering a new direct
prerequisite while working a task:

- record the new ticket in `.repoworkflow/tickets.csv` immediately;
- record every known direct dependency immediately;
- if the ticket belongs to a larger decomposed outcome, preserve a real
  executable dependency path back to that outcome through the appropriate
  prerequisite and convergence/certification tickets;
- do not continue dependent implementation while the new ticket or known
  dependency is absent from the canonical graph;
- do not invent dependency edges solely to encode container membership;
- validate and read back the committed graph before treating ticket creation or
  decomposition as complete.

This requirement exists so dependency traversal can reconstruct how work
expanded into prerequisite rabbit holes without relying on chat history or
human memory.

Before treating decomposition/ticket creation as complete, reconcile the
agreed capability list against the provider tickets that were actually created:

- every explicitly agreed implementation/certification capability must map to a
  created ticket or an explicitly documented deferred item;
- compare the final created-ticket set back to the agreed decomposition rather
  than assuming sequential ticket creation was complete;
- a capability discussed only in chat/specification notes is not safely
  retained until it has a durable ticket/work-graph representation;
- if a planned ticket is intentionally omitted, record that decision and why;
- do not begin dependent implementation while an agreed, non-deferred
  capability is missing from the provider/canonical work graph.

This reconciliation closes the gap where a capability can be specified,
announced as a planned ticket, and then disappear because the ticket itself was
never created.

[TICKET_STATE.md](TICKET_STATE.md) owns the concrete synchronized-ticket
creation, commit, validation, and readback procedure that implements this
requirement.

## 6. Keep dependencies direct

Do not duplicate transitive prerequisites.

If:

```text
A -> B -> C
```

already expresses the ordering, do not also store:

```text
A -> C
```

unless A independently requires C's interface.

This keeps the graph minimal while preserving exact executable constraints.

## 7. Shared prerequisite consolidation

A shared prerequisite remains an ordinary dependency target.

When several related tickets form a reusable subsystem, a human-facing
`Feature:` or `Epic:` ticket may document that subsystem. Consumers still
depend directly only on the concrete tickets whose outputs they require.

This prevents duplicate implementations and unnecessary serialization without
introducing a second machine-readable ownership graph.

## 8. Separate contract, dispatcher, and provider implementation

Provider boundaries are especially prone to poor decomposition.

Prefer:

```text
semantic contract
   ├── dispatcher / invocation layer
   ├── provider A implementation
   └── provider B implementation
```

Once the contract is frozen, dispatcher and provider implementations may often
proceed in parallel.

The portable contract must not leak provider-specific payloads, names, runner
labels, event structures, or authentication mechanics.

## 9. Separate presentation from semantics

Human-facing commands should consume semantic interfaces rather than own them.

Prefer:

```text
canonical semantic projection
   ├── status renderer
   ├── what-next renderer
   └── completion guidance
```

or:

```text
repository-information contract
   ├── issue-info presentation
   └── issue-start validation
```

This prevents presentation work from becoming an unnecessary blocker for other
semantic consumers.

## 10. Separate planning from mutation

Complex mutating commands often benefit from a read-only planner.

Prefer:

```text
state -> readiness / plan
              |
              v
       validated executor
```

The planner should be deterministic and read-only.

The executor should revalidate that the plan still refers to the same exact
candidate/state before mutation.

This makes safety tests much simpler and prevents stale plans from executing.

## 11. Separate shared state from local context

Multi-agent repositories must distinguish durable workflow facts from
clone/agent-local navigation or current-work context.

Examples of durable/shared facts:

- explicit issue relationships;
- validation evidence;
- accepted/rejected candidate records;
- authorization records;
- integration-attempt identities.

Examples of clone/agent-local facts:

- current issue being viewed/worked;
- navigation history;
- shell/completion cache;
- local transient convenience state.

There must not be one globally authoritative mutable "active issue" when
multiple agents may work concurrently.

A useful state-design progression is:

```text
relationship schema
      |
      v
durable/local ownership
      |
      v
concurrency / writer identity
      |
      v
recovery / stale-state reconstruction
      |
      v
generic state-store primitives
      |
      v
domain records
```

Each stage has independently testable invariants.

## 12. Cleanup is part of completion

Required cleanup or reconciliation is not an optional epilogue.

If an operation creates temporary state whose retirement is required for the
workflow to be complete, model that retirement explicitly.

For example:

```text
construct
  -> validate
  -> publish/request
  -> integrate
  -> verify landed state
  -> cleanup/reconcile
```

A workflow is not complete merely because its primary action succeeded.

Terminal cleanup should have its own preconditions and invariants when it occurs
after intervening asynchronous or external work.

## 13. Derive scheduling from the graph

Do not maintain a separate manual work order when the dependency graph can
answer the question.

Definitions:

```text
ready
  no unresolved direct leaf dependencies

blocked
  one or more unresolved direct leaf dependencies

parallel-ready
  two or more ready leaves with no dependency path between them
```

Container tickets use the same direct-dependency readiness rule as every
other ticket.  A descriptive Initiative/Epic/Feature prefix does not create
separate container readiness, ownership, or child-blocking semantics.

## 13.1 Published lane display notation

Published lane naming, issue qualification, stability, and completion-display
rules are defined in [PUBLISHED_LANES.md](PUBLISHED_LANES.md).

## 13.2 Finish dependency-complete work before switching tasks

The dependency graph and group structure exist so workers finish one meaningful
outcome before beginning unrelated work.

A documentation, specification, test, or scaffolding substep is not a completed
task while its ticket still requires implementation, migration, verification,
or integration.

Follow direct prerequisites to completion, return to the blocked parent, and
finish that parent's remaining contract before switching tasks.  Container work
is complete only after its required dependency path converges through
certification/integration.

Other work may start only when the current outcome is complete, unless the graph
shows it is genuinely parallel-ready and parallel execution will not fragment or
delay the active outcome.

A prerequisite may finish independently when it produces a real reusable
interface.  Preparatory/reference work that knowingly leaves its own ticket
contract unimplemented is not independently complete.


Continuation: [Sections 14–15](WORK_GRAPH_METHODOLOGY_CONTINUED.md).
