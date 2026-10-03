# Stage 2 TDD — State Machine, CLI, and Completion

Required state-machine tests:

- initial task-development state;
- regression-required state;
- ART PASS, FAIL, and INCOMPLETE transitions with no user result entry;
- local ART starts only on explicit full validation invocation; no heuristic such as
  code changes, idleness, or implementation completion starts it automatically;
- `validate regression --fast` runs the repository-defined minimal fast ART
  set and cannot satisfy/advance the complete ART gate;
- `validate regression --group NAME` runs only that ART group and cannot by
  itself satisfy/advance the complete ART gate;
- accumulated partial ART evidence does not satisfy the full gate unless the
  repository's declared complete required set for the exact candidate is
  authoritatively covered;
- AIT-required state and automatic AIT result recording;
- local integration validation starts only on explicit `validate integration`;
- bare `validate integration` orchestrates all required AIT and required MIT;
- `validate integration --automatic` selects AIT only and cannot skip a
  required MIT gate;
- `validate integration --manual` selects MIT only and cannot skip required
  AIT;
- `validate integration --group NAME` runs only the named integration subset
  and cannot by itself satisfy the complete integration gate;
- a full integration run executes AIT automatically but stops/presents required
  MIT for a human result rather than pretending MIT was automated;
- server examination automatically runs missing ART/AIT only; it never creates
  MIT evidence;
- AIT PASS, FAIL, and INCOMPLETE transitions, including automatic result
  recording and that AIT FAIL advances `Q` and resets `R`;
- MIT-required state only when manual integration testing is declared;
- MIT succeeded and failed human-result transitions, including that MIT FAIL
  advances `Q` and resets `R`;
- AIT PASS -> MIT-required when MIT is declared, versus AIT PASS -> accepted
  integration requirement when no MIT is declared;
- acceptance with AIT but no MIT, proving no unnecessary user test gate is
  introduced;
- accepted-but-not-yet-integrated state;
- preliminary-integration states;
- stale preliminary candidate state;
- landed-but-not-finalized state;
- finalized stable state;
- invalid transitions from every state are blocked.

Required `what-next` tests:

- text output identifies legal next actions;
- JSON exposes the same actions and blocked reasons;
- output is deterministic for the same repository state;
- no GREEN result, ready PR, or completed task is mistaken for a transition
  that the repository's policy does not permit.

Required configuration/PR tests:

- `config` reports effective configuration and source in text and JSON forms;
- `config get/set/unset` round-trips every supported mutable policy value;
- invalid keys/values fail atomically without modifying checked-in config;
- PR policy accepts exactly `required|allowed|disabled`;
- required mode exposes `pull-request` when state permits and blocks bypass;
- allowed mode permits both policy-legal PR and non-PR paths;
- disabled mode rejects `pull-request` with an actionable reason;
- `pull-request` derives the correct head/base/title/body/workflow metadata;
- repeated `pull-request` is idempotent and does not create duplicate PRs;
- ambiguous/conflicting existing PR state is a STOP;
- creating a PR never advances validation/acceptance/merge state by itself;
- platform/hardware config accepts only declared reproducibility capabilities
  and rejects forbidden identifying inventory;
- `what-next`, JSON, command acceptance, and completion agree with configured
  PR policy.

Required completion tests must exercise an actual supported shell completion
environment rather than merely inspect generated text:

- completion is generated from the same state-machine result as `what-next`;
- `rwf validate integration <TAB>` offers only legal outcomes when a result
  transition is pending, and the state identifies whether it is AIT or MIT;
- illegal commands disappear as state changes;
- options such as `--json` remain options rather than workflow states;
- filenames or unrelated shell candidates do not leak into controlled
  transition positions;
- quoting and spaces do not corrupt completion;
- completion works after command aliases and partial tokens;
- completion failure cannot execute a workflow mutation;
- manual execution and completion use the same command-path analyser and report
  the same first failure for equivalent input;
- unknown grammar tokens are reported as unrecognised commands and the first
  unknown token is underlined without rewriting the user's input;
- known command paths that are illegal in the current workflow state underline
  the first state-invalid token and show `Legal transitions:` exactly once;
- state-dependent dynamic completion with no matching partial candidate reports
  `no completions available from the current state` and shows the
  human-readable current state plus legal transitions exactly once;
- bare `list[str]` completion with no match reports generic
  `no completions available for` and does not render workflow-state or legal
  transition information;
- a callable `_values` provider returning `list[str]` receives the same
  bare-value diagnostic behaviour as a literal `list[str]`;
- multiple possible descendants sharing the same first illegal token produce
  one diagnostic for that first failure rather than duplicate downstream
  errors;
- state names rendered in diagnostics are normal human-readable phrases, not
  hyphenated internal identifiers.

