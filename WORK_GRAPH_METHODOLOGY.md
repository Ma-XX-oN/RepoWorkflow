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

- what outcome each umbrella represents;
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
- one umbrella incorrectly owns reusable infrastructure.

A useful rule is:

> If explaining one dependency requires a paragraph, look for a missing
> interface boundary.

## 5. Four graph relationships

RWF work graphs distinguish four relationships.

### 5.1 Child ownership

A child contributes to one umbrella outcome.

```text
Umbrella A
├── A1
├── A2
└── A3
```

Completing the children collectively satisfies the umbrella's stated outcome.

Child ownership does not itself impose sibling ordering.

### 5.2 Shared umbrella attachment

A consumer umbrella uses a reusable subsystem owned by another umbrella.

```text
Shared capability S
├── S1 contract
└── S2 implementation

Umbrella A ---- attaches to S
Umbrella B ---- attaches to S
```

The shared children remain owned by S.  They are not copied or multi-parented
into A and B.

Attachment is architectural information.  It does not create a scheduling edge
by itself.

### 5.3 Direct leaf dependency

A concrete executable leaf requires another concrete leaf first.

```text
S1 -> S2 -> A2
```

Leaf dependencies are authoritative for executable readiness.

### 5.4 Direct umbrella dependency

A consumer umbrella depends on another umbrella only when the complete consumer
outcome cannot be complete until the complete prerequisite umbrella outcome is
complete.

Do not promote every cross-umbrella leaf dependency into an umbrella
dependency.

For example:

```text
Umbrella A
├── A1
└── A2

Umbrella B
├── B1 depends on A1
└── B2
```

does not imply that B depends on all of A.

Umbrella dependency is appropriate only when completion of B genuinely requires
the whole A outcome.

## 6. Keep umbrella dependencies transitively reduced

The umbrella graph is a roadmap, not a duplicate of every transitive fact.

If:

```text
A -> B -> C
```

already expresses the outcome ordering, normally do not also record:

```text
A -> C
```

unless A independently requires C.

A transitive-reduced umbrella graph stays readable while the leaf graph
retains precise execution dependencies.

## 7. Shared prerequisite consolidation

A single shared prerequisite may remain an independent leaf.

When several related shared leaves form one reusable subsystem, create a shared
capability umbrella.

A common pattern is:

```text
Shared subsystem
├── semantic contract
├── dispatcher / invocation layer
└── provider implementation
```

Consumers attach to the shared subsystem and directly depend on only the leaves
they actually consume.

This prevents:

- arbitrary ownership by the first consumer that discovered the prerequisite;
- duplicate implementations;
- multi-parented leaves;
- unnecessary serialization between unrelated consumers.

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

Umbrella readiness is a separate high-level view:

```text
umbrella blocked
  one or more unresolved direct umbrella dependencies
```

A blocked umbrella may still contain ready leaves.  Umbrella blocking must not
unnecessarily serialize its independently executable children.

## 14. Use decomposition to expose architecture problems

During issue refinement, treat the following as diagnostic signals:

- a leaf both defines a contract and consumes it;
- a presentation command blocks a non-presentation consumer;
- provider-specific mechanics appear in portable semantics;
- one issue contains both read-only planning and mutation;
- one state issue simultaneously owns storage layout, concurrency, recovery,
  and domain records;
- several unrelated umbrellas depend on the same loose leaves;
- cleanup happens long after creation but lives in the same leaf;
- an "active issue" is represented as one shared mutable global value;
- an umbrella dependency exists only because one child consumes one child;
- dependency descriptions repeatedly use "sort of", "through", or "indirectly".

These are reasons to inspect boundaries, not automatic reasons to create more
issues.  Split only when a cleaner independently testable contract appears.

## 15. Testing consequences

Good decomposition should make tests nearly derivable from the issue contract.

For each leaf, test at least:

1. valid preconditions -> expected postconditions;
2. each important missing/invalid precondition -> actionable failure;
3. each invariant under normal execution;
4. each invariant under failure;
5. rollback or recovery behaviour for partial failure;
6. idempotency where the interface promises it;
7. concurrency behaviour where shared state is touched;
8. changed input/candidate invalidation where identity matters.

Contract tests should precede provider implementations where practical.

Provider implementations should be tested against the same semantic contract,
not only against provider-specific examples.

## 16. A practical decomposition procedure

When restructuring an existing backlog:

1. Write the outcome of each broad issue in one sentence.
2. Identify independently testable contracts or state transitions inside it.
3. Turn those contracts/transitions into candidate leaves.
4. For each leaf, write interface, preconditions, postconditions, invariants,
   failure behaviour, and direct blockers.
5. Inspect every dependency that is difficult to state directly.
6. Extract missing interfaces or shared prerequisites where necessary.
7. Consolidate related cross-umbrella shared prerequisites under a reusable
   capability umbrella.
8. Record child ownership separately from shared umbrella attachment.
9. Add direct leaf dependencies for executable ordering.
10. Promote only genuine whole-outcome relationships to direct umbrella
    dependencies.
11. Transitively reduce the umbrella graph.
12. Recalculate ready, blocked, and parallel-ready leaves.
13. Check whether cleanup/reconciliation is represented explicitly.
14. Check whether local context has been confused with durable shared state.
15. Re-run the decomposition test until every leaf has a clean completion
    boundary.

## 17. Completion test for a leaf

Before accepting an issue as a leaf, ask:

- Can I name one principal interface or transition it owns?
- Can I state its preconditions without describing unfinished work inside the
  same issue?
- Can I state its postconditions observably?
- Can I state the invariants independently of implementation details?
- Is failure/rollback behaviour defined?
- Can it be tested without first implementing an unrelated presentation layer?
- Does it depend only on exact interfaces it consumes?
- Would splitting it further reveal a genuinely reusable/testable contract,
  rather than merely making smaller tickets?

If the final answer is no, the leaf likely needs another decomposition pass.

## 18. Completion test for an umbrella

Before accepting an umbrella relationship, ask:

- Do its children collectively satisfy one coherent outcome?
- Would completing every child naturally mean the umbrella is complete?
- Are reusable cross-cutting children owned elsewhere rather than duplicated?
- Are sibling ordering constraints expressed as dependencies rather than
  implied by ownership?

Before adding an umbrella dependency, additionally ask:

> Could the consumer umbrella legitimately be complete while the proposed
> prerequisite umbrella remains incomplete?

If yes, retain precise leaf dependencies instead of adding the umbrella edge.

## 19. Design principle

The target is not the maximum number of issues.

The target is the smallest graph in which:

- ownership is clear;
- interfaces are explicit;
- safety invariants are testable;
- shared capabilities have one architectural owner;
- executable prerequisites are direct;
- parallel work is visible;
- high-level outcome ordering is understandable;
- no workflow completion relies on undocumented cleanup or hidden state.

A good issue graph is therefore both a project plan and an executable
architecture model.
