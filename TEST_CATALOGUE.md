# Static Test Catalogue and Rosetta Translation

Issue #14 extends the validation design toward a static, language-agnostic test
catalogue.  This subsection records the settled design decisions reached so far;
the complete schema and TDD policy remain under design and are not frozen here.

The authoritative repository catalogue is `.ci/tests.json`.

The executable stage vocabulary is **RED, GREEN, temporary, regression, and
integration**. Catalogue group metadata uses `type: regression` or
`type: integration` for retained automated suites, and `type: manual` only
for separately authorized manual integration cases. `type: invariant` is invalid:
an invariant is a requirement being tested, not a separate RWF execution
stage. Issue-specific RED/GREEN selectors are named `issue-<number>-...`;
the optional temporary catalogue is `.ci/temp-tests.json`. Do not infer
that unregistered files are automatically regression tests, or migrate
short-lived tests into retained suites without verifying their ownership
and value.

`aliases` are **named associations of already registered group keys**,
used for durable high-risk group expansion and other named selections.
They do not define the regression or integration stages; stage membership
is defined by per-group `type`. An integration stage includes the
applicable broad regression obligations and integration-only probes as
specified in `TEST_STRATEGY.md`.



The catalogue has three top-level collections: `test-harnesses`, `tests`,
and `aliases`.  `test-harnesses` is the Rosetta dictionary.  Each key names
a harness and its value describes how native test targets are translated into
process arguments.  `tests` is an array of test declaration objects.  Each
declaration selects a Rosetta entry with `test-harness` and maps RWF group
keys to native targets.  `aliases` maps semantic section names to canonical
group keys already declared under `tests`.

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
  ],
  "aliases": {
    "parser": [
      "issue-123-empty-input",
      "issue-123-null-input"
    ]
  }
}
```

Alias names are semantic coverage sections, not executable groups.  Alias members
must name canonical group keys declared in `tests`; an unknown member fails the
catalogue closed.  Aliases do not reference other aliases, so expansion is
one-level and deterministic.  Multiple aliases expand by set union and duplicate
group keys collapse to one selected group.  Alias membership does not imply
complete regression coverage.

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

For the current inventory of test modules not yet directly registered, see
[the unregistered module classification review](TEST_CLASSIFICATION_REVIEW_20261031.md).
This review is not a reason to automatically promote unverified candidates;
each retained or retired group needs issue-contract evidence.

The catalogue is static.  The **intended** retained regression membership
comes from entries whose metadata says `type: regression`; integration entries
mark the separate cross-boundary stage. Fast selection is derived from speed
metadata; group selection matches canonical group keys. Separate manually
maintained aggregate suite membership is intentionally avoided because it
would create multiple places that must remain synchronized.

**Current implementation gap:** RepoWorkflow engine `rwf test regression`
still delegates to `scripts/validate.py`, which executes broad filesystem
unittest discovery rather than selecting registered group targets by stage.
`rwf test integration` runs that broad validation plus platform probes.
Therefore the catalogue's intended stage-based full selection is **not yet
implemented**, even though individual named-group selection and `.ci/run`
invocation are implemented. Do not represent discovery-only test results as
proof of catalogue selection. The reviewed modules and retire-or-retain
decisions must be resolved before switching the broad runner to catalogue-only
selection, so required test coverage is not silently dropped.

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

