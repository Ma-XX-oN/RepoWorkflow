# Work Graph Testing and Refinement

Status: authoritative repository-neutral companion to
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

This document defines how to test and refine a work graph after applying the
decomposition and relationship model.  It is repository-independent.

All leaf and umbrella acceptance also remains subject to the universal test
adequacy and verification gate in [TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 1. Testing consequences

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

## 2. A practical decomposition procedure

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

## 3. Completion test for a leaf

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

## 4. Completion test for an umbrella

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

## 5. Design principle

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
