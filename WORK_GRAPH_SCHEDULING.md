# Scheduling and graph-derived work boundaries

Continuation of [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

Coordinators dispatching multiple agents MUST follow the shared-PMD
naming and conversation-only worker launch conventions in
[AGENT_PROMPT_PACKAGING.md](AGENT_PROMPT_PACKAGING.md).
Shared prompt revisions follow [PMD_AUTHORING.md](PMD_AUTHORING.md);
launching a new worker never transfers an existing owner claim.

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

## 13.3 Speculative work on serial dependencies

Speculative ticket work applies **only** when a downstream ticket has a real
serial dependency on an unfinished prerequisite.  Independent tickets without
a dependency path are ordinary parallel work, not speculation.

A downstream worker may begin bounded implementation or test preparation before
its prerequisite is DONE only when the prerequisite's required interface is
stable enough to support that work.  Record the assumed interface revision,
unresolved facts, upstream ownership and the evidence needed to revalidate it.
Avoid conflicting writes to the predecessor's owned files or state.

Speculation changes neither the canonical graph nor completion semantics:

- Keep every direct dependency edge and the original acceptance contract.
- A speculative downstream ticket remains **blocked**, not ready or DONE, while
  any prerequisite is unfinished.  An early start must be explicitly labelled
  speculative; it must not be presented as ordinary scheduler eligibility.
- No DONE handoff, closure, integration, or dependent advancement may rely on
  speculative work until every prerequisite is verified DONE and the downstream
  implementation has passed applicable integration and acceptance tests against
  the completed predecessor's actual interface and exact revision.
- If the predecessor changes, invalidate or revise dependent speculative work
  and rerun the affected verification.  Never treat mocks or draft interfaces
  as proof of provider integration.
- Preserve exclusive source and issue ownership, security/authorization gates,
  and the prohibition on unsafe merges or production cutovers.

Use speculation to reduce the critical path of a *serial* chain, not as a way to
declare blocked tickets complete or relabel parallel tasks.  If a ticket has an
independent deliverable that can truly reach DONE without its successor or
predecessor, model it as an ordinary separate ticket and direct dependency
instead of calling it speculative completion.

## 13.4 Convergence-owner handoff and child-ticket closure

**Every explicitly designated convergence ticket** carries final acceptance
and closure responsibility for its contributing executable tickets.  This
applies to integration, certification, consolidation and other convergence
work, whether the path was serial, parallel, speculative, multi-lane or
cross-repository.  The designation comes from the agreed ticket/work
contract, **not** from an Initiative/Epic/Feature prefix, title wording,
graph position, or inferred container membership.

The worker who owns a contributing ticket remains responsible for its
independent implementation and tests.  When that scope is ready for
convergence, the worker must:

1. Record the exact issue/PR, source and artifact revisions, interface
   contract, executed tests/CI, results, unresolved failures, remaining
   integration gates and lifecycle state.
2. Explicitly hand off final acceptance/closure responsibility to the
   designated convergence owner and release the active claim through the
   authoritative ownership mechanism.  Do not abandon a live claim or
   silently transfer another worker's session/identity.
3. Retain durable authorship and evidence; a handoff does not erase
   implementation ownership history or mark the ticket completed.

The convergence owner must acknowledge and legitimately acquire each
handoff before acting on its closure authority.  It then owns the exact
integration/revalidation work, resolves mismatches through the appropriate
source owner, and records its acceptance decision for **each** handed-off
ticket.  A failed or stale integration result must reopen the necessary
work or return a specific correction to its former worker with a new
explicit ownership transfer.  No simultaneous active owners.

**Handoff is not DONE.**  A child may be `accepted` independently without
yet being `completed`; final closure by the convergence owner requires
that child's actual acceptance contract and applicable integrated tests to
pass against the exact candidate.  The convergence owner may perform
explicitly authorized preparation/verification needed to retire child
dependencies while its own convergence ticket remains blocked.  This does
not make the blocked ticket ready or allow it to advance prematurely.
Only a child's canonical durable `completed` state with
`dependency_satisfied=true` satisfies its dependency edges.  Once all
children are genuinely completed, finish the convergence ticket's own
acceptance and close **the convergence ticket last**.

This policy must not force already independently completed tickets to be
reopened just to manufacture a handoff.  It must not introduce new graph
edges to encode ownership, invent a separate parent/container graph, or
let the convergence owner bypass issue claims, provider permissions,
artifact provenance, security gates, mandatory tests, user acceptance or
repository-specific merge authorization.  **Authority to close an issue
does not grant authority to merge its PR.**

### Required convergence ownership in issue contracts

**The tickets themselves are the durable source of truth.**  Record the
handoff and final closure responsibilities in the current authoritative
issue bodies **at decomposition/assignment time**, rather than relying on
an agent prompt, a chat history, or an inferred container graph.  A
handoff comment can record an actual transfer, but it does not replace
the issue's standing ownership and acceptance contract.

Every **contributing implementation/certification ticket** that will be
closed by a designated convergence owner must identify:

- The exact convergence ticket/owner responsible for final integration,
  acceptance and closure.  Do not invent an owner when designation is
  unresolved; resolve it before treating dispatch as complete.
- Its own independent implementation/test scope and the evidence that
  will accompany handoff: issue, PR, branch, exact commit/artifact,
  interface revision, executed/failed/not-run tests and CI, remaining
  defects and applicable final integration gates.
- The required handoff point: the worker offers evidence and releases
  only its own claim through supported, authorized means.  Handoff is
  not DONE, dependency satisfaction, issue closure or merge authority.
  A later correction is returned through explicit reassignment.

Every **designated convergence ticket** must identify:

- The exact contributing ticket IDs (and existing PRs when known),
  without adding artificial dependency edges to encode membership.
- The convergence owner's responsibility to acknowledge and safely
  acquire handoffs, reconcile actual interfaces and exact revisions,
  execute required real integration/acceptance, and record a separate
  decision and evidence for closing each contributing ticket.
- Failure handling: leave incomplete tickets open, return specific
  corrections to the appropriate worker, and prevent competing active
  claims or stale integration evidence from being treated as accepted.
- Completion order: close qualifying child tickets only after their
  actual acceptance contracts pass, then close the convergence ticket
  **last**.  Do not reopen legitimately completed independent leaves
  solely to manufacture a transfer; issue closure does not permit merge.

**Prompt usage:** Worker and converger prompts should explicitly instruct
agents to read and follow their current issue bodies and linked
convergence/handoff contracts.  They may briefly identify the designated
convergence ticket for clarity, but do **not** need to duplicate the
ticket's standing handoff procedure in each prompt.  Initial, continued,
recovered and acceptance work must reread the authoritative ticket after
a material contract or ownership change.

Where no automated claim-transfer command exists, explicit documented
issue handoff and acknowledgement can satisfy the procedural rule,
subject to actual provider authority and single-owner safety.  Do not
claim an atomic transfer or mutate a live claim without permission.

The transfer/closure invariant is required even where RWF has no automated
claim-transfer or child-retirement command yet.  Record explicit, verifiable
human/agent handoffs; report missing automation as an optional enhancement,
not a prerequisite for applying the ticket-level policy.  Never claim an
unsupported atomic transfer occurred.  See the
completion evidence checklist in
[WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md).

Further sections: [14. Use decomposition to expose architecture problems](WORK_GRAPH_REFINEMENT.md).
