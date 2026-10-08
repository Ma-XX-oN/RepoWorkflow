# Universal Test Adequacy and Verification Gate

Status: authoritative repository-neutral testing policy for RepoWorkflow and
every consumer project that uses RepoWorkflow.

This document defines how to decide whether testing is adequate for a change.
Repository-specific test suites remain owned by each repository, but their
verification must satisfy this policy before work is called complete.

The policy applies to implementation work, bug fixes, refactors, migrations,
provider integrations, generated artifacts, persistent state, and code review.
A dimension that genuinely does not apply must be recorded as N/A rather than
satisfied with a meaningless test.

## 1. Meaning of GREEN

GREEN means:

> every identified verification obligation for the exact candidate passed.

GREEN does not mean that the software has been proven defect-free. Passing
tests establish only the behaviour covered by those tests and their oracles.

Completion therefore requires both:

1. the required tests/checks are GREEN; and
2. the test set itself has passed this adequacy gate.

A test run with unexamined acceptance criteria, lifecycle states, boundaries,
or provider assumptions is not adequate merely because every executed test
passed.

## 2. Independent test basis and oracles

Expected behaviour must be derived independently from the implementation under
test.

Authoritative test bases include, in order appropriate to the work:

- explicit requirements and acceptance criteria;
- public or internal contracts and specifications;
- documented invariants;
- verified external-provider behaviour;
- authoritative persisted data and schemas;
- established compatibility behaviour that the change must preserve.

Do not derive both implementation behaviour and expected test results from the
same implementation assumption.

When a proposed behaviour change conflicts with an established regression or
compatibility test, do not rewrite that test's oracle merely to make the
proposal GREEN.  First identify the authoritative requirement or contract that
explicitly supersedes the established behaviour.  If no such authoritative
supersession exists, the disagreement is evidence against the proposal.  When
a contract is intentionally superseded, record that contract delta and why the
older oracle no longer applies before changing or removing the regression.

Specification/contract-based tests and implementation/structural tests are
separate evidence. Structural inspection can show that a path was exercised;
it cannot establish that the path implements the correct requirement.

When an external provider is involved, validate the provider behaviour or
contract used by the test before treating a fake response as authoritative.

## 3. Requirement and invariant traceability

Every independently testable acceptance criterion and invariant must map to
explicit verification evidence.

Before closure, maintain enough traceability to answer:

- What requirement or invariant is being verified?
- Which test/check verifies it?
- What observable result establishes success?
- Is the evidence for the exact candidate being accepted?

A requirement with no verification evidence is a failed closure gate.

One test may verify several requirements when the mapping remains explicit.
Several tests may verify one requirement when distinct dimensions are needed.

## 4. Test-dimension analysis

Analyse relevant test dimensions before or alongside implementation rather than
choosing cases only after the code exists.

For each behaviour, consider at least:

- equivalence classes of valid and invalid inputs;
- meaningful minimum, maximum, just-inside, and just-outside boundaries;
- zero, one, and many cardinalities where collections/relationships exist;
- ordering where order changes semantics;
- combinations of conditions, flags, permissions, and prerequisites;
- invalid, malformed, missing, stale, conflicting, and unauthorized inputs;
- success, expected failure, and interruption/recovery paths;
- platform/runtime/capability differences that change behaviour.

Use decision tables when combinations of independent conditions select
different outcomes. Do not rely on a few intuitive happy-path combinations
when the decision space is material.

Exhaustive testing is normally impossible. Select representative cases
deliberately and document the remaining risk when it matters.

## 5. Stateful and lifecycle behaviour

A stateful feature must be tested as a sequence of transitions, not only as an
isolated operation from an empty state.

Identify the relevant states, legal transitions, illegal transitions, and
events that change state. Test applicable lifecycle dimensions such as:

1. initial/empty state;
2. first successful operation;
3. repeated operation with unchanged input;
4. subsequent normal operation after success;
5. changed input or changed selection;
6. overlapping/pre-existing state;
7. read-after-write behaviour;
8. stale/conflicting state;
9. persistence across process restart/reload/reopen;
10. retry after interruption or provider failure;
11. invalid transitions;
12. cleanup, rollback, or reconciliation.

