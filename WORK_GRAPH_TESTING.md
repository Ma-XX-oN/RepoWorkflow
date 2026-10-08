# Work Graph Testing and Refinement

Status: authoritative repository-neutral companion to
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

This document defines how to test and refine a work graph after applying the
direct-dependency model. It is repository-independent.

Every issue remains subject to the universal test adequacy and verification
gate in [TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 1. Testing consequences

Good decomposition should make tests nearly derivable from the issue contract.

For each executable ticket, test at least:

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

## 1.1 Interface-first provider/consumer testing

When a direct dependency exists only because a consumer needs a provider
interface, consider extracting that interface before implementation.

A predefined executable interface can then support three separate test layers:

1. provider conformance tests against the real implementation;
2. consumer tests against deterministic replay of the same interface;
3. real integration tests after both sides independently conform.

This can make tests smaller and more diagnostic while also allowing provider
and consumer implementation work to proceed in parallel.

The technique is optional.  Use it only when the interface can be defined
independently and precisely enough to serve as a shared oracle.  Do not invent
an interface merely to create parallel work.

The executable contract proposal is defined in
[EXECUTABLE_INTERFACE_CONTRACTS.md](EXECUTABLE_INTERFACE_CONTRACTS.md).
Universal adequacy requirements in [TEST_ADEQUACY.md](TEST_ADEQUACY.md) still
apply.

## 2. A practical decomposition procedure

When restructuring an existing backlog:

1. Write the outcome of each broad ticket in one sentence.
2. Identify independently testable contracts or state transitions inside it.
3. Turn those contracts/transitions into candidate executable tickets.
4. For each executable ticket, write interface, preconditions, postconditions,
   invariants, failure behaviour, and direct blockers.
5. Inspect every dependency that is difficult to state directly.
6. Extract missing interfaces or shared prerequisites where necessary.
7. Add only direct dependencies that represent exact required inputs/results.
8. Remove redundant transitive dependency edges.
9. Recalculate ready, blocked, and parallel-ready tickets.
10. Check whether cleanup/reconciliation is represented explicitly.
11. Check whether local context has been confused with durable shared state.
12. Re-run the decomposition test until every executable ticket has a clean
    completion boundary.

Descriptive `Initiative:`, `Epic:`, and `Feature:` tickets may document
larger outcomes, but their prefixes and prose are not machine-readable graph
relationships.

## 3. Completion test for an executable ticket

Before accepting a ticket as executable work, ask:

- Can I name one principal interface or transition it owns?
- Can I state its preconditions without describing unfinished work inside the
  same ticket?
- Can I state its postconditions observably?
- Can I state the invariants independently of implementation details?
- Is failure/rollback behaviour defined?
- Can it be tested without first implementing an unrelated presentation layer?
- Does it depend only on exact interfaces it consumes?
- Would splitting it further reveal a genuinely reusable/testable contract,
  rather than merely making smaller tickets?

If the final answer is no, the ticket likely needs another decomposition pass.

## 4. Completion test for descriptive container tickets

A descriptive Initiative, Epic, or Feature ticket is useful when it gives a
human-readable view of a coherent larger outcome.

Before using one, ask:

- Does the title prefix accurately describe the scale of the outcome?
- Does its body clearly identify the implementation/certification tickets that
  collectively satisfy it?
- Are actual execution constraints represented as direct dependencies on the
  executable tickets themselves?
- Would removing the prefix leave RWF scheduling unchanged?

If the final answer is no, the decomposition is mixing presentation taxonomy
with executable graph semantics.

## 5. Dependency review

For each direct edge A -> B, verify that A genuinely requires B's exact result.

If A -> B -> C already captures the ordering, do not add A -> C unless A
independently consumes C's interface.

When several consumers use the same prerequisite, keep one prerequisite ticket
and add direct edges only from consumers that actually require it.

## 6. Design principle

The target is not the maximum number of tickets.

The target is the smallest direct-dependency graph in which:

- interfaces are explicit;
- safety invariants are testable;
- executable prerequisites are direct;
- parallel work is visible;
- descriptive Initiative/Epic/Feature titles improve human navigation without
  changing scheduling semantics;
- no workflow completion relies on undocumented cleanup or hidden state.

A good work graph is therefore both a project plan and an executable dependency
model.
