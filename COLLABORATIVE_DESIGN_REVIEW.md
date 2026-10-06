# Collaborative Design Review

Status: authoritative project-neutral discipline for collaborative design,
refinement, and review.

## 1. Purpose

A collaborator should evaluate ideas, not merely agree with them.

A proposed idea is a hypothesis to test against accepted contracts, invariants,
and evidence before it becomes part of a design.  A collaborator must help keep
the design internally consistent, including when that requires disagreeing with
or correcting a proposal.

The goal is to catch contradictions, information loss, and category mistakes
before implementation makes them expensive.

## 2. Core rule

Before accepting or extending a design proposal:

1. identify the existing invariants and accepted decisions that constrain it;
2. determine what semantic information the proposal preserves, changes, or
   discards;
3. check whether it contradicts an earlier definition or contract;
4. distinguish the kind of idea being proposed;
5. challenge any conflict before building further on the proposal;
6. state uncertainty when the existing contracts do not decide the question.

Do not accept an idea merely because it is plausible, compact, convenient, or
suggested by the person leading the design discussion.

## 3. Required distinctions

During design work, keep these categories separate.

### 3.1 Semantic facts

These describe what the system means and what relationships are authoritative.

Changing a semantic fact changes the contract.

### 3.2 Representation rules

These describe how already-established semantics are displayed or encoded.

A representation rule must not silently create, remove, or alter semantic
relationships.

### 3.3 Normalization or reduction rules

These transform a structure into a simpler equivalent form.

A reduction is valid only when all externally relevant information required by
later stages can be reconstructed without ambiguity.

### 3.4 Algorithms

Algorithms choose among multiple valid outcomes, such as ordering alternatives
or routing alternatives.

Do not call a canonical representation expansion an algorithm merely because
code will implement it.

Keeping these categories distinct prevents implementation choices from being
mistaken for semantic requirements.

## 4. Lossless-reduction rule

A structure may be collapsed only when the collapse preserves the external
connectivity and other information required by downstream consumers.

If two elements require independently distinguishable outgoing relationships,
collapsing them into one element is not lossless merely because they are
visually related.

When in doubt, demonstrate the reconstruction from the reduced form back to
the required semantic facts before accepting the reduction.

## 5. Renderer example

A graph renderer provides a concrete example of this discipline.

Sibling nodes that share one externally equivalent dependency track can be
represented by a collapsed sibling structure and expanded mechanically as a
fan during rendering.

Cousin nodes are different when each retains its own outgoing track.  Collapsing
those cousins would erase which source owns which connection.  Their visual
proximity does not make the reduction lossless.

This example is rationale for the general rule.  The collaboration discipline
applies to design work in any project.

## 6. Challenge constructively

A useful challenge identifies a concrete reason, such as:

- conflict with an accepted invariant;
- information that would be lost;
- a previously defined term being used with a different meaning;
- a representation being mistaken for semantics;
- an algorithm being introduced where the outcome is actually canonical;
- an untested assumption about provider, environment, or system behaviour.

Do not invent speculative objections merely to appear critical.  Challenges
must be tied to contracts, evidence, reproducible behaviour, or a clearly stated
uncertainty.

## 7. Maintain design continuity

Iterative design discussions must not repeatedly rediscover settled facts.

Collaborators should keep track of the current accepted invariants and use them
when evaluating the next proposal.  When a new proposal invalidates an earlier
decision, call out the conflict explicitly and decide which rule changes before
continuing.

Terminology should remain stable unless a deliberate terminology change is
made and its consequences are propagated.

## 8. Review procedure

For each material proposal, ask:

- What existing invariant constrains this?
- Is this semantic, representational, a reduction, or algorithmic?
- What information enters the transformation?
- Can the required information be recovered afterward?
- Does this contradict a definition already accepted?
- Is there a simpler canonical rule that removes the need for an algorithm?
- If alternatives remain, what deterministic selection rule chooses among
  them?
- What test would expose the proposal if it were wrong?

A proposal that cannot yet answer these questions remains provisional.

## 9. Relationship to testing

Design review and test adequacy reinforce each other.

A contradiction found during design should become a contract clarification or
test obligation where appropriate.  Tests should verify the independent
invariant, not merely reproduce the implementation's assumptions.

Projects should apply their own authoritative test-adequacy and verification
rules to the resulting contracts.

In RepoWorkflow, [TEST_ADEQUACY.md](TEST_ADEQUACY.md) is the concrete
repository-neutral test-adequacy and verification contract used to apply this
principle.

## 10. Principle

The collaborator's responsibility is to improve the design, not to agree with
the latest proposal.

Agreement is appropriate after the proposal survives the relevant invariant,
information-preservation, terminology, and evidence checks.  Disagreement and
correction are expected outcomes when those checks reveal a problem.
