# RepoWorkflow Public Workflow

Status: authoritative public-workflow synopsis for issue #51.

This document defines the intended human-facing `rwf` workflow.  It supersedes
older public-command proposals in closed issues #14/#15 while preserving useful
lower-level implementation machinery behind internal/adapter boundaries.

## 1. Public command surface

```text
rwf
├── init
│   ├── local-only
│   ├── bash
│   ├── zsh
│   └── ...
├── status
├── what-next
├── issue
│   ├── info [N]
│   ├── list [<ids...>] [--links]
│   ├── select dependency to-tickets [--compare|--replace]
│   ├── select dependency from-tickets [--compare|--replace]
│   ├── start N
│   └── abort
├── tdd
│   ├── red group NAME
│   └── green
├── validate
│   ├── regression [--fast] [--group NAME]
│   └── integration [--automatic|--manual] [--group NAME]
│       ├── succeeded
│       └── failed
└── done
    ├── patch
    ├── minor
    └── major
```

`repo-workflow` and `rwf` are aliases over the same state machine and command
grammar.

The normal public surface does not include `rwf version`,
`publish-validation`, `verify-release`, or CI/provider plumbing such as
`preflight`, `run`, `finalize`, and `github-*`.  Required lower-level
capabilities may remain temporarily available to machine callers while their
adapter replacements are implemented.

## 2. Help and completion

The authored command grammar is the single source for parsing, completion,
diagnostics, double-Tab descriptions, and `--help`.

`--help` is valid after every valid command prefix.  It exposes the same
semantic descriptions as double-Tab completion, with normal help formatting.

First Tab performs ordinary completion or a contextual completion diagnostic.
A second Tab at the same completion point renders descriptions/details.

Dynamic `_values` providers use one explicit result contract:

```python
{
  "completions": [...],
  "on-tab": completion_handler,
}
```

`on-tab` is optional; absence means the default completion handler.  Provider
semantics must not depend on whether Python happened to return a string,
`list[str]`, described fragments, or another shape.

A custom `on-tab` handler is the extension point for shell/presentation
behaviour and contextual diagnostics.  The semantic command grammar therefore
does not hard-code Bash-specific insertion behaviour.

Completion and diagnostic paths are read-only, preserve the literal typed
input, and identify the first failing token.  Static parsing, help, and syntax
diagnostics run before workflow-configuration discovery so an uninitialized
checkout can still explain its public command surface.

Issue #52 owns implementation of this contract.

## 3. Repository initialization

The canonical state directory is:

```text
.repoworkflow/
```

Normal initialization is:

```text
./RepoWorkflow/rwf init
```

It initializes the repository's RepoWorkflow state/integration.  If
`.repoworkflow/` already exists, initialization aborts rather than silently
acting idempotently.

A local-only installation is:

```text
./RepoWorkflow/rwf init local-only
```

This is for repositories that are not ready or willing to adopt RepoWorkflow
officially.  The complete RWF footprint remains clone-local and should be
excluded through local Git mechanisms such as `.git/info/exclude`, not by
editing committed `.gitignore`.

After successful repository initialization, RWF explains the optional
shell-specific stage, for example:

```bash
source <(rwf init bash)
source <(rwf init zsh)
```

`rwf init bash`, `rwf init zsh`, etc. emit shell-specific initialization
source.  Shell-specific command discovery/completion belongs there rather than
in the platform-neutral Python workflow model.

`--force` is not part of the intended init interface.

Issue #27 owns implementation.

## 4. Repository-owned adapters

RepoWorkflow owns workflow semantics; consumer repositories own facts and
provider-specific mechanics through explicit adapters.

The intended adapter families are:

```text
repo-version
repo-info
repo-ci
```

### 4.1 repo-version

RWF invokes semantic version operations internally.  Users do not normally
invoke version transitions through `rwf`.

Examples of internal semantic requests include:

```text
task --issue N
task --increment CI-iteration
task --increment merge-integration-failed
integrate --increment patch
integrate --increment minor
release-major
```

The consumer adapter derives and applies literal versions.

### 4.2 repo-info

`repo-info` supplies repository/issue information without teaching core RWF
GitHub/`gh` or another forge's API.

It powers `rwf issue info`, issue-number/title completion, and issue
validation at start time.

Issue #53 owns this adapter and issue commands.

### 4.3 repo-ci

Repository/CI-provider mechanics belong behind a portable adapter boundary.
RWF owns candidate identity, required test coverage, legal transitions,
PASS/FAIL/INCOMPLETE semantics, evidence validity, and authorization/current
base requirements.

The adapter owns environment/runner provisioning, repository-specific
validation execution, artifact transport/materialization, result transport, and
provider event interpretation.

GitHub Actions is one provider implementation, not the workflow model.

Issue #55 owns this migration.

## 5. Issue workflow

```text
rwf issue info
rwf issue info N
rwf issue list
rwf issue list --links
rwf issue list 54 64 9
rwf issue list 54 64 9 --links
rwf issue start N
rwf issue abort
```

