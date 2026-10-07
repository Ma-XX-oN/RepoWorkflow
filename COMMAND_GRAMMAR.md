# Declarative Command Grammar and Completion

Status: authoritative command/completion contract for issues #51/#52.

RepoWorkflow uses one Python-owned recursive command structure as the source for
argument validation, completion candidates, completion help, normal `--help`,
and shared diagnostics.  Shell adapters render that structure; they do not
maintain independent command policy.

## 1. Static command tree

The human-authored form remains a plain recursive dictionary.

Conceptually:

```python
Description = str
CommandEntry = Description | CommandNode
CommandNode = dict[str, CommandEntry | ValueProvider]
ValueProvider = Callable[[Context], CompletionSpec]
```

Structural rules:

- `""` is optional; when present it maps to the description for executing the
  current node as-is.
- literal command alternatives remain recursively nested dictionary entries;
- dynamic positional values use `"_values"`;
- switches are declared under `"_switches"`;
- ordered positional continuations use `"_ordered"`;
- switch positional parameters use `"_params"`;
- `"_quantifier"` applies to the construct beside which it is declared;
- ordinary authored command tokens and parameters have descriptions;
- `<last-terminal>` is presentation-only and never an authored or parseable
  token;
- unsupported special keys such as `_for-states` are invalid.

The complete authored forms are:

```python
"<param>": "<help>"
"<param>": param_completion_fn

"--<switch>": "<help>"
"--<switch>": {
  "_params": [
    {
      "<param0-opt0>": ...,
      "<param0-opt1>": ...,
      "_quantifier": "...",
    },
    {
      "<param1-opt0>": ...,
      "<param1-opt1>": ...,
      "_quantifier": "...",
    },
  ],
  "_quantifier": "...",
}

"<cmd>": "<help>"
"<cmd>": {
  "_values": completion_fn,
  "_value_description": "<help>",
  "_quantifier": "...",
}
"<cmd>": {
  "_switches": {
    "--<switch0>": ...,
    "--<switch1>": ...,
  }
}
"<cmd>": {"_switches": switch_completion_fn}
"<cmd>": {
  "<cmd-opt0>": ...,
  "<cmd-opt1>": ...,
  "_quantifier": "...",
}
"<cmd>": {
  "_ordered": [
    {"<cmd0-opt0>": ..., "<cmd0-opt1>": ...},
    {"<cmd1-opt0>": ..., "<cmd1-opt1>": ...},
  ],
  "_quantifier": "...",
}
```

`completion_fn` returns a list of completion item strings.
`switch_completion_fn` returns the valid switch dictionary for the current
context.  `param_completion_fn` returns the valid positional-parameter
dictionary for the current context.

Quantifier scope is structural:

- inside one `_params` position, it controls that parameter position;
- beside `_params`, it controls occurrences of the switch itself;
- beside `_ordered`, it controls repetitions of the complete ordered sequence;
- beside `_values`, it controls dynamic positional-value cardinality;
- beside a dictionary of terminal command/parameter alternatives, it controls
  how many alternatives from that choice group may be consumed.

A repeated choice group is unordered: each occurrence may select any declared
terminal alternative.  A repeated multi-token structure must use `_ordered`
so its return/sequence boundary is explicit rather than inferred from nested
command recursion.

The general quantifier default is `{1}`.  A switch declaration is optional by
being a member of `_switches`; when its switch-level quantifier is omitted it
may occur at most once.  A switch-level `*` or `+` therefore permits repeated
occurrences without changing whether the switch is otherwise selected.

Quantifier syntax is regex-style: `?`, `*`, `+`, `{n}`, `{n,}`, and
`{n,m}`.

## 2. Ordered parameters and switch parameters

An ordered slot is one dictionary of alternatives.  Literal keys match
themselves.  Angle-bracket parameter keys describe positional values.  A
callable parameter alternative resolves the valid values for the current
context.

For example:

```python
"move": {
  "_ordered": [
    {"<ISSUE>": issue_completion_fn},
    {"to-lane": "Move to lane"},
    {"<LANE>": lane_completion_fn},
  ],
}
```

represents:

```text
move ISSUE to-lane LANE
```

A repeatable parameterized switch is represented without losing either
cardinality:

```python
"--follow": {
  "_params": [
    {
      "initiative": "Follow initiative boundary",
      "epic": "Follow epic boundary",
      "feature": "Follow feature boundary",
      "group": "Follow any group boundary",
      "back-only": "Traverse toward dependencies/root only",
    },
    {
      "<N>": count_completion_fn,
      "_quantifier": "?",
    },
  ],
  "_quantifier": "*",
}
```

Parser, completion, help, and diagnostics consume these exact structures.

## 3. One dynamic provider result contract

Every dynamic `_values` provider returns one explicit completion
specification:

```python
{
  "completions": [...],
  "on-tab": completion_handler,
}
```

`on-tab` is optional.  Absence means the default handler.