Verify invariants after meaningful transitions, not only at the final state.

## 6. State sufficiency

The existence of persisted, cached, generated, or derived state does not prove
that the state is usable.

Where state is part of the contract, verification must separately establish:

- existence;
- correct type/schema/shape;
- required contents;
- completeness;
- semantic correctness;
- consistency with authoritative sources;
- correct identity/version/candidate binding.

Tests must inspect the state future operations actually consume. A shallow
assertion such as "file exists", "graph exists", or "cache populated" is not
sufficient when later behaviour depends on its contents.

## 7. Mocks, fixtures, fakes, and authoritative sources

Mocks, fixtures, emulators, fake providers, and generated test data are part of
the test system and require validation.

A provider fixture must model the relevant authoritative contract rather than a
reduced payload invented to satisfy the implementation.

For provider-backed or externally synchronized behaviour:

1. identify the authoritative source;
2. verify the source's relevant contract/shape/semantics;
3. validate test doubles against that contract;
4. verify the real authoritative source contains the data the feature assumes
   exists;
5. test missing, incomplete, stale, and conflicting authoritative data where
   those states are possible.

Correct synchronization code operating against an unpopulated authoritative
source is not a complete implementation.

## 8. Black-box, structural, and static verification

Requirements coverage and structural coverage are different obligations.

Use specification/contract-based black-box tests to establish externally
required behaviour.

Use structural/white-box techniques where they add evidence that important
branches, conditions, error paths, or internal invariants were exercised.

Use static analysis/review where applicable to detect defects without executing
the software, including invalid assumptions, unreachable paths, unsafe
constructs, type/schema violations, and policy violations.

Do not substitute statement/branch/path coverage percentages for requirement
coverage. High structural coverage can still execute the wrong behaviour.

## 9. Defect-fix discipline

Every bug investigation must follow the evidence-driven experiment protocol in
[BUG_INVESTIGATION.md](BUG_INVESTIGATION.md).  That protocol requires repeated:

```text
Problem
Hypothesis
Action
Learning
```

cycles from objective reproduction through root-cause identification.  It
applies to every bug resolution, not only renderer or high-risk defects.

For every defect fix:

1. reproduce the defect with failing objective evidence;
2. identify the violated requirement/invariant and root cause through the
   required experiment cycles;
3. apply the fix only after evidence identifies the defect mechanism with
   sufficient confidence;
4. run confirmation testing proving the original defect is corrected;
5. run relevant regression testing;
6. normally retain a regression test that would fail if the defect returns;
7. when the known-bad candidate remains reproducible, demonstrate that retained
   regression RED against that actual bad candidate and GREEN against the
   corrected candidate; a regression that is only shown GREEN on the fix has
   not yet proved that it detects the escaped defect;
8. examine whether the escape reveals a reusable process/test improvement.

An escaped defect is evidence about both the product and the verification
process. Fixing only the local code without examining a reusable systemic
testing gap is incomplete.

## 10. Risk-based depth

Test depth must reflect risk.

Increase verification depth for behaviour with high failure impact, high
likelihood, complex state, concurrency, persistence, security/safety
invariants, external-provider dependencies, difficult recovery, or a history of
defects.

Low-risk simple behaviour does not require ceremonial tests for irrelevant
dimensions. Mark those dimensions N/A and keep the rationale clear.

Defect clusters deserve additional scrutiny. Repeated defects in one component
or contract are evidence that the existing suite is not yet sufficient there.

## 11. Reproducibility and configuration

Verification evidence must be reproducible enough to identify what was actually
tested.

Record or bind, as applicable:

- source/candidate revision;
- test revision when different;
- configuration;
- fixture/test-data revision;
- provider/API/schema version;
- runtime/toolchain;
- relevant operating system/architecture/capability;
- command or authoritative validation entry point;
- result and failure evidence.

A result from one candidate, configuration, or provider contract must not be
silently reused for a materially different one.

## 12. Test-suite health

Existing tests must be challenged periodically rather than treated as permanent
proof of adequacy.

