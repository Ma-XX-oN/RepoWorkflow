# RepoWorkflow Design

Status: design specification for issue #1.  No production implementation is
part of this document commit.

## 1. Goals

RepoWorkflow provides one authoritative implementation of repository workflow
rules that can be reused by multiple repositories without copying CI engines,
policy scripts, tagging logic, or artifact safeguards.

The design must support three execution contexts with equivalent semantics:

1. local developer execution;
2. GitHub Actions;
3. another CI/automation platform.

GitHub-specific YAML is therefore an adapter, not the workflow engine.

## 2. Consumption model

Each consumer adds this repository as a Git submodule using the same directory
name as the repository:

```text
Project/
└── RepoWorkflow/
```

The superproject Gitlink pins an exact RepoWorkflow commit.  This makes the
workflow implementation used by a candidate explicit, reproducible, and
reviewable in the consumer's history.

A consumer may update the submodule only as an explicit repository change.
RepoWorkflow must not silently self-update during validation.

## 3. Layering

### 3.1 GitHub adapter

`.github/workflows/ci.yml` should be byte-for-byte identical across consumers
whenever technically possible.

It may contain only GitHub-specific responsibilities, including:

- event declarations;
- permissions;
- checkout and recursive submodule initialization;
- GitHub runner/matrix provisioning;
- GitHub artifact upload/download used to transport structured result records;
- GitHub job outputs;
- narrowly authorized GitHub publication operations.

It must not contain project-specific test commands, artifact generators,
version discovery, branch-policy algorithms, result semantics, or project
special cases.

### 3.2 RepoWorkflow engine

RepoWorkflow owns platform-independent mechanisms and invariants:

- request/version validation;
- exact-candidate validation;
- authoritative terminal-tag eligibility;
- environment lifecycle;
- result-record schema;
- required-result aggregation;
- PASS / FAIL / INCOMPLETE classification;
- branch-policy evaluation;
- repository/Actions-policy evaluation;
- generated-artifact change-set enforcement;
- common tagging rules;
- common serial/parallel execution helpers.

### 3.3 Consumer configuration

The consumer's `.ci` data describes repository-specific facts.  Configuration
must remain declarative.  When behaviour has meaningful logic, configuration
points to a repository-owned script instead of embedding a miniature program in
JSON.

### 3.4 Consumer scripts/tests

The consumer owns how its own operations work, including:

- reporting and internally validating its version;
- authoritative validation for each required environment;
- builds and packaging;
- dependency/integration verification;
- artifact generation and independent artifact verification;
- project-specific prerequisite checks.

## 4. Universal CI request guard

`.ci/run-ci-request` is part of the authoritative validation contract in every
execution environment.  It is not merely a GitHub trigger file.

Before an authoritative validation run begins, RepoWorkflow must establish all
of the following:

1. `.ci/run-ci-request` exists.
2. It contains a syntactically valid development version.
3. The repository-owned version script succeeds.
4. The version script reports exactly the requested version.
5. The checkout being validated is the exact candidate commit associated with
   the run.
6. The worktree/checkout satisfies the required cleanliness and repository
   provenance rules.
7. The authoritative tag source is current enough to establish eligibility.
8. Neither terminal tag for the development iteration already exists:
   - `v<version>`;
   - `v<version>-CI-FAIL`.

If authoritative tag state cannot be established because the remote, network,
credentials, or required history is unavailable, eligibility is INCOMPLETE.
RepoWorkflow must never infer "untagged" from stale or unavailable evidence.

On GitHub, modification of `.ci/run-ci-request` is additionally the explicit
request to spend the expensive CI quota.  Manual dispatch may be supported as
another explicit request, but it must pass the same universal guard.

## 5. Version contract

RepoWorkflow must not know where a consumer stores its version.

Each consumer provides one authoritative version script.  That script may read
one file or reconcile several version-bearing files.  Its contract is:

- success means the repository's version state is internally valid;
- stdout reports exactly one canonical development version;
- non-zero exit means version state cannot be accepted.