The provider contract must not assign semantics by Python return-type shape.
A provider does not sometimes return `list[str]`, sometimes
`list[dict]`, or a special single string with implied behaviour.

`completions` may contain whatever validated completion-entry representation
the grammar/compiler defines for:

- catalogue-owned values;
- described command fragments;
- state-derived legal transitions.

The distinction belongs to the completion entries/specification, not to the
outer Python container type.

A custom `on-tab` handler is the first-class escape hatch for exceptional
completion presentation or insertion behaviour.  Shell-specific concepts such
as whether a completion adds a trailing space belong in the handler/adapter,
not in the semantic command grammar.

## 4. Dynamic state projection

There is no separate `_for-states` field.

A provider receives `Context`, consults the authoritative state/repository
model, and returns only the appropriate completion specification.

Example:

```python
def get_integration_next(context: Context) -> CompletionSpec:
  state = get_workflow_state(context)
  completions = []

  if state.manual_integration_pending:
    completions.extend([
      {"succeeded": "Report integration tests succeeded"},
      {"failed": "Report integration tests failed"},
    ])

  return {"completions": completions}
```

General-syntax diagnosis may evaluate a general projection while legal
completion evaluates the current-state projection, but both come from the same
authored command tree/providers.

## 5. Catalogue completion

Repository-owned catalogues remain authoritative for their identifiers and
metadata.  The grammar does not duplicate those definitions.

For example, issue-scoped TDD group completion may return:

```python
{
  "completions": [
    "issue-173-parser",
    "issue-173-version",
  ],
  "on-tab": issue_tdd_group_handler,
}
```

Ordinary shell completion may derive and insert the common prefix
`issue-173-` when several candidates match, or the full name when only one
matches.

The custom handler may produce contextual diagnostics such as:

```text
RepoWorkflow error: no TDD test group exists for issue 173.

Expected a group named:
  issue-173-...

Test catalogue:
  <repository-declared catalogue location>
```

That runtime diagnosis is distinct from descriptive help.

## 6. First Tab, double Tab, and --help

One Tab performs ordinary completion or a contextual completion diagnostic.

A second Tab within the same completion context displays descriptive help for
that grammar position.  Changing line, cursor/current word, or completion
context resets the double-Tab state.

`--help` is accepted after every valid command prefix and exposes the same
semantic help as double Tab, formatted as ordinary command help.

Therefore these two surfaces are equivalent in content:

```text
rwf issue info <TAB><TAB>
rwf issue info --help
```

For issue information, double Tab may show matching issue numbers and titles
while single Tab inserts/completes issue numbers.

Contextual first-Tab/runtime errors must be actionable.  `--help` should
explain command usage/configuration rather than merely repeat the runtime error.

## 7. Executable nodes and <last-terminal>

When a node is executable as-is and also has continuations, completion may
present its current-node action as:

```text
<last-terminal>
```

The sentinel is display-only.  It is never inserted into the command line and
is rejected if typed manually.

## 8. Shared diagnostics

Parsing, manual execution, and completion use one command-path analyser.

Diagnostics:

- preserve literal typed input;
- identify the first failing token/span;
- never invent a hypothetical completion to explain an error;
- distinguish unknown grammar from state-illegal transitions and
  completion-specific failures;
- remain read-only.

State-related diagnostics include one human-readable state line and the legal
transitions exactly once when that information is relevant.

Example:

```text
RepoWorkflow error: transition is not legal in the current state:
  validate integration s
           ^^^^^^^^^^^

Legal transitions:
  regression required
  → validate regression
```

A legal state-derived prefix whose partial token matches no current candidate
may report:

```text
RepoWorkflow error: no completions available from the current state:
  validate integration s
                       ^

Legal transitions:
  integration result pending
  → validate integration failed
```

Catalogue/custom handlers may instead provide domain-specific diagnostics, such
as the missing issue-scoped TDD group error in section 4.

## 9. Shell adapters

Bash, zsh, and other supported shells are presentation adapters.

They may implement shell-specific mechanics required by `on-tab`, but must not
duplicate command legality, workflow state, catalogue policy, or diagnostics.

Shell initialization is emitted through commands such as:

```text
rwf init bash
rwf init zsh
```

The platform-neutral Python engine remains authoritative.

## 10. Read-only completion invariant

Completion/help/diagnostic paths must not:

- execute a workflow transition;
- change version state;
- create commits/tags/branches;
- alter `.repoworkflow` durable state;
- run destructive repository operations.

Tests must prove that failed and successful completion leave workflow/repository
state unchanged.

## 11. Implementation ownership

Issue #52 owns migration from the return-shape-coupled provider model to the
explicit completion specification.  Issue #456 owns the quantified command,
switch, parameter, and ordered-position grammar described above.

Issue #54 owns issue-scoped TDD group completion/diagnostics.

Issue #27 owns shell initialization/registration.

The complete public command model is defined in
[PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md).
