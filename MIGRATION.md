# Migration Plan

Status: planning document for issue #1.  It records the responsibilities that
must be preserved when existing repositories adopt RepoWorkflow.  It is not an
implementation checklist authorizing removal of existing validation.

## 1. Migration rule

No existing workflow or validation path is removed merely because it appears
redundant.  For every migration:

1. inventory the old path and its exact responsibility;
2. establish an independent regression/contract proving that responsibility;
3. map it to RepoWorkflow plus the consumer's configuration/scripts;
4. verify the new causal path end to end;
5. only then remove the superseded path.

The target is common orchestration, not reduced validation coverage.

## 2. Intended consumers

Initial consumers are:

- DownloadConversation;
- AIConversationCore;
- AgentPanelSpeaker.NET;
- AI-General-Memory;
- Multi-AI.

Each should consume RepoWorkflow as a Git submodule named `RepoWorkflow` and
retain repository-specific facts under `.ci` plus repository-owned scripts.

## 3. Common target shape

```text
Consumer/
├── RepoWorkflow/                 # pinned submodule
├── .ci/
│   ├── run-ci-request
│   └── repository configuration
├── .github/workflows/ci.yml      # common thin GitHub adapter
├── scripts/
│   ├── workflow-version          # repo-defined authoritative version
│   └── validate-*                # one authoritative entry per environment
└── ...
```

Repositories with committed generated artifacts additionally declare generator,
verifier, and output allow-list information.  They should not require a
repository-specific copy of the common lifecycle engine.

## 4. Responsibilities to consolidate

### 4.1 CI contract duplication

Existing repositories contain similar but divergent request, matrix, result,
and tagging engines.  These responsibilities should move to RepoWorkflow while
consumer configuration/scripts preserve repository-specific behaviour.

### 4.2 Actions/repository policy

Common enforcement for workflow allow-lists, write permissions, source/document
mutation restrictions, and generated-artifact publication boundaries should be
implemented once in RepoWorkflow.

### 4.3 Branch policy

The branch-parent/dependency-history checker currently arose from
AIConversationCore lineage problems, but the invariant is general.  Every
consumer should be able to declare its branch topology and use the same checker.

### 4.4 Test orchestration

Individual tests should not be enumerated as GitHub jobs or as a shared JSON
program.  Each required environment exposes one repository-owned authoritative
validation script.  That script may compose repository tests serially or in
parallel, using shared helpers when useful.

## 5. Known existing workflow responsibilities

The following are responsibilities that must be reconciled rather than simply
deleted.

### AIConversationCore

Current/recent responsibilities include:

- ordinary CI request/matrix/tagging behaviour;
- branch-parent/dependency-history enforcement;
- the historical `Phase 8 validation` regression bundle;
- deterministic committed browser-artifact generation/publication.

The Phase 8 checks overlap the regular Core test matrix and should become
ordinary authoritative Core validation rather than a permanent special workflow
once equivalence is proven.

Branch-policy semantics should move to the common engine while Core supplies its
actual branch graph.

Generated browser-artifact generation/verification remains Core-specific through
scripts and declarations; publication safety/lifecycle becomes common.

### AgentPanelSpeaker.NET

Current/recent responsibilities include:

- request/matrix/tagging behaviour;
- Windows/.NET application validation;
- AIConversationCore integration validation, including pinned Core behaviour,
  built/deployed application tests, bundled runtime checks, and projection
  checks;
- repository task execution used for checked-in verification tasks.

The Core integration responsibility must become part of APS's authoritative
validation script/environment rather than being lost when standalone workflow
YAML is consolidated.

### AI-General-Memory

Its existing repository-specific version location and test requirements should
be exposed through repository scripts/configuration.  Common CI lifecycle and
policy code should be removed only after the shared engine is proven equivalent.

### Multi-AI

Multi-AI is an early-stage application repository, not a documentation-only
repository.  RepoWorkflow adoption must support its future application test
matrix without baking today's limited implementation state into the shared
engine.

### DownloadConversation

DownloadConversation is in the middle of converting its older CI/test-cycle
model to explicit request/matrix/result-tag semantics.  RepoWorkflow should
become the shared foundation rather than leaving another permanent local copy
of the CI engine.

DownloadConversation also has a committed generated userscript responsibility.
Its repository scripts should own userscript generation/verification; the
shared engine should own output-boundary enforcement and lifecycle semantics.

A temporary instruction currently prohibits triggering/rerunning/dispatching
GitHub Actions in DownloadConversation through 2026-09-30.  Migration planning
and local validation may continue, but any DC Actions acceptance run must wait
until that restriction expires unless the user explicitly changes it.

## 6. Version migration

Each consumer should replace format-specific logic in the common engine with a
repository-owned version script.  That script is responsible for reconciling
all version-bearing locations in that repository and emitting one canonical
version only when they agree.

RepoWorkflow then compares the emitted version to `.ci/run-ci-request` and
checks terminal-tag eligibility.

## 7. Environment migration

Current GitHub runner labels should not automatically become the permanent
cross-platform contract.  Consumers should declare required platform/capability
facts where practical.  The GitHub adapter maps them to GitHub runners; local
and future adapters establish whether they can satisfy the same requirements.

A separate environment is warranted for a genuinely different required
platform/capability set.  Test-level parallelism remains inside the repository's
single validation script for that environment.

## 8. Artifact migration

For each committed generated artifact:

1. identify the repository-owned generator;
2. identify/create an independent verifier;
3. declare the only paths generation may modify;
4. prove deterministic generation where required;
5. move change-set enforcement into RepoWorkflow;
6. keep GitHub commit/push permission in a narrowly scoped GitHub publication
   path only.

Repos without committed generated artifacts should have no artifact hook.

## 9. Pilot strategy

Before migrating all consumers, select one repository whose required behaviours
exercise enough of the design to validate the contracts without maximizing
migration risk.

The pilot must prove at least:

- submodule pinning;
- local authoritative invocation;
- GitHub adapter invocation;
- request/version/tag guard;
- one environment validation entry point;
- PASS/FAIL/INCOMPLETE result handling;
- branch-policy execution;
- policy enforcement;
- result-tag publication.

If the selected pilot has a generated committed artifact, artifact lifecycle can
be proven in the same pilot; otherwise that contract requires a second focused
consumer validation before broad rollout.

## 10. Completion condition for a consumer

A consumer is not considered migrated until:

- its authoritative validations are accounted for;
- old and new behaviour have been compared using independent tests/oracles;
- local execution uses the same shared engine as hosted execution;
- `.ci/run-ci-request` guard semantics are enforced;
- terminal tags are protected from reuse;
- branch and Actions policies are enforced through the shared mechanism;
- any generated artifact is bounded and independently verified;
- superseded workflow/code copies are removed;
- the remaining GitHub workflow surface contains only the intended common
  adapter and any unavoidable GitHub-only publication mechanism.
