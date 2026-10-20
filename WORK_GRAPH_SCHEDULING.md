# Scheduling and graph-derived work boundaries

Continuation of [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

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

### Required instructions in every convergence work prompt

**Prompt authors must include the ownership and handoff contract when
dispatching work.**  The agent carrying out a task cannot be expected to
infer this procedure from a ticket number, title, graph or prior chat.
The instruction belongs in the actual copyable worker/converger prompt;
a link to this methodology alone is not sufficient.

A contributing **implementation-worker prompt** must state:

- The specific convergence issue/owner receiving the eventual handoff, or
  clearly mark that designation unresolved before work is assigned.
- The worker owns implementation and independent testing of its assigned
  scope, but the named converger owns final integrated acceptance and
  closure of the handed-off issue.
- Before leaving the work, the worker records and offers a handoff with
  exact issue/PR/branch/commit/artifact/CI references, interface revision,
  passed/failed/not-run acceptance, unresolved issues and necessary next
  actions.  It must release its own active claim only through supported,
  authorized means and must never surrender someone else's claim.
- A handoff does not mean DONE, close the issue, satisfy dependencies, or
  authorize a merge.  Unfinished independent work is not falsely handed
  off as complete; record remaining work and continue if actionable.
- Source corrections subsequently requested by the converger require an
  explicit return/reassignment and preserved ownership provenance.

The designated **convergence-worker prompt** must state:

- Exactly which contributing tickets and existing owned PRs it receives,
  and that it must verify rather than assume each handoff/claim state.
- The converger acknowledges/acquires handoffs and owns final interface
  reconciliation, exact-source integration, required acceptance tests and
  justified completion/closure of **each** contributing ticket.
- If a child is blocked or a correction is needed, the converger keeps it
  open, assigns the repair to the appropriate owner explicitly, and
  retains exact evidence and tracked blockers.  No premature DONE.
- Close children only after their individual requirements pass on the
  relevant real integrated result, then complete the convergence ticket
  **last**.  Already completed independent children need no fabricated
  transfer/reopen.  Maintain all existing direct dependencies.
- **Closing issues and merging PRs are separate authorities.**  No merge
  without explicit repository/user authorization.

For a multi-worker dispatch, include both sets of instructions in the
initial individual prompts; do not wait for workers to announce DONE and
then retrofit the handoff.  Carry the same rule through continuation,
context-recovery, blocker-resolution and acceptance prompts.

This is an **agent-prompt and documented handoff requirement**.  Manual
issue comments and explicit handoff acknowledgements are sufficient when
no safe automated ownership transfer exists; a missing automatic command
must not block documentation or sensible agent instructions.  Never claim
an atomic provider operation or change a live claim without authority.

The transfer/closure invariant is required even where RWF has no automated
claim-transfer or child-retirement command yet.  Record explicit, verifiable
human/agent handoffs; report missing automation as an optional enhancement,
not a prerequisite for applying the prompt-level policy.  Never claim an
unsupported atomic transfer occurred.  See the
completion evidence checklist in
[WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md).

Further sections: [14. Use decomposition to expose architecture problems](WORK_GRAPH_REFINEMENT.md).
