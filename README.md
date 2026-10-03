# RepoWorkflow

RepoWorkflow provides the shared, platform-independent repository workflow for
CI, branch policy, validation, generated artifacts, candidate bookkeeping, and
terminal result tagging. It is consumed as a Git submodule named `RepoWorkflow`
in each repository.

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

Each consumer owns repository-specific facts and operations:

- one authoritative version read command;
- an optional version setter command used when RepoWorkflow must advance a
  consumed development iteration;
- one authoritative validation command per genuinely distinct environment;
- repository-specific tests, builds, packaging, and integration checks;
- branch topology declarations;
- required platform/capability declarations;
- optional committed-artifact generator and independent verifier commands;
- generated-output allow-lists.

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

The normal consumer-side entry point is:

```text
python scripts/repoworkflow.py <command>
```

After pin establishment, that launcher delegates unchanged arguments to:

```text
python RepoWorkflow/repo_workflow.py <command>
```

Important commands include `what-next`, `validate`, `version`, `preflight`,
`verify`, `run`, `finalize`, `branch-policy`, `repository-policy`, and
`materialize-artifacts`.  `repo-workflow` and `rwf` are equivalent aliases.
`what-next` reports the legal transitions for the current workflow state;
`validate regression` and `validate integration succeeded|failed` record the
issue-#15 workflow transitions; and `version` forwards semantic version intent
to the repository-owned adapter.  Bash completion is generated from the same
recursive `COMMANDS` grammar and state projection rather than a separate shell
command list.

`verify` remains the full local authoritative validation path: it enforces
repository and branch policy, prepares development bookkeeping,
materializes/verifies declared committed artifacts, runs every locally
addressable environment, aggregates results, and creates the terminal
development result tag automatically.

A repository's individual tests are not listed in RepoWorkflow configuration.
Each environment exposes one repository-owned validation command, which may use
RepoWorkflow's serial/parallel helpers or its own orchestration. Direct execution
of that validation command is useful for debugging, but it is not the
repository's authoritative result-recording workflow.

## Documentation

- [DESIGN.md](DESIGN.md) defines the architecture and invariants.
- [COMMAND_GRAMMAR.md](COMMAND_GRAMMAR.md) defines the recursive public command
  grammar, state-aware completion, and shared diagnostic contract.
- [COMMAND_GRAMMAR_TESTS.md](COMMAND_GRAMMAR_TESTS.md) freezes the Stage-2 TDD
  matrix for state, CLI, and completion behaviour.
- [CONFIGURATION.md](CONFIGURATION.md) defines the implemented configuration and
  script contracts.
- [ADOPTION.md](ADOPTION.md) defines the consumer migration procedure.
- [MIGRATION.md](MIGRATION.md) records the existing-repository migration scope.
