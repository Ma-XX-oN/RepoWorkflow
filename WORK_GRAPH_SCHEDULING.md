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

Further sections: [14. Use decomposition to expose architecture problems](WORK_GRAPH_REFINEMENT.md).