This permits consumers to derive versions from package metadata, source
headers, project files, plain VERSION files, or multiple synchronized sources
without teaching RepoWorkflow those formats.

RepoWorkflow compares only:

```text
requested version == repository-reported canonical version
```

## 6. Validation contract

### 6.1 One entry point per environment

Each required environment/capability set declares exactly one repository-owned
authoritative validation script.

RepoWorkflow does not receive a list of individual tests to run.

The validation script decides:

- which tests/checks/builds are authoritative;
- ordering dependencies;
- parallel versus serial execution;
- setup and teardown;
- whether independent checks continue after another check fails;
- repository-specific logging and diagnostics.

RepoWorkflow may provide reusable helpers such as serial and parallel runners.
Those helpers are orchestration primitives; they do not define which project
tests exist.

### 6.2 Environment matrix

Separate environment entries are justified by genuinely different required
execution conditions, such as:

- operating system;
- runtime family/version;
- desktop/UI capability;
- hardware/device capability;
- other externally meaningful platform requirements.

Test-level parallelism alone is not a reason to create another environment.

Configuration should describe capabilities in platform-neutral terms where
practical.  A GitHub adapter may map those requirements to GitHub runner
labels; another platform may map them differently.

### 6.3 Result classification

A validation environment produces one structured result associated with the
exact version and commit.

- PASS: all required validation represented by that environment completed and
  passed.
- FAIL: required validation executed and established a genuine source/product
  failure.
- INCOMPLETE: the required result could not be established because of missing
  platform capability, infrastructure, credentials, network, runner,
  prerequisite, or equivalent inability.

Independent required environments must all report before terminal
finalization.  A failing environment does not suppress execution of unrelated
required environments.

## 7. Terminal result tags

For a development version `X`:

- complete required PASS => `vX`;
- complete genuine FAIL => `vX-CI-FAIL`;
- any required INCOMPLETE/missing result => no terminal tag.

Terminal result tags are immutable.  Once either terminal tag exists for a
version, that development iteration is consumed and cannot be rerun as a new
candidate after source changes.  A subsequent source change requires the next
issue iteration.

An infrastructure retry may re-evaluate the same unchanged candidate when no
terminal result has been established.

## 8. Branch policy

Branch-parent and dependency-history protection is a common repository
invariant, not a product-specific Core feature.

RepoWorkflow owns the policy algorithm.  Consumers provide the intended graph,
including as needed:

- default integration parent;
- explicit parent for issue/feature branches;
- umbrella/integration branches;
- allowed dependency branches;
- integration target;
- other declarative lineage exceptions.

The shared checker should establish facts from Git history rather than trust
branch names alone.  It should detect practical violations such as:

- declared parent not matching allowed ancestry;
- unrelated imported issue history;
- undeclared dependency merges;
- incorrect pull-request base;
- an umbrella branch without the required declaration.

The same checker must be invokable locally.  GitHub may run it automatically as
a cheap preflight without starting expensive validation.

## 9. Repository and GitHub Actions policy

RepoWorkflow owns common enforcement that prevents automation from evolving
back into repository-editing machinery.

Common policy should cover, where technically enforceable:

- allowed workflow entry points;
- least-privilege workflow permissions;
- restriction of repository writes to explicitly approved publication paths;
- prohibition of general source/document mutation by CI automation;
- generated-artifact publication as a narrow declared exception;
- detection of unapproved `git commit`/`git push` patterns in workflows;
- consistency of the common GitHub adapter.

Repository-specific exceptions should be minimal, declarative, and reviewable.

## 10. Generated artifacts

A consumer that commits generated artifacts declares each artifact and provides
repository-owned scripts for generation and independent verification.

RepoWorkflow should perform the safety lifecycle:

1. establish the pre-generation repository state;
2. invoke the declared generator;
3. inspect the resulting changed-file set;
4. reject any modification outside the declared output allow-list;
5. invoke the declared independent verifier;
6. record a structured result;
7. permit publication only after all applicable safeguards pass.

