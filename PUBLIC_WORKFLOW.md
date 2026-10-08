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
│   ├── <ISSUE...> dependency to-tickets [--compare|--replace]
│   ├── <ISSUE...> dependency from-tickets
│   │   [--compare|--replace|--replace-title|--replace-dependencies]
│   ├── start N
│   └── abort
├── tdd
│   ├── red group NAME
│   └── green
├── high-risk <SECTION> [<SECTION> ...]
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

Dynamic positions follow the provider contracts in
[COMMAND_GRAMMAR.md](COMMAND_GRAMMAR.md).  Simple quantified `_values`
completion functions return lists of completion strings.  State-projection
positions that require described fragments or custom Tab behaviour use the
explicit completion-specification extension with optional `on-tab`.

A custom `on-tab` handler remains the extension point for
shell/presentation behaviour and contextual diagnostics.  The semantic command
grammar therefore does not hard-code Bash-specific insertion behaviour.

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

## 4. High-risk verification sections

`rwf high-risk <SECTION> [<SECTION> ...]` associates one or more semantic
test-catalogue alias sections from `.ci/tests.json` with the active current
issue.

All requested section names are validated before durable mutation.  Repeated
invocation is idempotent, changed invocation unions with the existing set, and
the normalized association is stored with the issue lifecycle record.  The
command reports the complete attached alias set after success.

Completion for the positional SECTION values comes from the catalogue alias
names.  Help uses the same grammar/completion source.  A future general
`rwf status` implementation must include these lifecycle-owned associations;
the association is not duplicated into a separate status store.

High-risk sections add targeted issue-verification coverage.  They never replace
the issue's own required groups and do not by themselves imply complete
regression or integration evidence.

## 5. Repository-owned adapters

RepoWorkflow owns workflow semantics; consumer repositories own facts and
provider-specific mechanics through explicit adapters.

The intended adapter families are:

```text
repo-version
repo-info
repo-ci
```

### 5.1 repo-version

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

### 5.2 repo-info

`repo-info` supplies repository/issue information without teaching core RWF
GitHub/`gh` or another forge's API.

It powers `rwf issue info`, issue-number/title completion, and issue
validation at start time.

Issue #53 owns this adapter and issue commands.

### 5.3 repo-ci

Repository/CI-provider mechanics belong behind a portable adapter boundary.
RWF owns candidate identity, required test coverage, legal transitions,
PASS/FAIL/INCOMPLETE semantics, evidence validity, and authorization/current
base requirements.

The adapter owns environment/runner provisioning, repository-specific
validation execution, artifact transport/materialization, result transport, and
provider event interpretation.

GitHub Actions is one provider implementation, not the workflow model.

Issue #55 owns this migration.

## 6. Issue workflow

```text
rwf issue info
rwf issue info N
rwf issue list
rwf issue list --links
rwf issue list 54 64 9
rwf issue list 54 64 9 --links
rwf issue 54 dependency from-tickets
rwf issue 54 64 9 dependency from-tickets
rwf issue 54 64 9 dependency to-tickets
rwf issue start N
rwf issue abort
```

`issue info` and `issue list` read repository issues through `repo-info`.
Explicit dependency synchronization accepts one or more ticket numbers and
synchronizes title and direct dependencies together as defined by
[TICKET_STATE.md](TICKET_STATE.md).

The ticket server is always authoritative for titles. `to-tickets` requires
an exact title match before mutating provider dependencies.

Ticket creators use `Initiative:`, `Epic:`, and `Feature:` prefixes when
they improve navigation. These prefixes are descriptive only and have no RWF
workflow semantics.

`issue start N` establishes work on issue N. Branch-parent identity is
recorded in Git history; it is not stored in ticket relationship state.

`issue abort` stops active work without pretending the issue completed and
without discarding durable evidence/history.

## 7. Dependencies, lanes, and multiple agents

Lane planning uses only explicit direct ticket dependencies:

```text
rwf lanes select <issues...>
rwf lanes list
rwf lanes view
```

The issues passed to `lanes select` are explicit focus seeds.  Without a
`--follow` option, ordinary dependency/dependant traversal does not start and
the projected lane selection contains only those explicit seeds.  Only the
explicit focus seeds receive the `*` marker.  Dependency direction itself is
unchanged: direct dependency edges remain the sole scheduling and topology
authority.

`--follow` is the general traversal-enabling mechanism:

```text
--follow group [N]
--follow feature [N]
--follow epic [N]
--follow initiative [N]
```

Supplying any valid form above enables ordinary traversal through both direct
dependencies and direct dependants.  Encountered `Feature:`, `Epic:`, and
`Initiative:` tickets are included but stop traversal unless the applicable
follow allowance permits crossing them; an explicitly selected group seed is
not stopped merely because it is a group.

