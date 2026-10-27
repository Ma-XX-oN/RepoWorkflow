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

For human-facing **Progress Graph (PG)** Mermaid dependency diagrams, use
the five-status colours and exact Unicode symbols in
[WORK_GRAPH_VISUAL_CONVENTIONS.md](WORK_GRAPH_VISUAL_CONVENTIONS.md).
For RWF's formal six-state **Lifecycle Graph (LG)**, use
[SIX_STATE_LIFECYCLE.md](SIX_STATE_LIFECYCLE.md) and
[LANE_GRAPH_DISPLAY.md](LANE_GRAPH_DISPLAY.md).  These are display names,
not new dependency graphs, lifecycle transitions, or CLI commands.

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

In the human-facing Progress Graph, show active authorised speculative work as
`◑ Speculative` with the prescribed dark blue fill and amber border, even
though its executable dependency readiness remains **blocked**.  When all
direct prerequisites become DONE, the speculative visual designation ends:
show `◐ In progress` if work continues or `♥ Done` if its own acceptance
is independently complete.  Do not use the speculative symbol for idle,
unauthorised, or merely proposed downstream work.  This is a presentation
rule, not a lifecycle state or dependency-edge change.

Use speculation to reduce the critical path of a *serial* chain, not as a way to
declare blocked tickets complete or relabel parallel tasks.  If a ticket has an
independent deliverable that can truly reach DONE without its successor or
predecessor, model it as an ordinary separate ticket and direct dependency
instead of calling it speculative completion.

## 13.4 Mandatory RWF scheduling and speculation gate

This gate is **mandatory for coordinators and controllers** before scheduling
workers, generating SPINUP commands, advancing successors, or declaring
dependency-derived work ready.  Consult the current authoritative dependency
graph, live issue acceptance contracts, owner claims, handoffs and exact
candidate revisions.  A stored snapshot or speculative prediction does not
establish an upstream ticket as DONE.

### Classification before dispatch

Classify each relevant ticket using the current evidence:

| Class | Required condition | Scheduling consequence |
|---|---|---|
| **DONE** | Its own scoped acceptance and handoff are independently verified | May satisfy downstream dependency gates |
| **READY** | All direct prerequisites are verified DONE, work is authorised and unclaimed or held by its continuing owner | May execute normally |
| **SPECULATIVE-ELIGIBLE** | One or more direct prerequisites remain incomplete, but a sufficiently stable exact upstream interface enables bounded independent authorised work | May execute provisionally, subject to speculation and ownership gates |
| **BLOCKED** | Direct prerequisites remain incomplete and no independently executable authorised scope is presently available | Do not dispatch as normal ready work |
| **DEFERRED** | Explicitly deferred by the authorised scope, owner or required approval gate | Do not dispatch until the deferral is lifted |

**Speculative eligibility is not DONE and is not ordinary readiness.**
An anticipated or likely completion never substitutes for verified upstream
acceptance.  In the Progress Graph, use the `◑ Speculative` status **only
once authorised speculative execution is underway**.  A merely eligible
but idle downstream ticket retains the applicable blocked visual status.

### Two execution frontiers

Maintain and publish two separate dispatch frontiers:

1. **Ordinary READY frontier:** tickets with every direct prerequisite DONE.
2. **SPECULATIVE-ELIGIBLE frontier:** bounded downstream work whose unfinished
   prerequisite has a documented stable interface and which can make
   independent progress without conflicting with its predecessor's owner.

Prioritise completion of executable prerequisites on the critical dependency
path.  Do not place a speculative dependent *ahead of* its runnable
prerequisite as if it were already ready, but do not serialize independent,
authorised work unnecessarily.  Concurrent execution is allowed only where
source/issue ownership, interface stability, acceptance and approval
boundaries remain intact.

### Speculative execution and completion boundary

Before speculative work begins, record the incomplete direct prerequisites,
exact upstream interface revision, stability evidence, bounded work scope,
owner/approval basis, and final revalidation requirements.  Its
implementation and focused tests may be provisionally finished, but the
ticket may **not** be classified DONE, handed off as accepted, integrated
on the assumption of upstream completion, or used to advance successors
until all direct prerequisites are verifiably DONE and the downstream
candidate is revalidated against their *actual accepted revisions*.

If upstream changes invalidate assumptions, revise affected work and
rerun appropriate tests.  A completion claim must be established by
independent acceptance evidence, not inferred from upstream predictions,
mock results or an open/closed issue label alone.

### Mandatory scheduling output

Before generating worker prompts or presenting the next work order, report:

- **DONE** tickets with verified acceptance/handoff evidence.
- **READY** tickets and runnable prerequisites.
- **SPECULATIVE-ELIGIBLE** tickets, explicitly identifying unresolved
  prerequisites and the independent authorised scope.
- **BLOCKED** tickets with their exact missing prerequisites.
- **DEFERRED** tickets and the authority/condition for resumption.

Generate independently copyable SPINUP prompts only for currently authorised
READY work or explicitly labelled, authorised speculative work.  Prefer
runnable prerequisites before dependents and recheck the live graph,
claims and acceptance gates whenever scheduling decisions change.

This gate does not expand the scope of any worker, transfer ownership,
authorise a new claimant, permit conflicting source writes, override security
or approval controls, or modify the canonical dependency graph, six-state
lifecycle, or `rwf lanes view` rendering contract.  It supplements
§13.2 and §13.3 rather than replacing their completion rules.

Further sections: [14. Use decomposition to expose architecture problems](WORK_GRAPH_REFINEMENT.md).
