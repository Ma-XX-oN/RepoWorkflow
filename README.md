# RepoWorkflow

RepoWorkflow provides the shared, platform-independent repository workflow for
CI, branch policy, validation, generated artifacts, candidate bookkeeping, and
terminal result tagging. It is consumed as a Git submodule named `RepoWorkflow`
in each repository.

[REPOWORKFLOW_OVERVIEW.md](REPOWORKFLOW_OVERVIEW.md) explains the broader RWF
model: what it is, the engineering disciplines it combines, and how those
ideas improve decomposition, testing, scheduling, integration, and completion.

The central boundary is:

> GitHub workflow YAML is only a bootstrap. Repository workflow logic must remain
> executable locally and on other CI platforms.

A consumer is structured broadly as:

```text
Project/
├── RepoWorkflow/               # submodule pinned to an exact commit
├── .ci/                        # repository-specific declarations
├── .github/workflows/ci.yml    # tiny stable reusable-workflow handoff
├── scripts/repoworkflow.py     # tiny stable local pin launcher
├── scripts/                    # repository-specific operations
└── tests/
```

## Runtime dependencies

Install the supported Python runtime dependencies after cloning or updating
RepoWorkflow:

```text
python -m pip install -r requirements.txt
```

The terminal styling adapter uses the declared capability-aware backend.
`rwf settings color always` fails explicitly when that backend is unavailable;
it never silently degrades to uncoloured output.  `color auto` may remain
unstyled when styling is unavailable or inappropriate for the output stream.

## Responsibilities

RepoWorkflow owns common lifecycle and invariant machinery:

- `.ci/run-ci-request` candidate binding and refresh;
- automatic development-iteration advancement after a consumed terminal result;
- authoritative remote terminal-tag checks;
- exact-candidate and clean-checkout validation;
- PASS / FAIL / INCOMPLETE semantics and result aggregation;
- branch-parent/dependency-history policy;
- canonical GitHub-workflow/repository policy;
- generated-artifact output and verifier safeguards;
- automatic terminal result tagging for authoritative local development verify;
- serial/parallel orchestration helpers.

Each consumer owns repository/provider-specific facts and operations through
explicit adapters, including `repo-version`, `repo-info`, and `repo-ci`.
Those adapters own semantic version application, issue/repository information,
repository-specific validation, provider execution/transport, builds,
packaging, artifacts, and declared platform/capability mechanics.

## Pinned local engine

The superproject gitlink is the authoritative RepoWorkflow identity. Consumers
install `templates/local/repoworkflow.py` as `scripts/repoworkflow.py`. This
small launcher runs before any submodule engine code is trusted.

The normal command is:

```text
python scripts/repoworkflow.py verify
```

The launcher performs only local Git reads first:

1. read the expected RepoWorkflow commit from `HEAD:RepoWorkflow`;
2. read the current `RepoWorkflow` checkout HEAD;
3. if they match, immediately delegate to the pinned engine without a submodule
   update or network repair;
4. if the checkout is missing or mismatched, run the exact submodule repair,
   verify the resulting HEAD equals the gitlink, and only then delegate.

An explicit repair can be forced even when the checkout currently matches:

```text
python scripts/repoworkflow.py --force-repair verify
```

The repair operation is:

```text
git submodule update --init --recursive --force RepoWorkflow
```

It is therefore exceptional rather than part of every test run.

## GitHub bootstrap and reusable workflow

GitHub must discover a workflow file in the consumer repository before checkout,
so every consumer retains a tiny stable `.github/workflows/ci.yml`. It contains
only event declarations and a reusable-workflow handoff to:

```text
Ma-XX-oN/RepoWorkflow/.github/workflows/consumer-ci.yml@bootstrap-v1
```

The large hosted implementation lives once in RepoWorkflow. The reusable
workflow checks out the consumer recursively, which materializes the exact
RepoWorkflow gitlink pinned by that candidate, and repository policy verifies
that the checked-out engine HEAD equals that gitlink before validation.

`bootstrap-v1` is the stable handoff contract. Normal RepoWorkflow releases do
not require copying a large workflow into every consumer. A bootstrap-contract
change is therefore explicit and exceptional.

## Authoritative local verification

The normal local development workflow is one command:

```text
python scripts/repoworkflow.py verify
```

The launcher first establishes the pinned engine as described above. The engine
then owns candidate bookkeeping. The caller does not manually refresh
`.ci/run-ci-request`, reorder bookkeeping commits, or opt into terminal tagging.
Before validation, `verify` rebinds the request after ordinary source commits
when necessary. If the current development iteration is already consumed
remotely, RepoWorkflow invokes the repository-owned semantic version adapter
with `task --increment CI-iteration`, verifies that only `R` advanced by one,
and records the resulting version/request change in one bookkeeping commit.

A completed development result always creates a local terminal tag:

```text
PASS  -> v<version>
FAIL  -> v<version>-CI-FAIL
```

INCOMPLETE creates no terminal tag. `--push` additionally pushes RepoWorkflow's
bookkeeping/artifact commits and the resulting terminal tag to the authoritative
remote. The legacy `--tag` spelling is accepted for compatibility but is no
longer required for `verify`.

RepoWorkflow still requires a clean checkout before it performs bookkeeping;
source changes remain the caller's commits. The existing request-boundary guard
remains an invariant check for corruption or unsupported manual manipulation,
not normal workflow bookkeeping.

## Universal request guard

