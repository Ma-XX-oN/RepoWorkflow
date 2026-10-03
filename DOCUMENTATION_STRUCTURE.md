# Documentation Structure Policy

Status: authoritative policy for structuring RepoWorkflow source documentation.

This document defines how documentation should be kept concise and navigable
without sacrificing authoritative information.

## 1. Purpose

The practical ~500-line documentation ceiling is a maintainability signal, not
a content budget.

A document approaching the ceiling should trigger a review of its
responsibilities.  The goal is not to make the file numerically smaller.  The
goal is to keep each authoritative document focused enough that its subject,
ownership, invariants, and relationships remain easy to understand and verify.

## 2. Preserve semantics

Do not satisfy a size limit by deleting, weakening, or compressing information
that is still authoritative.

In particular, do not remove or abbreviate solely for line count:

- invariants;
- preconditions or postconditions;
- failure and rollback behaviour;
- edge cases;
- examples that establish intended semantics;
- rationale needed to prevent a previously rejected design from returning;
- compatibility or migration requirements;
- cross-component responsibility boundaries;
- verification or acceptance requirements.

Concise wording is preferred when it preserves the complete meaning.  Concision
must not create ambiguity or silently discard constraints.

## 3. Split by responsibility

When a document becomes too broad, identify a real subject or responsibility
boundary and move that complete responsibility into a focused companion
document.

Good split boundaries include:

- architecture versus public workflow;
- command grammar versus grammar test contract;
- work-graph methodology versus graph-testing/refinement procedure;
- lifecycle semantics versus integration/release mechanics;
- static test catalogue versus execution strategy;
- generic policy versus provider-specific implementation contract.

A split should answer a clear question such as:

```text
Document A
  What is the model or contract?

Document B
  How is that model tested or applied?
```

or:

```text
Document A
  What is the portable semantic rule?

Document B
  What are the provider/integration mechanics?
```

Do not create arbitrary "part 1" / "part 2" pages merely to move lines.

## 4. One authoritative owner

After a split, each semantic rule should have one authoritative home.

Other documents should link to that owner rather than reproduce the same
contract in slightly different wording.

A useful cross-reference should briefly explain why the reader should follow
it, for example:

```text
WORK_GRAPH_METHODOLOGY.md defines decomposition and graph semantics.
WORK_GRAPH_TESTING.md defines how those semantics are verified.
```

Cross-references should reduce duplication, not hide important relationships.

## 5. Preserve context during extraction

When moving material to a companion document:

1. identify the complete responsibility being extracted;
2. move all rules, examples, edge cases, and rationale belonging to it;
3. keep enough context in the original document to explain the relationship;
4. add an explicit link to the new authoritative owner;
5. check neighbouring sections for assumptions that now require a link;
6. verify that no requirement was lost or accidentally duplicated;
7. re-check both documents for coherent scope and naming.

A split is incomplete if a reader must reconstruct the old document mentally to
understand either new one.

## 6. Line count is a trigger, not a target

Do not optimize a document toward 499 or 500 lines.

If a document is approaching the practical ceiling and another coherent
responsibility can be extracted, perform the split even if small wording edits
could technically keep the file under the threshold.

Likewise, do not split a focused document merely because it is moderately long
if there is no sound responsibility boundary.  The structural boundary is the
primary criterion.

## 7. Relationship to source-size policy

The same principle applies to authoritative production source:

- size pressure is evidence that responsibilities may be mixed;
- extract coherent modules/interfaces rather than minifying logic;
- preserve tests and invariants through the extraction;
- do not weaken behaviour simply to satisfy a line-count rule.

Source and documentation differ in mechanics, but both use the size ceiling as
an architectural diagnostic rather than a deletion quota.

## 8. Review checklist

Before accepting a size-driven split, verify:

- Does each resulting document have one clear purpose?
- Is every authoritative rule still present?
- Were examples and edge cases preserved where they carry semantics?
- Is there exactly one authoritative owner for each contract?
- Are cross-references explicit and useful?
- Did the split reduce mixed responsibilities rather than merely page length?
- Could a reader understand either document without knowing the pre-split
  layout?
- Was anything shortened only to make the line counter pass?

If the last answer is yes, restore the information and find a better structural
split.

## 9. Principle

Prefer several concise, directed, semantically complete documents over either:

- one sprawling document containing unrelated responsibilities; or
- several arbitrarily divided pages that merely distribute the same sprawl.

The line ceiling exists to encourage better structure.  It must never become a
reason to lose information.
