# RepoWorkflow

RepoWorkflow defines a shared, platform-independent repository workflow for CI,
branching policy, validation, generated artifacts, and result tagging.

**Status:** design/documentation only.  Implementation has not started.  The
architecture is tracked by issue #1 and is intentionally being documented
before code is written.

## Purpose

Multiple repositories need the same workflow invariants without copying and
slowly diverging CI implementations.  RepoWorkflow is intended to be consumed
as a Git submodule named `RepoWorkflow` in each repository.

The central rule is:

> GitHub workflow YAML is only a GitHub adapter.  Repository workflow logic
> must remain usable locally and on other CI platforms.

A consuming repository should therefore look broadly like this:

```text
Project/
├── RepoWorkflow/               # submodule pinned to an exact commit
├── .ci/                        # repository-specific declarations
├── .github/workflows/ci.yml    # thin, common GitHub adapter
├── scripts/                    # repository-specific operations
└── tests/
```

## Responsibility boundary

### RepoWorkflow owns

- CI request/version guard semantics;
- terminal-tag eligibility and immutability;
- exact candidate/checkout validation;
- PASS / FAIL / INCOMPLETE result semantics;
- required-environment result aggregation;
- branch-parent/dependency-history policy algorithms;
- GitHub Actions/repository-mutation policy algorithms;
- generated-artifact change-set safeguards;
- common result schemas and tagging rules;
- reusable helpers for serial/parallel validation orchestration.

### Each consuming repository owns

- an authoritative version script;
- one authoritative validation script per required environment/capability set;
- repository-specific tests, builds, packaging and integration checks;
- branch topology declarations;
- environment/capability requirements;
- optional generated-artifact generator and verifier scripts;
- generated-output allow-lists;
- repository-specific prerequisites and dependency contracts.

### GitHub workflow YAML owns only GitHub mechanics

Examples include events, permissions, checkout/submodule initialization,
runner provisioning, matrix fan-out, GitHub artifact transport, job outputs,
and narrowly authorized GitHub publication operations.

It must not become the implementation of repository validation, version
handling, branch policy, artifact generation, or result semantics.

## Validation entry points

RepoWorkflow does not receive a JSON list of individual tests.  Each required
execution environment has exactly one repository-owned validation entry point.
That script decides how to fan out its internal work, including parallel and
serial groups.  RepoWorkflow may provide shared orchestration helpers, but the
repository remains authoritative for which tests are required and how they are
composed.

Different matrix entries should represent genuinely different required
machines, platforms, or capabilities rather than test-level parallelism.

## CI request guard

`.ci/run-ci-request` is a universal candidate guard, not merely a GitHub
trigger.  Before an authoritative validation run, RepoWorkflow must establish
that:

1. the request file exists;
2. its version equals the version reported by the repository's version script;
3. the exact candidate commit is being validated;
4. neither `v<version>` nor `v<version>-CI-FAIL` already exists on the
   authoritative tag source;
5. inability to establish eligibility is INCOMPLETE, not success.

GitHub may additionally use modification of `.ci/run-ci-request` as the
explicit trigger for expensive remote CI.

## Result semantics

- Complete required validation PASS: `v<version>`.
- Complete genuine validation failure: `v<version>-CI-FAIL`.
- Infrastructure, platform, credential, network, runner, or prerequisite
  inability: INCOMPLETE and no terminal result tag.
- Terminal result tags are immutable and consume that development iteration.

## Documentation

See [DESIGN.md](DESIGN.md) for the architectural contract and
[MIGRATION.md](MIGRATION.md) for the intended migration of existing
repositories.
