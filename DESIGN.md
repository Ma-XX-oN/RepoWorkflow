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

## 2.1 Consumer root and self-hosting

RepoWorkflow is intended to be able to consume its own workflow without
creating recursive RepoWorkflow submodules.  Engine location and consumer
repository identity are separate concepts.

For a normal consumer using RepoWorkflow as a submodule, the layout may be:

```text
repo/
├── .repoworkflow/
└── RepoWorkflow/
    └── .repoworkflow/
```

The enclosing `repo/.repoworkflow/` belongs to the consumer and is the only
RepoWorkflow state/configuration namespace applicable while operating on
`repo`.  The nested `repo/RepoWorkflow/.repoworkflow/` belongs to the
RepoWorkflow repository itself.  Its presence in the pinned submodule must not
affect, supplement, override, or leak into the enclosing consumer's workflow.

This is a lookup rule, not a Git-ignore rule.  RepoWorkflow's own
`.repoworkflow/` may contain checked-in policy needed when RepoWorkflow is
developed as a repository in its own right.

All `.repoworkflow` lookup must therefore be rooted explicitly at the resolved
consumer repository root.  RWF must not recursively search for, merge, or
inherit nested `.repoworkflow` directories.

When RepoWorkflow is developed directly, its repository root is also its
consumer root and its own root-level `.repoworkflow/` is active.  Self-hosting
therefore uses the same consumer contract as any other repository; it does not
require a nested `RepoWorkflow/RepoWorkflow` submodule or product-specific
special case.

Initialization invoked through a consumer's pinned engine, for example
`RepoWorkflow/repo-workflow init`, initializes the enclosing consumer root.
It must not initialize or select the submodule's own workflow namespace merely
because the executable resides inside that submodule.

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

## 13.1 Static test catalogue and Rosetta translation

Issue #14 extends the validation design toward a static, language-agnostic test
catalogue.  This subsection records the settled design decisions reached so far;
the complete schema and TDD policy remain under design and are not frozen here.

The catalogue has two top-level collections: `test-harnesses` and `tests`.
`test-harnesses` is the Rosetta dictionary.  Each key names a harness and its
value describes how native test targets are translated into process arguments.
`tests` is an array of test declaration objects.  Each declaration selects a
Rosetta entry with `test-harness` and maps RWF group keys to native targets.

For example:

```json
{
  "test-harnesses": {
    "CTest": {
      "leading-params": ["--output-on-failure"],
      "delim": "|",
      "layout": ["-R", "$tests"]
    }
  },
  "tests": [
    {
      "test-harness": "CTest",
      "command": "test/ctest",
      "issue-123-empty-input": {
        "type": "regression",
        "speed": "fast",
        "name": "parser_empty_input"
      },
      "issue-123-null-input": {
        "type": "regression",
        "speed": "fast",
        "name": "parser_null_input"
      }
    }
  ]
}
```

The group key is the RWF identity.  `name` is the native test target understood
by the selected harness.  `type` describes the RWF validation role, such as
`regression` or `integration`.  `test-harness` identifies how those native
targets are executed and selected.  This avoids overloading the word "type" for
both concepts.

`command` always means the executable; it is never a test name, project target,
or other input.  It may be supplied by either the selected harness definition or
the test declaration, but not both.  The resolved pair must contain `command`
in exactly one place: both present and both absent are invalid.  The effective
command is therefore unambiguous and remains a single string.

A harness can supply the standard executable:

```json
{
  "test-harnesses": {
    "CTest": {
      "command": "ctest",
      "leading-params": ["--output-on-failure"],
      "delim": "|",
      "layout": ["-R", "$tests"]
    }
  },
  "tests": [
    {
      "test-harness": "CTest",
      "issue-123-empty-input": {
        "type": "regression",
        "speed": "fast",
        "name": "parser_empty_input"
      }
    }
  ]
}
```

Alternatively, a harness can omit `command` so multiple declaration objects can
reuse the same translation while supplying compatible repository-specific
executables or wrappers.

`leading-params` contains invariant arguments placed after the executable and
before the generated selection layout.  `layout` may be a string or an array
of strings; an array preserves process argument boundaries rather than asking
RWF or a shell to parse a command line.

The layout template vocabulary currently has these meanings:

- `$test`: expand the layout once for each selected native test name;
- `$tests`: join the selected native test names with `delim` and substitute
  the joined value once;
- `$ftests{...$test...}`: apply the enclosed template to every selected native
  test name, join the formatted values with `delim`, and substitute the joined
  value once;
- `$file`: substitute the pathname of a temporary indirect-selection file.

`delim` is valid and required when a template performs a multiple-test join,
including `$tests` and `$ftests{...}`.  It is not needed for purely individual
`$test` expansion.

For example, a .NET harness can express the native filter grammar without
teaching RWF what `FullyQualifiedName` or `|` means:

