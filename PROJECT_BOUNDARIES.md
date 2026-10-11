# Project boundaries: RepoWorkflow and proposed ProjectWorkflow

Status: **PROPOSED — boundary review, not approved**
Date: 2026-10-11
Owner of review: [RWF roadmap #648](https://github.com/Ma-XX-oN/RepoWorkflow/issues/648)

This document sets out a possible separation of concerns. It **does not**
authorize a new repository, moving tickets, implementing ProjectWorkflow,
changing execution dependencies, approving a specification, or merging a PR.

## Missions

**RepoWorkflow (RWF)** orchestrates software-development execution: turning
actionable repository tickets into completed, independently verified and
appropriately integrated work while preserving requirements, dependencies,
tests, decisions and unfinished transitions. Git, issue providers, test
frameworks, build tools and CI remain their own authorities.

**ProjectWorkflow (PWF, proposed)** orchestrates project direction: outcomes,
roadmaps, milestone/phase acceptance, specification baselines, controlled
amendments and project-level progress. It should apply to software and
non-software projects, including programmes spanning repositories.

Both are valuable, but ordinary developer workflows must function without
PWF. A roadmap is not part of the executable ticket dependency DAG.

## Capability ownership

| Capability | Proposed owner | Boundary |
| --- | --- | --- |
| Development ticket dependency DAG/readiness | RWF | Actual execution prerequisites only |
| Ticket lifecycle, lanes, workspaces, agents | RWF | Developer work and conflict recovery |
| Branch ancestry, Git integration, PRELIM | RWF | Source identities and Git transitions |
| Local/hosted tests and platform selection | RWF | Executes tests; emits exact evidence |
| Explicit local/hosted artifact builds | RWF | Reuses .ci/run; selects JSON build recipes |
| repo-version, RC, software release | RWF | Software candidate identities and promotion |
| Repository/CI security boundaries | RWF | Protected production enforcement is deferred |
| Development-ticket acceptance requirements | RWF | Required for closing/verifying actual work |
| Project objectives, roadmap hierarchy | PWF | Organizational, not executable edges |
| Project milestones and phase acceptance | PWF | Aggregates evidence from multiple activities |
| Project specification baselines/amendments | PWF | Project-level change control; not Git release authority |
| Cross-repository programme coordination | PWF | References each source without owning its Git state |
| Project-level dashboards and reporting | PWF | Derived status; no duplicate evidence authority |
| Provider sync/offline projections | Each, at own boundary | Reuse patterns, don't couple internal stores |

RWF may consume a development requirement supplied by a project-management
platform; it does not need that platform's roadmap model to execute it.
PWF may reference RWF development tickets, but must not reinterpret or edit
their dependency edges as an incidental effect of phase organization.

## Initial integration contract

Start **read-only**: PWF may query RWF's provider-neutral view of ticket IDs
and work status, dependency/readiness summaries, verified candidate SHAs,
test/build outcomes and evidence identifiers, integration and release records,
including freshness and unavailable/INCOMPLETE states.

RWF must not import PWF code, schema or runtime as a dependency. PWF may
later request creation of development tickets only through RWF's established
authorization and mutation interfaces as a separate approved feature.

Authoritative facts stay with their original owners: Git owns source ancestry,
ticket provider owns ticket identity/title, RWF work/lifecycle stores own
development transitions, test/build/CI providers own execution readbacks,
repo-version adapter owns consumer literal version operations, and project
governance owns scoped project approvals. Neither component can infer
approval merely from an offline flag, closed ticket or passing CI.

If offline support is implemented for PWF, use explicit synchronization,
compare/merge/revision checking and stale-snapshot indications, analogous
to RWF TICKET_STATE.md, without merging project hierarchy into RWF's
executable dependency graph.

## Scope test for new proposals

Ask: **Would developers need this to complete repository work reliably if
no project roadmap system existed?**

- Yes: RWF, subject to an actual user/workflow contract.
- No, primarily concerns outcomes, programme-level decisions or milestones:
  candidate PWF scope.
- Both: keep the underlying execution/evidence authority in RWF and expose
  the smallest stable interface needed by PWF; do not duplicate state.

Apply this test to every proposed CLI command, state field and ticket.
Shared display does not imply shared mutation authority.

## Disposition of existing roadmap work

| Existing issues | Proposed disposition |
| --- | --- |
| #648 roadmap umbrella | Retain as boundary/roadmap planning record; mark generalized roadmap engine as candidate PWF |
| #649 architecture and trust boundaries | Preserve RWF-relevant security and data-authority lessons; separate PWF-specific roadmap schema concerns |
| #650 read-only roadmap CLI | Hold as candidate PWF feature; do not make RWF lifecycle depend on it |
| #651 evidence-backed phase aggregation | PWF owns phase aggregation; RWF exposes evidence/read-only status |
| #652–#656 phase tickets | Preserve as **planning milestones for RWF development**, not proof that a generic roadmap engine belongs in RWF |
| #543, #579–#583, #641–#647 | Remain RWF operational/test/build/version capability work |
| #85 and #86 | Remain RWF; production protection stays deferred until separately authorized |

These are proposed classifications only. No tickets are closed, moved or
duplicated by this document, and no canonical graph relationships change.

## Current decision boundary

Recommended now: adopt the *conceptual ownership separation* for review,
keep the RWF waterfall as a useful planning instrument, and put a generic
`rwf roadmap` engine on hold pending explicit boundary approval.

Not decided: whether PWF needs a repository, executable CLI, independent
provider integration, local project records or separate deployment.
Do not start those initiatives merely because this document exists.

A later approval should identify this document's exact revision, reviewers,
scope and unresolved exceptions. **Approval of this boundary would still
not authorize a PR merge, new external project, privileged mutations or
security activation.**

## Navigation

- [RWF roadmap #648](https://github.com/Ma-XX-oN/RepoWorkflow/issues/648)
- [Phase 0 #649](https://github.com/Ma-XX-oN/RepoWorkflow/issues/649)
- [Development ticket state contract](TICKET_STATE.md)
- [Work graph methodology](WORK_GRAPH_METHODOLOGY.md)
- [Public RWF workflow](PUBLIC_WORKFLOW.md)
- [Waterfall capability audit](REMAINING_WORK_DECOMPOSITION_AUDIT.md)

## GitHub scope labels (triage, not transfer)

Existing roadmap tickets have been classified using GitHub labels:

- `scope:project-workflow`: #648 (general roadmap capability direction),
  #650 (roadmap read-only UI), #651 (project-phase evidence aggregation).
- `scope:shared-boundary`: #649 (joint authority, trust and split-design
  questions; RWF-specific invariants must remain with RWF).
- `scope:rwf-roadmap`: #652–#656 (milestone containers describing RWF's
  actual build/version/integration/security/consumer work, **not**
  requirements to implement a general roadmap engine in RWF).

These labels are a **classification of proposed ownership**, not completion,
approval, a dependency edge, an issue migration or creation of a PWF system.
Do not relabel the RWF leaf implementation issues just because they appear
in a phase. Preserve the issue descriptions and history. Once the boundary
is explicitly approved, provider-independent ownership and any actual
migration can be considered separately.
