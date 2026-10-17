# JavaScript executable-interface record/playback (issue #670)

This is the standalone Node 22+ **JavaScript first draft** of RepoWorkflow's
generic interface recorder/player, based on the Python *design* in [#518](../../issues/518)
and [#553](../../issues/553). The Python engine itself is **not yet implemented
on main**; cross-language byte-for-byte compatibility remains unverified.

## Entry point

`testing/javascript/interface-playback.mjs` exports `InterfacePlayback`,
`Free` and `validateInteraction`. It imports only Node standard-library modules, including the adjacent
`interface-stream.mjs` bounded JSONL reader and has no RepoWorkflow CLI dependency.

Public operations:

- `record(filter, invoke, receiver, functionName, args = [], kwargs = {})`
  executes the implementation, takes before/after snapshots, filters the
  interaction and returns/rethrows the real result.
- `load(source)` accepts an in-memory interaction array, JSON path, or JSONL
  path. JSONL is validated in an independent forward scan and replayed lazily
  with a bounded one-line buffer (1 MiB maximum interaction line). The
  recording-wide identity map stores logical IDs, not interaction bodies.
  `new InterfacePlayback({ maxLineBytes: N })` sets a larger explicit bound
  for legitimate large interactions; the default is 1 MiB.
  Malformed/truncated lines, duplicate `$new` and forward/unknown `$ref`
  fail during loading before any user call executes.
- `save(path)` writes one canonical interaction per JSONL line; saving a
  lazy-loaded source uses an independent reader without consuming the replay
  cursor.
- `replay(receiver, functionName, args = [], kwargs = {})` verifies the
  next recorded interaction and reproduces mutations/return/exception.
- `test(invoke, receiver, functionName, args = [], kwargs = {})` executes
  and compares the live implementation to recorded consequential behaviour.
- `reset()` restarts playback from the first interaction.

The `Free` sentinel represents free functions. JavaScript kwargs are explicitly
supplied as a final object to `invoke` when the `kwargs` map is nonempty;
this is an intentional JavaScript adapter, **not** Python keyword calling.

## Tests

`node --test tests/interface-playback.test.mjs`

Only constructed synthetic test data is committed. For AICC #127, any original
`.mlog.zst`, extracted backend response body, cookie, token or authenticated
capture must remain **outside every Git repository**. This library does
**executable interface replay**, not raw HTTP packet/HAR playback; a separate
adapter must translate captured network events into calls to the real host
interface.

## Limits / compatibility

- Only JSON-native finite scalars, lists, plain objects and enumerable fields
  of explicitly supplied custom instances are supported. Native Date, Map,
  Set, buffers and typed arrays are rejected.
- Type restoration for custom objects requires trusted constructor mappings;
  arbitrary constructor loading is not supported.
- JSONL replay is lazy and bounded per line, although identity validation
  retains recording-local logical identifiers and performs a complete
  preflight scan. In-memory array and `.json` inputs remain materialized.
- Full compatibility with a future Python executable implementation remains
  an explicitly separate gate.
- Selective `$unchanged` is verified during `test()` against pre-call state.
  `replay()` preserves those fields without applying a recorded mutation.
- A source-compatible JavaScript abstraction does not establish parity with
  the unfinished Python implementation or authorize #518/#561 closure.
- Test-only module. It is not part of a RepoWorkflow or DC production build.

Do not merge #670 until the open acceptance gaps are resolved and the exact
hosted candidate is certified.
