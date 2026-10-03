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
## Concrete issue #15 TDD matrix

The cases below are fixed before implementation.  Tests may use helper
functions to avoid duplication, but the observable inputs and outcomes must
remain equivalent.

### Grammar validation

1. A node containing `"": "description"` validates and is executable as-is.
2. A normal token mapped to a non-empty description validates as a terminal.
3. A normal token mapped to another dictionary validates recursively.
4. An empty or non-string terminal description is rejected.
5. An unsupported underscore-prefixed key such as `_for-states` is rejected.
6. `<last-terminal>` used as an authored token is rejected.
7. A literal `_values` list containing only non-empty strings validates.
8. A literal `_values` list containing an empty/non-string value is rejected.
9. A callable `_values` provider returning `list[str]` validates at runtime.
10. A callable returning described command fragments validates recursively.
11. A callable returning a mixed list of strings and dictionaries is rejected.
12. A dynamic fragment containing `""` or `_values` at its fragment root is
    rejected because fragments must contribute described next-command tokens.
13. A dynamic token colliding with a static token is rejected.
14. Duplicate dynamic tokens from separate fragments are rejected.

### Static parsing and terminal behaviour

15. A complete static terminal command parses successfully.
16. A node with `""` plus continuations parses successfully without a
    continuation.
17. A non-terminal prefix is rejected as incomplete.
18. Tokens following a terminal command are rejected.
19. Bare `list[str]` values are accepted only as the final value token.
20. `<last-terminal>` is rejected if typed manually at any position.

### State projection

Use fixtures with human-readable states and exact legal transitions:

- `regression required` -> `validate regression`;
- `integration result pending` ->
  `validate integration succeeded`,
  `validate integration failed`;
- accepted without merge authorization -> no merge transition.

21. The general grammar recognizes both integration-result commands regardless
    of current state.
22. The legal-only projection exposes only transitions returned by the current
    state provider.
23. Changing the state changes completion candidates without changing the
    authored `COMMANDS` tree.
24. A GREEN result alone never exposes a merge/integrate transition when
    authorization is absent.

### Exact diagnostics

All diagnostics preserve the literal typed command after the executable name,
use a non-zero status for manual execution errors, and perform no mutation.

25. Unknown top-level command while the state is `regression required`:

```text
RepoWorkflow error: unrecognised command.
  foo
  ^^^

Legal transitions:
  regression required
  → validate regression
```

26. First state-invalid token, with input
`validate integration s` while the state is `regression required`:

```text
RepoWorkflow error: transition is not legal in the current state:
  validate integration s
           ^^^^^^^^^^^

Legal transitions:
  regression required
  → validate regression
```

27. Legal prefix but no state-valid completion, with state
`integration result pending` and only `failed` legal:

```text
RepoWorkflow error: no completions available from the current state:
  validate integration s
                       ^

Legal transitions:
  integration result pending
  → validate integration failed
```

28. Bare catalogue completion miss:

```text
RepoWorkflow error: no completions available for:
  validate regression --group z
                              ^
```

The catalogue miss must not contain `Legal transitions:`.

29. A callable provider returning `list[str]` produces the same generic
    catalogue-miss diagnostic as a literal `list[str]`.
30. If several descendants lie below one state-invalid token, only the first
    invalid token is diagnosed once.
31. A state-related diagnostic contains exactly one `Legal transitions:`
    block.
32. State display names contain spaces as documented and do not expose
    hyphenated/internal state identifiers.
33. Manual execution and completion of the same invalid path identify the same
    first mismatch and render the same diagnostic body.

### Completion candidates and descriptions

34. Prefix matching returns only candidates beginning with the literal current
    partial token.
35. Static described commands expose their description to detailed completion.
36. Dynamically returned described commands expose their description.
37. Bare `list[str]` values never acquire synthetic descriptions.
38. When a node is executable and has continuations, normal completion can
    present `<last-terminal>`.
39. `<last-terminal>` is presentation-only and is never returned as an
    insertable command token.

### Real Bash completion

These tests source the shipped Bash script and directly set `COMP_WORDS`,
`COMP_CWORD`, and any completion-state variables.

40. Both `repo-workflow` and `rwf` are registered.
41. In `integration result pending`,
    `rwf validate integration <TAB>` returns exactly the legal result
    candidates plus terminal presentation when applicable.
42. A partial legal token completes normally.
43. A partial state-invalid token prints the documented state-aware diagnostic
    and leaves `COMPREPLY` empty.
44. A bare catalogue miss prints the generic catalogue diagnostic and leaves
    `COMPREPLY` empty.
45. Controlled positions do not fall back to filesystem completion.
46. Completion failure cannot invoke a workflow mutation.
47. A second Tab within the documented timing/context window renders
    descriptions for described static/dynamic candidates.
48. Changing command line, cursor/current word, or completion context resets
    the double-Tab state.
49. Bare catalogue names remain names-only on repeated Tab.

### Workflow CLI and version forwarding

50. `what-next` text and `what-next --json` expose the same transition set
    and blocked reasons.
51. `version` and `version --json` query the repository-owned adapter.
52. `version task issue N` forwards `task --issue N`.
53. `version integrate increment patch` forwards
    `integrate --increment patch`.
54. `version integrate increment minor` forwards
    `integrate --increment minor`.
55. `version release-major` forwards `release-major`.
56. RepoWorkflow never constructs a literal target version for those semantic
    mutations.
57. ART FAIL advances only `R` by exactly one through
    `task --increment CI-iteration`.
58. Integration FAIL advances `Q`, resets `R`, and leaves the issue
    component `P` unchanged through
    `task --increment merge-integration-failed`.
59. Adapter query/mutation may change only the documented worktree state and
    must not move HEAD, create commits, or mutate Git refs.
60. `repo-workflow` and `rwf` execute equivalent public commands.

### Repository invariants

61. Every issue #15 test leaves its temporary repository clean unless the
    tested transition explicitly commits documented bookkeeping.
62. Failed parsing, failed completion, and blocked state transitions leave the
    repository/workflow state unchanged.
63. The full pre-existing RepoWorkflow suite remains GREEN.
64. The issue branch passes the repository's authoritative local/hosted
    validation on the exact final candidate.

