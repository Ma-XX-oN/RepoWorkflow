# RepoWorkflow First-Use Test Strategy

This document contains the first-use and assembled-public-workflow extensions
to the repository-wide strategy in [TEST_STRATEGY.md](TEST_STRATEGY.md).
The universal adequacy requirements remain authoritative in
[TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## Public CLI bootstrap matrix

Every public command pathway that does not semantically require initialized
workflow configuration must be exercised through the assembled CLI from a Git
repository with no `.ci/repoworkflow.json`.

The matrix must cover every statically authored command prefix automatically,
plus dynamic prefixes that cannot be enumerated statically.  It must prove
that:

- `--help` works before workflow-configuration discovery;
- unknown commands and invalid syntax report grammar diagnostics first;
- configuration-required execution requests configuration only after syntax is
  accepted;
- read-only commands that have an independent repository/provider resolution
  path do not acquire full workflow configuration merely to run.

Adding a new public command requires an explicit bootstrap/configuration
classification and corresponding black-box coverage.  Parser/unit tests or
configured synthetic fixtures do not substitute for this assembled-path gate.


## First-use workflow validation

Component, contract, store, adapter, and semantic-transition tests do not by
themselves prove a supported public workflow.  Every supported public workflow
family must also have an assembled **first-use scenario** registered in
`FIRST_USE_WORKFLOWS.json`.

A first-use scenario starts from the minimum external state promised by the
documentation and enters through the real public boundary.  It must not
pre-create internal state that the public workflow is responsible for creating.

Examples of prohibited shortcuts include:

- directly creating relationship, current-work, lifecycle, lane-selection, or
  workspace records when the public workflow owns their creation;
- manually injecting runtime identity in a human first-use scenario when the
  supported shell/session invocation layer owns establishing it;
- calling semantic helpers instead of the shipped launcher/CLI;
- replacing an assembled provider path with mocks below the documented adapter
  boundary;
- preinstalling configuration or generated adoption files that the first-use
  workflow is supposed to discover or create.

Provider/network behaviour may be controlled at the documented external
adapter boundary so tests remain deterministic.

The registry classifies each scenario as:

- `covered`: authoritative assembled test(s) exist;
- `gap`: supported/component behaviour exists but assembled first-use coverage
  is missing and an explicit repair issue owns it;
- `pending`: the public feature itself is not yet complete and its
  implementation owner must include first-use coverage before closure.

`tests/test_first_use_workflows.py` enforces that every executable static
public command path maps to a registered scenario or an explicit compatibility
exemption, that covered scenarios name real tests, and that gaps/pending
scenarios have an issue owner.

The repository-wide ticket audit is maintained in
`FIRST_USE_WORKFLOW_AUDIT.md`.  A public first-use owner issue is not complete
until its scenario is `covered`; lower-level GREEN tests cannot substitute for
that gate.

## Acceptance traceability and stateful scenario completeness

A GREEN first-use file is not sufficient evidence that a public workflow's
documented contract is complete.

Every registered public first-use scenario must maintain an acceptance matrix in
`FIRST_USE_WORKFLOWS.json`.  Each requirement must map to exactly one of:

- executable verification naming a concrete test method; or
- an explicit open issue that owns deliberately deferred behaviour.

A scenario may be marked `covered` only when every acceptance requirement has
executable verification.

For stateful scenarios, the registry must enumerate applicable lifecycle
dimensions: initial empty state, repeated invocation, additional targets,
overlapping state, read-after-write, stale/conflicting state, persistence, and
provider failure.  Each dimension must point to an acceptance requirement with
executable verification before the scenario is covered.

Covered scenarios that fake an external provider boundary also require an
explicit provider-contract verification target.  Fixtures must model a
validated real/provider contract shape, not a reduced implementation-shaped
payload.

These are closure gates.  Registry tests must fail for missing acceptance
verification, unverified stateful lifecycle dimensions, or a covered provider
scenario without a provider-contract verifier.
