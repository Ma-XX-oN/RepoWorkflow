# Umbrella-centred Git integration — proposed RWF contract

Status: **DESIGN ACCEPTED; NOT IMPLEMENTED OR VERIFIED** (accepted requirements, 2026-11-05).
This records accepted user requirements for subsequent implementation and tests.
Until implementation and verification, existing [PARENT_BRANCH_WORKFLOW.md](PARENT_BRANCH_WORKFLOW.md),
[RELATIONSHIP_GRAPH.md](RELATIONSHIP_GRAPH.md), [PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md),
and [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) describe current behaviour.
Do not treat this proposal as a deployed feature or silently change existing branch identities.

## Objective and boundaries

RWF owns branch creation, work-branch parent selection and integration.
An agent with a checkout uses `rwf`; an agent without a checkout invokes the
**same command semantics** through hosted `.ci/rwf`. This equivalence is
required for **all** RWF commands, not merely `issue start`. Agents must not
circumvent RWF by arbitrarily creating managed issue branches. Server-side
permissions/rules must enforce this boundary as far as the provider permits;
client validation alone does not prevent direct Git pushes.

An umbrella is an **integration branch**. A ticket with an exact title prefix
`Initiative:`, `Epic:`, or `Feature:` is an umbrella. This is an
intentional **change from the current descriptive-only prefix contract**;
implementation must revise the affected authoritative documents and tests.

The authoritative *direct dependency DAG* remains unchanged as a graph.
Traversing its **dependant** direction from ticket T identifies all reachable
qualifying umbrella tickets. Follow **all** paths; do not discard a reachable
umbrella because another is closer. No new graph, membership database, or
dependency edges are needed merely to select a Git integration parent.
Git identity records the selected parent and preserves it even if the DAG
or ticket titles subsequently change.

## Umbrella starts versus umbrella work

`rwf issue start <ticket-id>` **must reject a direct start** when the
requested ticket is an umbrella (title begins with `Initiative:`,
`Epic:`, or `Feature:`). The rejection is read-only: no branch, identity
commit, claim or ticket-state mutation. For example, `rwf issue start 660`
fails when #660 is an umbrella.

Umbrella integration branches are **automatically created or reused** while
starting a subordinate implementation ticket. Creating the necessary parent
branch does not count as directly starting the umbrella. Existing umbrella
branches remain usable: authorized workers may switch/check out an umbrella
branch to integrate accepted child changes, resolve conflicts, run tests and
perform the existing completion/PRELIM workflow. **Do not introduce an
`rwf issue integrate` command**; existing RWF operations cover these tasks.
A worker may also create the subordinate work branch directly from the
verified umbrella commit without checking out the umbrella first.

An umbrella with no subordinate implementation ticket remains a planning
container without an automatically created work branch until a subordinate
ticket is started. This policy does not forbid reading or planning the
umbrella ticket.

## Starting a ticket and building its integration hierarchy

A worker normally invokes `rwf issue start <ticket-id>`. RWF must validate
the **complete unique umbrella integration path** before creating or
modifying branches, claims or ticket state. Umbrella branches are created
or reused in **outermost-to-innermost** order, followed by the requested
ticket branch. An intermediate non-umbrella dependency ticket does not
become an integration branch.

For a ticket whose reachable DAG contains exactly one applicable integration
path, resolve it automatically. For multiple qualifying umbrellas or any
ambiguity at an ancestor level, require explicit resolution, e.g.
`rwf issue start 785 --parent 660`. The supplied parent must be an eligible
umbrella. Existing accepted ownership/branch identity must not be silently
reassigned.

An umbrella selection at one level must also resolve its own containing
umbrella hierarchy. If that higher-level path is ambiguous, report the
specific ambiguous ticket and its choices before changing Git state.

Illustrative dependency DAG (arrows here mean *is required by*, toward
dependants; `E`, `F`, `I` are ticket-title umbrella classifications):

```text
785 +- E660 - 55 - I222
    ^
786 +- 799 - F700
```

For `rwf issue start 786 --parent 660`, the required Git branch-parent
hierarchy is:

```text
main
  \-- issue-222-...
        \-- issue-660-...
              \-- issue-786-...
```

The #55 intermediate dependency does **not** become a branch in that hierarchy;
the alternative #700 umbrella does not become the implementation parent.
This hierarchy, not merely the final `--parent` argument, must be resolved
and validated before mutating Git. The graph itself remains a DAG and is
**not modified** by the parent-selection action.

