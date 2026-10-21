# Manual integration test declarations (RWF #700)

Manual integration tests (MIT) are **declarations, not runnable harness tests**.
They share the authoritative `.ci/tests.json` with automatic tests.  A manual
case belongs to the current issue exactly when its complete name matches
`issue-X-manual--NAME`, where `X` is a positive decimal ticket ID without
leading zeros and `NAME` matches `[A-Za-z0-9][A-Za-z0-9_-]*`.

Use the existing `tests` array and its existing `test-harness` grouping.
Manual entries require **exactly** `type`, `instructions`, and
`expected_result`.  The selected harness must exist in `test-harnesses`,
but the manual entry intentionally has **no** native `name`, `command`,
script path, or executable body.  An operator follows the instructions and
checks the expected result; RWF must never submit a manual case to the normal
`group_command` / automated test runner.

Example addition inside the existing `tests` array:

```json
{
  "test-harness": "unittest",
  "issue-700-manual--validate-case": {
    "type": "manual",
    "instructions": "Inspect the live integration candidate and record its SHA.",
    "expected_result": "The inspected SHA matches the selected candidate."
  }
}
```

The `unittest` harness in this example is an **existing declaration grammar
anchor**, not an instruction to execute the manual case using unittest.
Automatic groups keep their existing `type` and `name` and are unaffected.
Do not add a second manual-test catalogue or put manual definitions in aliases.

`read_manual_cases(root, issue)` returns an immutable tuple of frozen
`ManualCase(name, instructions, expected_result, definition_digest)` records,
sorted lexicographically by complete case name, independent of declaration
layout.  `find_manual_case(root, issue, name)` resolves the requested exact
case or rejects it; it never substitutes another issue's case.  Zero manual
cases means there is **no MIT requirement from this catalogue**.

Each `definition_digest` is lowercase SHA256 of canonical UTF-8 JSON:
`{"schema":"rwf-manual-case-v1", "name": ..., "metadata": ...,
"test-harness": ..., "harness-definition": ...}` using sorted object keys,
compact separators, and unescaped Unicode.  The digest covers the complete
manual definition and its harness identity, not unrelated cases.  The durable
result layer must ALSO bind PASS to the exact candidate source SHA/current
issue.  A changed definition makes its former result stale.  Test selection
itself makes no file, branch, or state mutation.

The reader validates `.ci/tests.json` using the repository's existing
`parse_test_catalogue` grammar, rejects repeated JSON keys, duplicate groups,
invalid/missing manual metadata, wrong manual names, unknown harnesses, and
malformed JSON.  An automatic group containing the substring `manual--` is
**not** a manual case merely because of that substring.  A group beginning
`issue-X-manual--` but lacking `type: manual` is rejected; likewise an entry
with `type: manual` but an invalid name.  Properly declared cases for other
issues remain in the shared catalogue but are not returned for this issue.

## Assembly requirement for RWF #699 / #702

At the inspected main revision, `self_ci.issue_verification_groups()` selects
all `issue-X-` groups without checking `type`, and `self_ci.group_command()`
requires a native `name`.  Integrating manual cases into a live test catalogue
therefore requires the CLI / integration planner to exclude them from
**every automated execution path** and present them as manual work only.
Do not repair this by adding a runnable `name` or executable harness command
to a manual group, or by relaxing automatic group validation.  Changes to
shared selectors must be reserved by the controller and the owning worker.

The catalogue reader does not execute a command, record a PASS/FAIL, decide
whether a result is outstanding, or advance any lifecycle state.  Those
separate responsibilities belong to RWF #701–#703 and convergence #699.