`N` defaults to 1 and must be positive.  Type-specific allowances compose and
are counted independently per traversal path.  `group N` uses one shared
per-path allowance across Feature/Epic/Initiative boundaries.  The same node may
therefore be visited with different remaining traversal allowances while still
appearing only once in the projected graph.

Stopped group boundaries may expose one adjacent context layer with
`--show-children group|feature|epic|initiative`.  This option does not itself
enable ordinary traversal.  It applies only to matching unfollowed boundaries
already present in the projected graph: shown nodes do not restart traversal,
while an independent followed path to the same node remains traversable.  Repeated type flags compose;
`group` matches Feature/Epic/Initiative.

The durable synchronized ticket state contains issue number, exact title, and
direct dependencies. Repeated lane operations use that local state. A missing
ticket is acquired from the configured provider, including title and direct
dependencies. `--refresh` explicitly rereads the relevant provider closure.

RepoWorkflow does not store a second relationship graph for container
ownership, membership, or attachment. Branch-parent identity is also outside
the ticket graph.

Initiative/Epic/Feature tickets are human-facing containers. Their prefixes do
not create ownership or scheduling relationships. Executable ordering is
represented only by direct dependency edges.

If #102 cannot proceed until #101 produces a required result, #102 depends
directly on #101. If several tickets have no dependency path between them, they
may proceed concurrently.

Branch ancestry is independent of dependency topology. A branch parent is
recorded and recovered from Git history under
[PARENT_BRANCH_WORKFLOW.md](PARENT_BRANCH_WORKFLOW.md).

The synchronized state, synchronization directions, conflict rules, and
ticket-creation workflow are defined by [TICKET_STATE.md](TICKET_STATE.md).
Repository-neutral decomposition guidance remains in
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md).

## 8. Optional TDD workflow

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

## 9. Reusable validation evidence

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

## 10. Validation commands

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

### 10.1 CI validation tiers

Hosted Self CI uses the same validation hierarchy:

- issue PRs run the issue-owned catalogue groups, durable high-risk alias
  groups, and cheap invariant groups;
- regression runs broad repository validation without the integration-only
  platform matrix;
- integration runs broad validation plus the authoritative platform/provider
  matrix;
- documentation-only changes retain the fast path.

Regression is selected explicitly when a dependency-complete umbrella outcome
is ready or when broader risk warrants it.  RepoWorkflow does not infer
umbrella semantics from Initiative/Epic/Feature title prefixes.

Authoritative `main` pushes are always integration candidates.  CI emits the
selected tier, groups, and reason so narrower evidence cannot be mistaken for a
stronger gate.

## 11. Status and guidance

`rwf status` answers where the current workflow stands: issue/context,
branch/version identity, TDD/ART/AIT/MIT evidence, blockers, and relevant
relationships.

`rwf what-next` answers which state transitions are legal now.

Both derive from the same state/evidence model used by completion.

Issue #58 owns alignment of these commands and removal of obsolete public
commands.

## 12. Commit/push remains Git

Normal source work remains normal Git work:

```text
git add ...
git commit ...
git push
```

RepoWorkflow does not replace ordinary source editing/commit commands unless a
specific workflow invariant requires an owned operation.

## 13. Completing work

```text
rwf done patch
rwf done minor
rwf done major
```

`done` means complete the current issue using the selected
integration/release intent.

Before completion, RWF verifies the required TDD, complete ART, AIT/MIT,
candidate cleanliness/identity, current base, and authorization evidence.

The completion target is the work branch's Git-native parent identity recovered
from branch history. It is not stored in ticket relationship state.

Patch/minor/major are semantic intents.  RWF calls `repo-version` internally.

Major completion may require stronger explicit authorization; the precise
authorization representation/lifetime is part of the state-schema/integration
design.

Issue #56 owns the public `done` workflow.  Existing #17 owns prelim
integration/reintegration/PRELIM mechanics and #18 owns protected-server
enforcement.

## 14. Existing lower-level work

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

## 15. Remaining design work

The major unsettled details are tracked explicitly rather than hidden in this
synopsis:

- exact durable/shared versus clone-local `.repoworkflow/` schema (#57);
- multi-agent active-work representation (#57);
- synchronized ticket-state and direct-dependency representation (#57);
- authorization representation/lifetime (#56/#57);
- exact `done patch|minor|major` integration transitions (#56);
- test-evidence fingerprint/invalidation rules (#16);
- portable `repo-ci` adapter contract (#55).

These items must be documented and RED-tested before their production
implementation.
