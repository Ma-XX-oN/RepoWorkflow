# 13. Universal closure gate — companion sections

Continued from [TEST_ADEQUACY.md](TEST_ADEQUACY.md).

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
- [ ] Escaped defects were assessed for systemic prevention improvements.
- [ ] For assembled escaped defects, retained regression continues through
  downstream supported stages that were previously unreachable.

### Temporary transformation fidelity

- [ ] Applicable temporary transformation-fidelity tests were run during
  regression validation.
- [ ] Material temporary preservation cases were reviewed for promotion into
  permanent contract/regression tests.
- [ ] The complete `.ci/temp-tests/<issue>/` sandbox is absent before
  integration.

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