When a mature suite repeatedly passes while defects escape, examine:

- untested requirements;
- repeated use of the same data/paths;
- missing boundaries or combinations;
- missing lifecycle transitions;
- self-authored oracles;
- stale provider fixtures;
- missing negative tests;
- missing assembled/end-to-end paths;
- areas with repeated defect concentration.

Add new techniques or scenarios when existing tests stop exposing meaningful
new failure classes. Preserve useful regression tests while avoiding redundant
tests that add no independent evidence.

## 12.1 Escaped-defect continuation and assembled-path coverage

When a defect is discovered through an assembled workflow, fixing only the
first failing layer is insufficient evidence of completion.

The retained regression must, where practical, continue through downstream
supported stages that were previously unreachable.  A replacement test that
only reconstructs the user's intent through lower-level helpers is not
equivalent to exercising the shipped public boundary.

For a pipeline such as:

```text
input
  -> acquisition
  -> normalization
  -> semantic model
  -> projection
  -> layout
  -> routing
  -> rendering/output
```

a defect at one stage must be followed by continued execution through later
supported stages after the fix.  This catches latent defects that were hidden
behind the original failure.

If the public/assembled path can be tested deterministically, at least one
regression must enter through that boundary rather than only through internal
helpers.

## 12.2 Interacting dimensions require cross-product analysis

Testing individual dimensions independently does not establish correctness for
their interactions.

When two or more dimensions materially influence behaviour, analyse their
cross-product explicitly using a decision table, pairwise strategy, exhaustive
bounded enumeration, or another justified combinatorial technique.

Examples include:

- fan-in degree x fan-out degree;
- same-lane x cross-lane;
- adjacent x long edge;
- grouped x ungrouped nodes;
- above x same-row x below placement;
- permission x lifecycle state;
- cache state x provider state;
- retry state x changed input.

A test suite that covers each factor separately but omits a material
combination has an identified adequacy gap.

## 12.3 Generated and property-based testing for combinatorial systems

When a component's valid state space is combinatorial and an independent oracle
exists, generated/property-based testing should supplement example-based tests.

Use bounded exhaustive generation where practical for small state spaces.
Otherwise use deterministic generation with reproducible seeds and explicit
coverage goals.

For every generated case, define an independent invariant such as:

- semantic equivalence;
- exact reachability;
- round-trip equality;
- conservation of state;
- monotonicity;
- idempotency;
- explicit rejection of unsupported input.

A generated case must either satisfy the invariant or fail through a documented
unsupported/invalid-input path.  Silent semantic drift is never acceptable.

## 12.4 Production-owned data as active test input

Repository-owned canonical data that materially drives behaviour is an active
test fixture, not merely configuration.

When such data changes, the workflows and components that consume it must be
re-exercised at an appropriate assembled level.  Schema validation alone is
insufficient when data topology, cardinality, ordering, or contents influence
behaviour.

Examples include dependency graphs, migration manifests, policy tables,
routing tables, compatibility matrices, and generated registries.

## 12.5 Certification and evidence invalidation

Historical certification evidence is valid only for the material inputs and
candidate to which it is bound.

Certification records should include enough identity to detect material drift,
such as:

- exact candidate SHA;
- authoritative data digest;
- relevant schema/contract version;
- provider/API version where applicable;
- fixture/data revision;
- configuration affecting behaviour.

When any material binding changes, prior evidence must become stale until it
is regenerated or replaced by current executable evidence.

A test that merely proves an old certification artifact exists or has a valid
shape does not establish that the current implementation remains certified.

Where the material input surface can be enumerated mechanically, derive the
required certification bindings mechanically rather than maintaining a manual
subset.  Refactoring that adds, removes, or splits material modules must then
invalidate certification automatically instead of depending on a maintainer to
remember every binding.

## 12.6 Evidence categories must remain distinct

Platform coverage, semantic/topology coverage, integration coverage, and
assembled public-workflow coverage establish different facts.

Do not cite a platform smoke probe as evidence of semantic coverage, or a unit
semantic test as evidence of assembled workflow correctness, unless the test
actually crosses the relevant boundary.