Generation and verification scripts must not require GitHub.  They must work
locally and on other CI platforms.

The act of committing/pushing a verified generated artifact to GitHub is a
GitHub publication concern and requires a narrowly scoped GitHub write job.
Repositories with no committed generated artifacts need no artifact-specific
hook.

## 11. Repository-provided configuration and hooks

The exact schema remains subject to contract testing, but RepoWorkflow is
expected to need repository-specific declarations for:

- authoritative version script;
- required environments/capabilities;
- one validation script per environment;
- branch topology and allowed dependencies;
- authoritative integration branch;
- authoritative remote/tag source where it cannot be safely derived;
- optional generated artifacts;
- artifact generators/verifiers and output allow-lists;
- repository-specific prerequisite or integration-validation scripts.

Configuration should point to scripts instead of encoding complex shell logic.

Illustrative only:

```json
{
  "versionScript": "scripts/workflow-version",
  "repository": {
    "integrationBranch": "main",
    "authoritativeRemote": "origin"
  },
  "environments": [
    {
      "id": "windows-desktop",
      "required": true,
      "platform": "windows",
      "capabilities": ["dotnet-10", "node-22", "desktop-ui"],
      "validationScript": "scripts/validate-windows"
    }
  ],
  "artifacts": [
    {
      "id": "generated-output",
      "generator": "scripts/generate-artifact",
      "verifier": "scripts/verify-artifact",
      "outputs": ["path/to/generated.file"],
      "committed": true
    }
  ]
}
```

This example is not yet a frozen schema.

## 12. Parallel/serial helper contract

RepoWorkflow may provide platform-independent helpers for consumer validation
scripts.  At minimum, useful primitives include:

- run a sequence and stop/continue according to explicit policy;
- run independent commands concurrently;
- wait for all independent commands so one failure does not hide others;
- preserve command identity, stdout/stderr, duration, and exit status;
- return deterministic aggregate status;
- distinguish validation failure from declared prerequisite/infrastructure
  inability where the caller supplies that classification.

Consumers remain free to implement their own orchestration when the shared
helpers are insufficient, as long as the environment exposes one authoritative
validation entry point to RepoWorkflow.

## 13. Local/GitHub/other-platform equivalence

The same RepoWorkflow engine and same consumer scripts/configuration must drive
all supported execution contexts.

A platform adapter is allowed to provide only platform-specific mechanics.
Changing execution platform must not alter:

- candidate/version eligibility rules;
- which repository validation is authoritative;
- PASS / FAIL / INCOMPLETE meaning;
- branch-policy semantics;
- artifact output restrictions;
- terminal-tag semantics.

This makes local execution a real authoritative workflow path rather than an
approximation of GitHub Actions.

## 14. Non-goals

RepoWorkflow must not:

- contain product-specific knowledge of AIConversationCore,
  DownloadConversation, AgentPanelSpeaker, AI-General-Memory, or Multi-AI;
- duplicate each consumer's test suite in shared configuration;
- turn JSON into a scripting language;
- use GitHub Actions as a general repository-editing mechanism;
- silently add fallbacks that weaken required validation;
- infer safety-critical branch, version, or tag facts from weak heuristics when
  a consumer declaration or authoritative check is required.

## 15. Implementation discipline

Implementation starts only after this design has been reviewed against the
existing consumers.

When implementation begins:

1. establish a specific RED contract test for each invariant;
2. implement the smallest shared mechanism that satisfies the documented
   contract;
3. verify GREEN with independent/nonvolatile oracles;
4. test the causal chain beyond the immediate helper or workflow boundary;
5. pilot one consumer before broad migration;
6. preserve existing authoritative validation coverage during migration;
7. remove old standalone/duplicate workflows only after equivalence has been
   established.

No generated-artifact, branch-policy, integration-validation, or other existing
check should be removed merely because RepoWorkflow has a nominal replacement;
its responsibility must first be mapped and verified in the new path.
