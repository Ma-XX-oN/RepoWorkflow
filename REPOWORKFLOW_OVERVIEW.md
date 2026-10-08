# RepoWorkflow Overview

Status: general repository-neutral overview of RepoWorkflow (RWF), its goals,
operating model, and the engineering disciplines it combines.

## 1. What RepoWorkflow is

RepoWorkflow is a repository-centred development workflow system.

It treats software work as more than a list of tickets and CI jobs.  RWF turns
requirements, contracts, dependencies, candidate identity, verification
evidence, and integration state into one executable workflow.

Its central goal is:

> make the path from an intended outcome to authoritative completed work
> explicit, testable, schedulable, reproducible, and safe to automate.

RWF does not replace Git, issue trackers, CI providers, or repository-specific
build systems.  It supplies workflow semantics that connect them.

## 2. What RWF does

RWF provides a common model for:

- decomposing work into explicit interfaces and state transitions;
- recording direct dependencies between executable tickets;
- deriving ready, blocked, and parallel-ready work from the graph;
- separating repository-neutral workflow from provider mechanics;
- binding validation evidence to exact source candidates;
- distinguishing PASS, FAIL, and INCOMPLETE;
- deciding whether test evidence is adequate rather than merely GREEN;
- coordinating local and hosted verification;
- preserving immutable evidence and candidate identity;
- managing integration and authoritative completion;
- supporting multiple workers without shared mutable ambiguity;
- representing speculative work separately from authoritative completion;
- converging decomposition boundaries into durable production design.

The human-facing interface is a Git-like command family such as:

~~~text
rwf init
rwf status
rwf what-next
rwf issue ...
rwf tdd ...
rwf validate ...
rwf done ...
~~~

The deeper goal is that those commands operate one coherent workflow model.

## 3. The gap RWF addresses

Existing tools solve important pieces of software delivery.

Issue trackers represent work, hierarchy, and blocking relationships.  CI runs
checks.  Git records source history.  Contract-testing tools verify integration
agreements.  Build systems schedule dependency graphs.

The missing piece is often the semantics between those systems.

A ticket can be blocked without defining the exact result it needs.  CI can be
GREEN without showing that the test set was adequate.  Passing evidence can be
reused accidentally for a changed candidate.  A worker can wait for long tests
even when downstream work only needs an already-defined interface.

RWF attempts to make those relationships explicit and executable.

## 4. Established foundations

Most individual RWF ideas come from established engineering practice.  RWF
deliberately reuses them rather than claiming them as inventions.

### 4.1 Design by Contract

RWF leaf tickets use concepts analogous to Design by Contract:

- preconditions;
- postconditions;
- invariants;
- client/provider obligations;
- observable completion boundaries.

RWF extends these ideas from routines and components to units of development
work.

### 4.2 Interface and modular design

Architecture has long used interfaces to separate consumers from
implementations.

RWF makes interface discovery an explicit decomposition objective.  The
interface may be pre-existing, newly designed, or provisional when useful for
decomposition and testing.

This exposes architecture before implementation makes it expensive to change.

### 4.3 Contract testing

Contract testing allows consumers and providers to be tested independently
against a shared agreement.

RWF uses the same separation:

~~~text
provider conformance
consumer contract/replay testing
real integration
~~~

The executable-interface proposal uses one deterministic contract semantics for
provider verification and consumer replay.

### 4.4 Specification-based testing

RWF requires expected behaviour to be derived independently from implementation.

Requirements coverage and structural coverage are separate evidence.  Test
design considers boundaries, equivalence classes, cardinality, condition
combinations, invalid cases, lifecycle states, persistence, restart, changed
inputs, provider failure, stale state, and exact candidate identity where
applicable.

Testing therefore participates in design instead of following coding as an
afterthought.

### 4.5 Dependency graphs and scheduling

Build systems and schedulers use dependency graphs to determine what can run.

RWF applies the same principle to development tickets.  Dependencies represent
exact required results rather than vague ordering hints.  Readiness should be
derived from the graph instead of maintained as a second manual work order.

### 4.6 Speculative and out-of-order execution

