# RepoWorkflow

RepoWorkflow provides the shared, platform-independent repository workflow for
CI, branch policy, validation, generated artifacts, candidate bookkeeping, and
terminal result tagging. It is consumed as a Git submodule named `RepoWorkflow`
in each repository.

The central boundary is:

> GitHub workflow YAML is only a GitHub adapter. Repository workflow logic must
> remain executable locally and on other CI platforms.

A consumer is structured broadly as:

```text
Project/
├── RepoWorkflow/               # submodule pinned to an exact commit
├── .ci/                        # repository-specific declarations
├── .github/workflows/ci.yml    # byte-identical GitHub adapter
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

GitHub YAML owns only GitHub mechanics: events, permissions, recursive checkout,
runner provisioning, matrix fan-out, Actions artifact transport, job outputs,
and narrowly authorized publication/tagging plumbing.

## Authoritative local verification

The normal local development workflow is one command:

```text
python RepoWorkflow/repo_workflow.py verify
```

The caller does not manually refresh `.ci/run-ci-request`, reorder bookkeeping
commits, or opt into terminal tagging. Before validation, `verify` rebinds the
request after ordinary source commits when necessary. If the current development
iteration is already consumed remotely and `setVersionCommand` is configured,
RepoWorkflow advances to the next iteration and records the new request in one
bookkeeping commit.

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
repository's own version command and ordinary source changes must not occur after
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

The shared command-line entry point is:

```text
python RepoWorkflow/repo_workflow.py <command>
```

Important commands include `preflight`, `verify`, `run`, `finalize`,
`branch-policy`, `repository-policy`, and `materialize-artifacts`. `verify` is
the full local authoritative path: it enforces repository and branch policy,
prepares development bookkeeping, materializes/verifies declared committed
artifacts, runs every locally addressable environment, aggregates results, and
creates the terminal development result tag automatically.

A repository's individual tests are not listed in RepoWorkflow configuration.
Each environment exposes one repository-owned validation command, which may use
RepoWorkflow's serial/parallel helpers or its own orchestration. Direct execution
of that validation command is useful for debugging, but it is not the
repository's authoritative result-recording workflow.

## Documentation

- [DESIGN.md](DESIGN.md) defines the architecture and invariants.
- [CONFIGURATION.md](CONFIGURATION.md) defines the implemented configuration and
  script contracts.
- [ADOPTION.md](ADOPTION.md) defines the consumer migration procedure.
- [MIGRATION.md](MIGRATION.md) records the existing-repository migration scope.