`issue info` lists/reads repository issues through `repo-info`.

`issue list` with no IDs lists all open issues.  With explicit IDs, it
displays the requested issue numbers and titles in supplied order.  `--links`
additionally includes the provider-neutral canonical issue link returned by
`repo-info`; core RWF does not construct provider URLs.

Single Tab completes matching open issue numbers.  Double Tab lists matching
issue numbers and titles.  A typed prefix filters the same source.

`issue start N` establishes work on issue N.  It verifies the issue through
`repo-info`, records who/what started it, invokes `repo-version` for the
issue-qualified task state, creates/verifies the work branch, and records the
explicit workflow relationships needed for later integration.

The start path should display the resolved relationships, for example:

```text
Starting issue #101

  umbrella:    #100  Parser refactor
  branch base: #98   Token stream API
  new branch:  issue-101-tokenizer-state
```

`issue abort` stops active work without pretending the issue completed and
without discarding durable evidence/history.

## 6. Umbrellas, dependencies, and multiple agents

Lane planning may begin directly from ticket-native dependency facts:

```text
rwf lanes select <roots...>
rwf lanes list
rwf lanes view
```

`lanes list` is the lane-membership inventory with issue titles and optional
links.  `lanes view` is the compact dependency topology.  Selection mutations
also render the topology after success.

Lane inspection uses synchronized local state by default; `--refresh`
explicitly rereads the relevant provider closure.  Cache and refresh rules are
in [LANE_CACHE_REFRESH.md](LANE_CACHE_REFRESH.md).  Display rules are in
[LANE_GRAPH_DISPLAY.md](LANE_GRAPH_DISPLAY.md).
When no canonical relationship graph exists yet, the first selection acquires
the complete dependency closure through the repository dependency adapter,
validates it, and creates the canonical RWF graph before decomposition.

An umbrella issue groups work that contributes to one larger problem or goal.
It is not itself a dependency edge and it is not a shared execution stack.

Sibling issues beneath one umbrella may have no ordering relationship at all.
Several agents may therefore work on those siblings concurrently.

RepoWorkflow models only explicit **direct issue dependencies** for ordering.
If issue #102 cannot proceed until #101 produces a required result, #102
directly depends on #101.  If #101 and #102 are merely related because both
contribute to umbrella #100, neither depends on the other.

An apparent indirect dependency is a decomposition signal rather than a
workflow relationship to preserve.  Work should be broken down until every
real ordering constraint can be represented by direct dependency edges.

Decompose an issue when more than one task is required to satisfy that issue's
outcome.  The original issue remains the umbrella for those child tasks because
their completion collectively satisfies the original target.

During decomposition, prerequisite work may be discovered that is useful to
multiple otherwise unrelated issues or umbrellas.  It does not become a child
of whichever consumer discovered it first.

A single shared prerequisite may remain an independent issue.  If the shared
capability itself requires several interface or implementation tasks, those
tasks belong under their own **shared capability umbrella**.  Consumer
umbrellas attach to that shared capability umbrella rather than duplicating or
multi-parenting its child issues.  Executable ordering still uses explicit
direct dependency edges to the specific leaf interfaces each consumer needs.

RepoWorkflow distinguishes four graph relationships:

- **child ownership**: a leaf or sub-umbrella contributes to one owning
  umbrella outcome;
- **shared-capability attachment**: a consumer umbrella uses a reusable
  subsystem owned by another umbrella; attachment alone creates no ordering;
- **direct leaf dependency**: one executable task requires another exact task
  interface or transition first;
- **direct umbrella dependency**: one complete umbrella outcome cannot be
  complete until another complete umbrella outcome is complete.

A direct umbrella dependency is a high-level roadmap relation, not a
replacement for leaf dependencies.  Record it only when the whole prerequisite
umbrella is required, not merely because one child consumes one child from
another umbrella.  The umbrella-dependency graph should omit edges already
implied transitively by other umbrella dependencies.

For example:

```text
#104  Define parser API
├── #101 Tokenizer     depends on #104
├── #102 Diagnostics   depends on #104
└── #103 Benchmarks    depends on #104
```

Before #104 completes, #101/#102/#103 are blocked.  After #104 completes,
those three issues are independently ready and may run in parallel.  If #105
depends on both #101 and #102, it remains blocked until both direct
dependencies complete.

The durable model must therefore distinguish:

- owning umbrella/grouping relationship;
- shared-capability umbrella attachment;
- explicit direct leaf-dependency edges;
- explicit direct umbrella-dependency edges;
- branch/dependency base;
- integration target;
- clone/agent-local current work context.

A branch based on another issue does not imply an issue dependency, and neither
branch ancestry nor umbrella membership may be used to infer dependency edges.

This direct dependency graph provides scheduling information as well as safety:
RWF can determine which issues are ready now, which are blocked, and which
ready issues can be worked in parallel.

One shared mutable active-issue stack is therefore not authoritative workflow
state.  A local navigation/context stack may exist, but it cannot serialize or
overwrite other agents' work.

