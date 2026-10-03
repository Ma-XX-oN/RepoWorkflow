# Declarative Command Grammar and Bash Completion

Issue #15 uses one Python-owned command data structure as the authoritative
description of the user-facing CLI grammar.  Argument parsing/validation,
shell-completion candidates, completion help, and normal command help must be
projections of that structure rather than independently maintained command
lists.

The authoritative human-authored form is a plain recursive Python dictionary.
A separate validator/compiler checks that structure at module load/test time
and may convert it into a richer runtime representation.  Human-facing command
definitions should remain data-first rather than requiring verbose
`CommandNode(...)` constructor syntax.

Conceptually, the recursive type is:

```python
Description = str

CommandEntry = Description | CommandNode

DynamicCommand = dict[str, CommandEntry]

DynamicResult = list[str] | list[DynamicCommand]

ValueProvider = Callable[[Context], DynamicResult]

ValueSource = list[str] | ValueProvider

CommandNode = dict[str, CommandEntry | ValueSource]
```

The loose type above is intentionally supplemented by structural invariants
that Python's normal `dict` type cannot express directly:

- `""` is optional and, when present, must map to a description string.  It
  means the command represented by the current node is valid as-is.
- `"_values"` is optional and, when present, must be either a static
  `list[str]` or a callable taking the current `Context`.
- every other key is a literal next command token and must map to either a
  description string or another valid `CommandNode`.
- ordinary command tokens always have descriptions.
- bare strings returned by `_values` are reserved for externally described
  values such as test-group names.  Their metadata remains in the authoritative
  source that owns those values rather than being duplicated in the command
  grammar.
- a callable `_values` provider may instead return described command-tree
  fragments.  This is the dynamic form used when current repository/workflow
  state determines which command transitions are legal.

For example:

```python
COMMANDS = {
  "validate": {
    "regression": {
      "": "Run all regression tests",
      "--fast": "Run fast smoke tests",
      "--group": {
        "": "Run a specific regression-test group",
        "_values": get_regression_group_names,
      },
    },
    "integration": {
      "": "Start validating integration tests",
      "_values": get_integration_next_commands,
    },
  },
  "what-next": {
    "": "Show legal next workflow transitions",
    "--json": "Output workflow guidance as JSON",
  },
}
```

A descriptionless value provider is appropriate for catalogue-owned identifiers:

```python
def get_regression_group_names(context: Context) -> list[str]:
  return get_test_catalogue(context).regression_group_names()
```

Those returned strings are valid next tokens, but the command grammar does not
invent or duplicate descriptions for them.

State-dependent command transitions use the same `_values` mechanism.  The
provider inspects the current context/state and returns normal described command
nodes:

```python
def get_integration_next_commands(
  context: Context,
) -> list[dict[str, str | dict]]:
  state = get_workflow_state(context)

  if state.manual_integration_pending:
    return [
      {
        "succeeded":
          "Report integration tests succeeded",
      },
      {
        "failed":
          "Report integration tests failed",
      },
    ]

  if state.automatic_integration_pending:
    return [
      {
        "--automatic":
          "Run automated integration tests",
      },
      {
        "--group": {
          "": "Run a specific integration-test group",
          "_values": get_integration_group_names,
        },
      },
    ]

  return []
```

There is deliberately no separate `_for-states` field.  Static grammar is
encoded directly in the tree.  Dynamic legality is obtained by calling
`_values` with `Context`; that provider consults the authoritative state
machine and exposes only the valid next command nodes/tokens.

The validator/compiler must reject malformed command data at startup/test time.
At minimum it must enforce the special-key rules above and recurse through both
static nodes and any validated runtime node representation.  The implementation
may use a `CommandNode` class internally after validation, but the
authoritative definition remains the plain dictionary tree.

The empty-string terminal has a completion-only presentation.  It is not a
literal shell token.  When the current node is executable as-is and also has
valid continuations, completion may render the current-node action as
`<last-terminal>`.  For example:

```text
rwf validate integration <TAB>

<last-terminal>  succeeded  failed
```

A second Tab within one second, with the same command line and completion
context, may show:

```text
<last-terminal>    Start validating integration tests
succeeded          Report integration tests succeeded
failed             Report integration tests failed
```

`<last-terminal>` must never be inserted into the command line or accepted by
the parser.  It is only a display sentinel for the `""` entry.

The Bash adapter is a presentation layer.  It supplies the current command
line/cursor context to the RWF completion engine and receives the candidates
derived from the command grammar and current workflow state.  It must not
duplicate RWF command or state policy.

Parsing and completion use one shared command-path diagnostic model.  The
diagnostic always preserves the literal command tokens the caller typed; it
never invents a hypothetical completion merely to explain an error.  It finds
the first token at which the typed path stops matching either the general
grammar or the currently legal dynamic projection and underlines exactly that
token in the rendered command.

The failure classes are:

- a token that does not exist in the general command grammar is an
  `unrecognised command`;
- a token sequence that exists in the general grammar but is not legal in the
  current workflow state is a
  `transition is not legal in the current state` error;
- a partial token at a legal state-dependent dynamic command position for which
  no legal candidate matches is a
  `no completions available from the current state` error;
- a partial token at a bare `list[str]` value position for which no value
  matches is a generic `no completions available for` error.

The last case is deliberately different because bare values are not workflow
transitions.  This includes both literal `list[str]` declarations and
callable `_values` providers whose resolved result is `list[str]`, such as
test-group catalogues.  No state-transition explanation is rendered for those
value-only positions.

Workflow-command diagnostics for either an unrecognised command or a
state-derived mismatch render one human-readable state line followed by the
currently legal transitions exactly once.  Bare value-list misses are the
exception because they are not workflow transitions:

```text
Legal transitions:
  integration result pending
  → validate integration failed
```

State names are display text such as `integration result pending`, not
hyphenated internal identifiers.  If several possible downstream commands
share the same first illegal token, the diagnostic reports that first failure
once rather than emitting one error for every descendant.

Manual command execution and shell completion must use this same analyser and
produce equivalent diagnostics for the same typed path.  An illegal manually
typed command must fail before mutation; completion must likewise never execute
a workflow mutation while diagnosing or enumerating candidates.

The intended Bash interaction is:

- one Tab performs normal completion and displays/inserts candidate names;
- a second Tab within one second, with the same command line, cursor position,
  current word, and completion context, displays descriptions as additional
  detail;
- changing any of that context resets the double-Tab state;
- described static or dynamic command nodes show their descriptions on the
  second Tab;
- descriptionless `list[str]` values, such as test-group names, remain names
  only on both single and double Tab.

For example:

```text
rwf validate regression <TAB>
<last-terminal>  --fast  --group
```

A second Tab within one second may show:

```text
<last-terminal>    Run all regression tests
--fast             Run fast smoke tests
--group            Run a specific regression-test group
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

