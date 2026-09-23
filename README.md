# RepoWorkflow

RepoWorkflow provides the shared, platform-independent repository workflow for
CI, branch policy, validation, generated artifacts, and terminal result tagging.
It is consumed as a Git submodule named `RepoWorkflow` in each repository.

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

- `.ci/run-ci-request` version/candidate eligibility;
- authoritative remote terminal-tag checks;
- exact-candidate and clean-checkout validation;
- PASS / FAIL / INCOMPLETE semantics and result aggregation;
- branch-parent/dependency-history policy;
- canonical GitHub-workflow/repository policy;
- generated-artifact output and verifier safeguards;
- terminal result tagging rules;
- serial/parallel orchestration helpers.

Each consumer owns repository-specific facts and operations:

- one authoritative version command;
- one authoritative validation command per genuinely distinct environment;
- repository-specific tests, builds, packaging, and integration checks;
- branch topology declarations;
- required platform/capability declarations;
- optional committed-artifact generator and independent verifier commands;
- generated-output allow-lists.

GitHub YAML owns only GitHub mechanics: events, permissions, recursive checkout,
runner provisioning, matrix fan-out, Actions artifact transport, job outputs,
and narrowly authorized publication/tagging plumbing.

## Universal request guard

`.ci/run-ci-request` is required for authoritative execution everywhere, not
only on GitHub. Its development version must match the repository's own version
command, the candidate must be exact and clean, and the authoritative remote
must not already contain either terminal tag:

```text
v<version>
v<version>-CI-FAIL
```

If authoritative eligibility cannot be established, execution is INCOMPLETE.
A terminal tag consumes that development iteration.

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
`branch-policy`, `repository-policy`, and `materialize-artifacts`.  `verify` is
the full local authoritative path: it enforces repository and branch policy,
applies the universal candidate guard, materializes/verifies declared committed
artifacts, runs every locally addressable environment, aggregates results, and
optionally creates/pushes the terminal tag.

A repository's individual tests are not listed in RepoWorkflow configuration.
Each environment exposes one repository-owned validation command, which may use
RepoWorkflow's serial/parallel helpers or its own orchestration.

## Documentation

- [DESIGN.md](DESIGN.md) defines the architecture and invariants.
- [CONFIGURATION.md](CONFIGURATION.md) defines the implemented configuration and
  script contracts.
- [ADOPTION.md](ADOPTION.md) defines the consumer migration procedure.
- [MIGRATION.md](MIGRATION.md) records the existing-repository migration scope.