Issue #57 owns the exact durable/local schema.  The repository-neutral method
for decomposing issues, extracting shared capabilities, defining leaf
contracts, and deriving executable scheduling is maintained in
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

## 7. Optional TDD workflow

```text
rwf tdd red group NAME
rwf tdd green
```

For active issue N, TDD group names must already exist in the repository's test
catalogue/Rosetta mapping and follow `issue-N-...`.

`rwf tdd red group <TAB>` completes only groups for the active issue.  Normal
completion may insert the shared `issue-N-` prefix when several groups match.

A custom `on-tab` handler may provide specific actionable diagnostics when no
group for the active issue exists or a different issue's group is selected.
The diagnostic should identify the expected naming rule and the catalogue or
configuration location that must be changed.

Double Tab and `--help` explain command usage, naming rules, and catalogue
location; they do not merely repeat a contextual runtime error.

RED runs the selected group and records RED only when the documented RED
expectations are satisfied.  GREEN runs the issue's required TDD groups that
are not already satisfied by reusable unchanged evidence.

Issue #54 owns this command family.

## 8. Reusable validation evidence

Workflow gates are based on whether every required test unit is satisfied for
the current effective candidate/input fingerprint, not on whether one broad
command happened to run.

This applies to:

- TDD groups;
- ART groups;
- `--fast` ART subsets;
- complete ART;
- AIT;
- MIT/manual evidence;
- integration groups/subsets.

A broader successful run may satisfy narrower requirements.  Several narrower
runs may collectively satisfy a broader gate.

For example, unchanged PASS evidence from A/B through `--fast`, C through a
group run, and D through another run may collectively satisfy complete ART when
A+B+C+D are the required ART set.

`--fast` alone does not imply complete ART merely because it passed.

Relevant source/configuration/catalogue/capability changes invalidate affected
evidence according to a deterministic fingerprint contract.

Issue #16 owns durable evidence, reuse, invalidation, and local/hosted-provider
equivalence.

## 9. Validation commands

Regression:

```text
rwf validate regression
rwf validate regression --fast
rwf validate regression --group NAME
```

Integration:

```text
rwf validate integration
rwf validate integration --automatic
rwf validate integration --manual
rwf validate integration --group NAME
rwf validate integration --group NAME --automatic
rwf validate integration --group NAME --manual
rwf validate integration succeeded
rwf validate integration failed
```

A manual integration result may only resolve an actual pending manual test
requirement.  Automated integration runners may record their own results.

Partial validation contributes reusable evidence but does not bypass missing
required coverage.

## 10. Status and guidance

`rwf status` answers where the current workflow stands: issue/context,
branch/version identity, TDD/ART/AIT/MIT evidence, blockers, and relevant
relationships.

`rwf what-next` answers which state transitions are legal now.

Both derive from the same state/evidence model used by completion.

Issue #58 owns alignment of these commands and removal of obsolete public
commands.

## 11. Commit/push remains Git

Normal source work remains normal Git work:

```text
git add ...
git commit ...
git push
```

RepoWorkflow does not replace ordinary source editing/commit commands unless a
specific workflow invariant requires an owned operation.

## 12. Completing work

```text
rwf done patch
rwf done minor
rwf done major
```

`done` means complete the current issue using the selected
integration/release intent.

Before completion, RWF verifies the required TDD, complete ART, AIT/MIT,
candidate cleanliness/identity, current base, and authorization evidence.

The integration target comes from explicit recorded workflow relationships,
not from a local navigation stack or merely Git ancestry.

Patch/minor/major are semantic intents.  RWF calls `repo-version` internally.

Major completion may require stronger explicit authorization; the precise
authorization representation/lifetime is part of the state-schema/integration
design.

Issue #56 owns the public `done` workflow.  Existing #17 owns prelim
integration/reintegration/PRELIM mechanics and #18 owns protected-server
enforcement.

## 13. Existing lower-level work

The revised public workflow reuses rather than discards existing lower-level
mechanisms where they still satisfy the new architecture:

- #5 — authoritative candidate bookkeeping and terminal tagging;
- #16 — validation evidence and reuse;
- #17 — prelim integration/reintegration/PRELIM tags;
- #18 — protected server enforcement;
- #19 — local Git guards;
- #27 — initialization.

Internal commands may remain temporarily for machine compatibility, but they
must not define the normal human-facing workflow or force GitHub-specific
semantics into the portable engine.

## 14. Remaining design work

The major unsettled details are tracked explicitly rather than hidden in this
synopsis:

- exact durable/shared versus clone-local `.repoworkflow/` schema (#57);
- multi-agent active-work representation (#57);
- direct dependency and umbrella/grouping representation (#57);
- authorization representation/lifetime (#56/#57);
- exact `done patch|minor|major` integration transitions (#56);
- test-evidence fingerprint/invalidation rules (#16);
- portable `repo-ci` adapter contract (#55).

These items must be documented and RED-tested before their production
implementation.