Processors can execute work before earlier work retires while preventing
speculative results from becoming architecturally authoritative too soon.

RWF applies the same distinction to development work:

~~~text
implementation/test work
        |
        v
speculative completion
        |
        v
dependency + integration resolution
        |
        v
authoritative completion
~~~

Execution order and retirement order are separate concepts.

### 4.7 Pipelining and latency hiding

Pipelined systems overlap useful work with otherwise idle time.

RWF applies this even to one coding worker:

~~~text
implement prerequisite
start heavy verification
begin depending ticket against frozen interface
collect prerequisite result later
continue, repair, or revalidate as required
~~~

The worker need not idle merely because verification is still running.

### 4.8 Exact identity and immutable evidence

Distributed build/release systems rely on immutable identities and reproducible
evidence.

RWF binds validation to the exact candidate tested.  Evidence from one
candidate cannot silently certify another.  The same principle applies to
contract identity and other correctness-relevant versions.

### 4.9 Refactoring and convergence

A good decomposition boundary is not always the best final production boundary.

After a related ticket sequence converges, RWF requires a design review.  The
final design may retain an interface, combine code paths, remove indirection,
or hide fragile sequencing behind a higher-level facade.

This applies to serial and parallel work.  The grouping need not have been
labelled a Feature or Epic in advance.

### 4.10 Scientific debugging

RWF treats bug investigation as an evidence-driven experiment loop:

~~~text
Problem
Hypothesis
Action
Learning
~~~

The purpose is to identify the defect mechanism rather than apply plausible
patches until tests happen to pass.

## 5. The RWF synthesis

None of those foundations alone defines RepoWorkflow.

RWF combines them into one lifecycle:

~~~text
intended outcome
      |
      v
interface-first decomposition
      |
      v
direct executable dependency graph
      |
      v
pre-implementation test design
      |
      v
implementation
      |
      +---- ordinary serial execution
      |
      +---- speculative execution when a contract permits it
      |
      v
candidate-bound verification
      |
      v
real integration
      |
      v
ticket-sequence convergence
      |
      v
authoritative completion
~~~

The distinctive part is the relationship between the practices.

An interface can simultaneously be:

- an architectural boundary;
- a decomposition boundary;
- a test oracle;
- a dependency result;
- a speculative-execution boundary;
- an invalidation boundary when it changes;
- something reconsidered during final convergence.

## 6. Earlier design and testing

Interface-first decomposition is not merely a scheduling optimization.

Defining the interface before coding forces early answers to questions such as:

- What does the consumer need?
- What does the provider guarantee?
- What inputs and outputs are observable?
- What errors are part of the contract?
- What state transitions are legal?
- What ordering is required?
- What invariants must hold?
- What can be tested before implementation exists?

This should improve implementation quality because coding begins from a clearer
boundary and an independently derived test basis.

It also exposes awkward APIs, missing states, excessive coupling, ambiguous
ownership, and fragile sequencing before late integration.

## 7. Speculative ticket execution

Once an explicit interface is frozen, downstream work may not need the provider
implementation to be authoritatively complete.

~~~text
provider implementation ---- heavy verification ---- retirement
          |
          +---- consumer work/test ---- speculative complete
~~~

The downstream result remains speculative while its prerequisite is unresolved.

If the provider implementation fails but the agreed interface remains
unchanged, valid downstream work can be retained.

If the interface changes:

1. revise the contract explicitly;
2. identify affected consumers;
3. mark affected speculative work stale;
4. revalidate against the new contract;
5. perform real integration.

RWF must not infer semantic compatibility automatically.

## 8. Execution is not retirement

RWF separates:

~~~text
execution state: complete
dependency retirement state: unresolved
~~~

Speculative completion does not authorize dependency retirement, authoritative
ticket closure, release based on unresolved behaviour, or skipping real
integration.

Only the required dependency and integration gates can retire the work
authoritatively.

## 9. Convergence after decomposition

Interfaces useful during development are inputs to final design, not automatic
permanent architecture.

A serial chain such as:

~~~text
A -> interface X -> B -> interface Y -> C
~~~

may converge into:

~~~text
durable interface Z
        |
        v
combined internal path for A + B + C
~~~

or Z may simply hide X and Y internally.

RWF therefore treats convergence as part of completing a coherent outcome.

## 10. Compared with a conventional ticket workflow

~~~text
Conventional workflow             RWF emphasis
-------------------------------   -----------------------------------------
ticket says what to do            ticket states an observable contract
blocked-by is ordering metadata   dependency names a required result
tests follow implementation       test basis starts before implementation
GREEN means jobs passed           GREEN also requires test adequacy
branch identifies work            exact candidate identity binds evidence
consumer waits for provider       contract may permit speculative execution
task done = implementation done   execution and retirement are separate
interfaces tend to persist        convergence reviews final architecture
~~~

This compares workflow semantics.  It does not claim that industry tools are
incapable of implementing any individual row.

## 11. Compared with issue trackers

Modern issue trackers can represent hierarchy and blocking relationships.

RWF requires more execution semantics.  A dependency should name the exact
result consumed by the dependent ticket.  The graph can then drive readiness,
parallelism, speculative eligibility, and convergence instead of serving only
as planning metadata.

Human-facing Initiative, Epic, and Feature labels remain useful for navigation,
but do not replace executable dependencies.

## 12. Compared with CI alone

CI answers whether configured checks ran and what they reported.

RWF additionally asks:

- Were the right requirements tested?
- Were lifecycle states and boundaries covered?
- Is the evidence for the exact candidate?
- Were test doubles validated against authoritative behaviour?
- Is missing infrastructure FAIL or INCOMPLETE?
- Can evidence legitimately be reused?
- Has real integration happened?
- Is the candidate ready for authoritative completion?

CI remains an execution provider.  RWF owns the workflow meaning of its result.

## 13. Compared with contract testing alone

Contract testing provides a provider/consumer verification boundary.

RWF places that boundary inside a larger work graph where the same interface
can influence decomposition, tests, speculative readiness, invalidation,
integration, retirement, and final convergence.

Contract testing is therefore one discipline inside RWF, not the full workflow.

## 14. Compared with a build scheduler

A build scheduler normally decides when build actions can execute.

RWF schedules development outcomes whose state can include design, code,
verification, external evidence, integration, and retirement.

Relevant states can therefore include blocked, ready, speculative-ready,
running, speculatively complete, stale, integration-blocked, and authoritatively
complete.

## 15. What RWF aims to improve

The combined model is intended to improve:

- decomposition quality through explicit contracts;
- architecture before coding;
- independently derived tests;
- safe parallelism based on real interfaces;
- single-worker throughput by hiding test latency;
- failure isolation between provider, consumer, contract, and integration;
- retention of valid downstream work;
- explicit invalidation after contract changes;
- reproducibility through exact identity;
- final production quality through convergence review.

## 16. What RWF does not claim

RWF does not claim to invent Design by Contract, modular design, contract
testing, dependency DAG scheduling, specification-based testing, CI/CD,
speculative execution, pipelining, immutable evidence, refactoring, facade
design, or scientific debugging.

Its value proposition is their operational combination.

Ideas that normally live in different disciplines and tools are given shared
workflow semantics.

## 17. Why combine disciplines

Development concerns are coupled.

Architecture affects decomposition.  Decomposition affects testability.
Testability affects scheduling.  Scheduling affects latency.  Contract changes
affect invalidation.  Integration affects retirement.  Final convergence
affects whether temporary boundaries become good production architecture.

Treating each concern independently loses those relationships.

RWF attempts to preserve them in one model.

## 18. Intended result

The intended result is not merely more automation.

It is a workflow in which:

- design starts before coding;
- tests start from independently stated behaviour;
- dependencies describe real interfaces;
- useful work starts as early as safely possible;
- test latency is hidden when possible;
- failures invalidate only what they actually invalidate;
- evidence belongs to exact candidates;
- integration remains real;
- temporary boundaries are reconsidered;
- authoritative completion means the required outcome has converged.

Detailed contracts and policies live in the specialised RWF documents.  This
overview explains how those pieces fit together and why.