Verification reporting must state which category each result establishes.

## 13. Universal closure gate

Before declaring coding work complete, answer each applicable item.

### Test basis

- [ ] Requirements/contracts/invariants are identified.
- [ ] Expected behaviour comes from an independent authoritative basis.
- [ ] External-provider assumptions are verified.

### Traceability

- [ ] Every acceptance criterion has explicit verification evidence.
- [ ] Every required invariant has explicit verification evidence.

### Dimensions

- [ ] Equivalence classes were considered.
- [ ] Boundaries were considered.
- [ ] Zero/one/many cardinalities were considered.
- [ ] Relevant condition combinations/decision tables were considered.
- [ ] Material interacting dimensions were exercised together, not only
  individually.
- [ ] Invalid/negative cases were considered.

### State and lifecycle

- [ ] Relevant initial and subsequent states were tested.
- [ ] Repeated operations were considered.
- [ ] Changed-input transitions were considered.
- [ ] Persistence/restart was considered where state survives execution.
- [ ] Invalid transitions and recovery were considered.

### State sufficiency

- [ ] State existence was verified.
- [ ] State contents and completeness were verified.
- [ ] State semantics and authoritative consistency were verified.

### Test independence and external data

- [ ] Black-box expectations are not copied from implementation assumptions.
- [ ] Mocks/fixtures/fakes are validated against authoritative contracts.
- [ ] Required authoritative external/persistent data is actually populated.
- [ ] Production-owned canonical data that drives behaviour is exercised as an
  active fixture at the appropriate assembled level.

### Structural/static verification

- [ ] Relevant code paths/branches were examined where useful.
- [ ] Static analysis/review was performed where applicable.
- [ ] Structural coverage was not substituted for requirement coverage.

### Defects and regression

- [ ] The original defect was reproduced when fixing a bug.
- [ ] Confirmation testing proves the fix.
- [ ] Relevant regression testing passes.
- [ ] A regression test is retained unless there is a documented reason not to.
- [ ] When a known-bad candidate is reproducible, the retained regression was
  demonstrated RED on that candidate and GREEN on the corrected candidate.
- [ ] Escaped defects were assessed for systemic prevention improvements.
- [ ] For assembled escaped defects, retained regression continues through
  downstream supported stages that were previously unreachable.

### Risk and reproducibility

- [ ] Test depth matches the risk.
- [ ] Combinatorial state spaces with an independent oracle use bounded
  generated/property coverage, or have a documented N/A rationale.
- [ ] Historical certification evidence is current for all material bindings,
  or is explicitly stale and regenerated before closure.
- [ ] Candidate/configuration/environment/provider identity is reproducible.
- [ ] Remaining untested material risk is explicit.

Any applicable unchecked item blocks an adequacy claim. A genuinely irrelevant
item is N/A, not implicitly passed.

## 14. Relationship to RepoWorkflow

RepoWorkflow owns this portable adequacy policy. Consumer repositories own
their repository-specific test commands, fixtures, provider adapters, and
validation implementation.

TEST_STRATEGY.md defines RepoWorkflow's own concrete lifecycle test
specification. WORK_GRAPH_TESTING.md defines how issue/work-graph contracts are
refined and accepted. Both must satisfy this universal policy.

RWF automation should enforce objective portions of this gate when metadata is
available, especially acceptance traceability, lifecycle scenario ownership,
exact-candidate evidence, provider-contract verification, and regression
ownership. Human/agent analysis remains responsible for semantic questions that
cannot be derived mechanically.

## 15. Reference basis

This policy generalizes established testing concepts rather than copying one
project's historical failures.

Primary references:

- ISTQB Certified Tester Foundation Level Syllabus v4.0.1:
  https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf
- NIST Software Supply Chain Security Guidance, testing practices:
  https://www.nist.gov/itl/executive-order-14028-improving-nations-cybersecurity/software-supply-chain-security-guidance-3
- NIST conformance testing overview:
  https://www.nist.gov/itl/ai/applied-ai-research-group/what-thing-called-conformance

RepoWorkflow's policy is authoritative for projects using RWF even when these
external references later evolve.