```json
{
  "test-harnesses": {
    "dotnet": {
      "command": "dotnet",
      "leading-params": ["test"],
      "delim": "|",
      "layout": [
        "--filter",
        "$ftests{FullyQualifiedName=$test}"
      ]
    }
  },
  "tests": [
    {
      "test-harness": "dotnet",
      "issue-123-example": {
        "type": "regression",
        "name": "A"
      },
      "issue-123-other": {
        "type": "regression",
        "name": "B"
      }
    }
  ]
}
```

Selecting native names `A` and `B` produces process arguments equivalent to:

```text
dotnet test --filter "FullyQualifiedName=A|FullyQualifiedName=B"
```

Indirect harnesses use `$file` in the command parameters so RWF can provide a
temporary selection file.  The exact file-content template/schema is still
under design and must be settled before this part of the Rosetta contract is
implemented.

The catalogue is static.  Full regression selection is derived from entries
whose metadata says `type: regression`; fast selection is derived from speed
metadata; group selection matches canonical group keys.  Separate manually
maintained aggregate suite membership is intentionally avoided because it would
create multiple places that must remain synchronized.

When many selected tests are representable in one native invocation, RWF may
batch them.  Batching must preserve whole test selections and respect the
platform's process argument limit rather than imposing an arbitrary test-count
limit.  Diagnostic hosted-runner probes have established that native Windows is
the constraining tested platform, so implementations must leave a conservative
margin rather than assume Unix-sized argument capacity.  Indirect selection can
avoid command-line growth when the harness supports it.

This Rosetta layer is deliberately data-driven.  RWF understands substitution,
joining, batching, and indirect-file mechanics, but does not embed CTest,
pytest, .NET, or another harness's test-selection grammar.

## 13.2 Declarative command grammar and Bash completion

Issue #15 uses one Python-owned command data structure as the authoritative
description of the user-facing CLI grammar.  Argument parsing/validation,
shell-completion candidates, completion help, and normal command help must be
projections of that structure rather than independently maintained command
lists.

The intended shape is deliberately simple and inspectable.  For example:

```python
COMMANDS = {
  "validate": {
    "regression": {
      "": "Run all regression tests",
      "--fast": "Run fast smoke tests",
      "--group": [
        "Run a specific group of tests",
        function_to_get_names,
      ],
    },
    "integration": {
      "": "Run all integration tests",
      "--automatic": "Run automated integration tests",
      "--manual": "Run manual integration tests",
      "--group": [
        "Run a specific group of tests",
        function_to_get_names,
      ],
    },
  },
  "config": {
    "": "Show repository configuration",
    "get": "...",
    "set": "...",
    "unset": "...",
    "--json": "...",
  },
}
```

The exact Python representation may gain metadata as implementation requires,
but it must preserve the single-source invariant.  In particular, the empty
string describes the action represented by the current command node, ordinary
keys describe literal subcommands/options, and a callable associated with an
argument-bearing entry supplies its dynamic completion values.

The Bash adapter is a presentation layer.  It supplies the current command
line/cursor context to the RWF completion engine and receives the candidates
derived from the command grammar and current workflow state.  It must not
duplicate RWF command or state policy.

The intended Bash interaction is:

- one Tab performs normal completion and displays/inserts candidate names;
- a second Tab within one second, with the same command line and completion
  context, displays the static command descriptions as additional detail;
- changing the command line or completion context resets the double-Tab state;
- when a dynamic value provider supplies values, those values are the
  completions on both single and double Tab.  RWF does not manufacture or
  maintain a second description set for them.

For example:

```text
rwf validate regression <TAB>
--fast  --group
```

A second Tab within one second may show:

```text
--fast     Run fast smoke tests
--group    Run a specific group of tests
```

By contrast, dynamic group completion remains:

```text
rwf validate regression --group <TAB><TAB>

issue-123-parser-empty-input
issue-123-browser-reconnect
```

The group names come from the static test catalogue.  Their completion data is
not duplicated in the command grammar.

A Bash prototype using a real pseudo-terminal established that Bash invokes the
completion function on repeated Tab presses with the same completion context,
that timing can be measured, and that the second invocation can print the
detailed list while returning an empty `COMPREPLY` to suppress Bash's redundant
plain list.  That path may produce the terminal bell; this is acceptable for
the initial implementation and can be revisited if it proves distracting in
normal use.

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

## 16. Guarded task-to-release lifecycle

Issue #14 extends this architecture with an explicit state-machine-driven
workflow for task validation, preliminary integration, protected server
integration, stable publication, local/hosted validation reuse, validation audit
records, workflow-aware completion, and local Git guard hooks.

The authoritative lifecycle design is documented in
[`WORKFLOW_LIFECYCLE.md`](WORKFLOW_LIFECYCLE.md).  The corresponding overall,
per-stage, concurrency, platform, and end-to-end test requirements are in
[`TEST_STRATEGY.md`](TEST_STRATEGY.md).  Implementations must preserve the
responsibility boundaries in this document: RepoWorkflow owns generic
workflow/state semantics, while each consumer repository retains its
repository-specific version mutation and validation logic behind declared
adapter contracts.