If no qualifying umbrella exists, the ticket is standalone: create its work
branch from `main`, and its eventual manual PRELIM candidate comes from its
own accepted ticket result. Do not choose an arbitrary currently checked-out
leaf branch.

## Ambiguity diagnostics and completion

If a new ticket has multiple eligible umbrellas and no established parent,
the command fails **without side effects**, listing all eligible umbrella
ticket IDs with their **exact current ticket titles**, sorted numerically:

```text
$ rwf issue start 785
ERROR: Ticket 785 is under multiple umbrella tickets:

  660 - <actual title of ticket 660>
  700 - <actual title of ticket 700>

Add `--parent <umbrella-ticket-id>` to specify which umbrella owns integration.
```

The example angle-bracketed titles above are explanatory placeholders, not
literal runtime output. Do not invent ticket titles.

Bash completion for `rwf issue start 785<Tab>` offers `--parent` **only
when that ticket has unresolved ambiguity**. Completion for
`rwf issue start 785 --parent <Tab>` displays the eligible IDs with their
exact titles and inserts only the selected ID; prefix filtering applies.
The command and completion must share the identical candidate-resolution
logic. Completion is read-only. Ambiguities involving ancestor umbrellas
must similarly identify the particular ticket and available choices.

## One implementation serving multiple umbrellas

A ticket can be reachable from more than one umbrella. It is **implemented
once**, with **one** canonical Git work branch and one semantic integration
parent. The first successful authoritative ownership establishment determines
that parent. Other umbrellas consume the implementation via the owning
umbrella's accepted outcome/dependency; they do not independently implement
the same ticket or need a second alias branch. Any dependency relationships
must remain governed by the DAG's existing authority; selecting a Git parent
must **not automatically add dependency edges**.

Requirements for shared work are reconciled across **all** consuming
umbrellas before acceptance: preconditions, postconditions and invariants
must be logically compatible and satisfied; conflicting requirements require
resolution. Acceptance tests must verify the unified contract, including
negative cases. Added requirements after acceptance require explicit
revalidation, not silent reinterpretation.

## Parallel agents, worktrees, offline reconciliation

Distinct child tickets may start concurrently from the same canonical
umbrella commit and develop in parallel, including bounded authorised
speculative work. Each has its own child branch/worktree; no agent needs to
check out the umbrella branch to create a child from its verified commit.
A shared Git repository prevents two worktrees from checking out the same
branch at once. Distinct clones do not share that protection.

The canonical umbrella branch is created once. A concurrent claimant must
reuse and validate the existing remote branch rather than overwrite it.
Publishing/integrating must use atomic, expected-tip, non-force Git ref
updates, and integration updates into one umbrella are serialized.
An existing branch's recorded parent is not changed by a later DAG edit.

Offline agents can independently create divergent histories even when they
begin at the same main commit, because separately generated identity commits
may differ. On synchronization, preserve all work, choose the authoritative
umbrella identity through explicit recovery, import the other child changes
without rewriting that canonical identity, and rerun applicable acceptance
against the reconciled source. Do **not** silently force-push or claim that a
Git merge alone establishes RWF acceptance.

## Verification and release gates

Test local and hosted `.ci/rwf` behaviour for equivalent command semantics,
validation, output and exit codes; test ambiguity, tab completion, multi-level
paths, graph diamonds and non-nearest umbrellas, standalone tickets, wrong
parent requests, branch reuse, shared worktrees, concurrent remote creates,
offline divergence, stable parent identity after DAG changes and negative
side-effect assertions. Use applicable native Linux/macOS/Windows verification.

Accepted child work integrates back into the **owning umbrella** branch. The
umbrella's exact assembled result must be verified before its manual PRELIM
candidate. PRELIM acceptance/promotion to `main` remains subject to separate
documented gates; this design does not authorize direct leaf-to-`main` merges.

## Pending implementation questions (do not guess)

- Define the exact deterministic integration-path choice and CLI syntax when
  multiple **ancestor** levels are ambiguous, including which level
  `--parent` resolves and how additional choices are supplied.
- Specify globally authoritative ownership claim semantics across clones
  without treating a local worktree claim as a distributed lock.
- Determine how server branch protections and permitted permissions enforce
  exclusive RWF-managed branch creation.
- Identify migration/recovery rules for historical work branches whose
  parent topology differs from this proposed model; preserve their existing
  identity markers without silent history rewrites.
