# Static Test Catalogue and Rosetta Translation

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