`.ci/run-ci-request` remains the exact-candidate binding used by distributed
execution and lower-level commands. Its development version must match the
repository's own semantic version adapter and ordinary source changes must not occur after
the request boundary. `verify` owns creating or refreshing that boundary during
normal local authoritative execution.

The authoritative remote must not already contain either terminal tag for the
candidate being validated:

```text
v<version>
v<version>-CI-FAIL
```

A terminal tag consumes that development iteration. If authoritative eligibility
cannot be established, execution is INCOMPLETE rather than a false PASS/FAIL.

## Result semantics

- complete required PASS => `v<version>`;
- complete genuine validation failure => `v<version>-CI-FAIL`;
- missing platform/capability/infrastructure/prerequisite => INCOMPLETE, no tag.

## Entry points

The intended human-facing interface is the Git-like `rwf` command family:

```text
rwf init
rwf status
rwf what-next
rwf issue ...
rwf tdd ...
rwf validate ...
rwf done ...
```

`repo-workflow` is an alias over the same state machine/grammar.

The full public workflow is defined in
[PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md).  Public `rwf version`,
`publish-validation`, and `verify-release` are not part of the intended
normal interface; version transitions are delegated internally to
`repo-version`.

Existing low-level validation/provider commands such as `preflight`, `run`,
`finalize`, and `github-*` are implementation plumbing retained only as
needed during migration.  Issue #55 moves provider-specific mechanics behind a
portable `repo-ci` boundary.

## Cross-repository management

RepoWorkflow defines repository-neutral workflow and work-graph semantics.
[WorkStack](https://github.com/Ma-XX-oN/WorkStack) is a separate
cross-repository manager that can consume those semantics to coordinate work,
dependencies, and durable lanes across multiple repositories.

RepoWorkflow does not define WorkStack's internal policy or data model; this
reference identifies the cross-repository layer that consumes RWF's generic
methodology.

## Documentation

- [REPOWORKFLOW_OVERVIEW.md](REPOWORKFLOW_OVERVIEW.md) explains what RWF is,
  what it improves, and how it combines established engineering disciplines.
- [DESIGN.md](DESIGN.md) defines the architecture and invariants.
- [COLLABORATIVE_DESIGN_REVIEW.md](COLLABORATIVE_DESIGN_REVIEW.md) defines
  a project-neutral discipline for evaluating design proposals against accepted
  invariants before extending them.
- [GRAPH_RENDERER.md](GRAPH_RENDERER.md) defines the constrained,
  project-neutral sibling-group DAG renderer used by lane graph display.
- [DOCUMENTATION_STRUCTURE.md](DOCUMENTATION_STRUCTURE.md) defines how size
  limits trigger concise rewrites or responsibility-based splits without
  losing authoritative semantics.
- [TEST_ADEQUACY.md](TEST_ADEQUACY.md) defines the universal repository-neutral
  test adequacy and verification gate applied to RepoWorkflow and consumers.
- [BUG_INVESTIGATION.md](BUG_INVESTIGATION.md) defines the required
  Problem/Hypothesis/Action/Learning experiment protocol for every bug
  investigation.
- [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) defines the
  repository-neutral method for decomposing issues into testable interfaces,
  direct dependency interfaces, and executable dependency graphs.
- [EXECUTABLE_INTERFACE_CONTRACTS.md](EXECUTABLE_INTERFACE_CONTRACTS.md)
  proposes deterministic executable interface contracts for parallel
  provider/consumer work, verification, and replay.
- [TICKET_STATE.md](TICKET_STATE.md) defines the canonical synchronized
  ticket file and the mandatory ticket-creation/dependency-recording workflow.
- [RELATIONSHIP_GRAPH.md](RELATIONSHIP_GRAPH.md) defines the versioned direct
  relationship schema, reconstruction rules, and executable readiness edges.
- [STATE_LAYOUT.md](STATE_LAYOUT.md) defines durable, clone-common, and
  worktree-local state ownership and path invariants.
- [STATE_CONCURRENCY.md](STATE_CONCURRENCY.md) defines durable mutation CAS,
  writer provenance, and concurrency invariants.
- [RUNTIME_IDENTITY.md](RUNTIME_IDENTITY.md) defines the provider-neutral
  writer/session invocation boundary for mutation-capable transitions.
- [WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md) defines the corresponding
  graph-testing, refinement procedure, and dependency acceptance checks.
- [WORKSPACE_MODEL.md](WORKSPACE_MODEL.md) defines repository-local workspace
  identity, lifecycle, claims, resume semantics, and cleanup invariants.
- [WORKTREE_BACKEND.md](WORKTREE_BACKEND.md) defines transactional local Git
  worktree provisioning, retirement, recovery, and dirty-work safeguards.
- [PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md) defines the intended human-facing
  `rwf` lifecycle, adapters, initialization, TDD, validation, and completion.
- [COMMAND_GRAMMAR.md](COMMAND_GRAMMAR.md) defines the recursive public command
  grammar, state-aware completion, and shared diagnostic contract.
- [COMMAND_GRAMMAR_TESTS.md](COMMAND_GRAMMAR_TESTS.md) freezes the Stage-2 TDD
  matrix for state, CLI, and completion behaviour.
- [CONFIGURATION.md](CONFIGURATION.md) defines the implemented configuration and
  script contracts.
- [ADOPTION.md](ADOPTION.md) defines the consumer migration procedure.
- [MIGRATION.md](MIGRATION.md) records the existing-repository migration scope.
