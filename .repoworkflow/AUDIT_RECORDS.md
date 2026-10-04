# Published-lane workflow audit records

Published-lane workflow audit reports are immutable per-run records under
`.repoworkflow/audit/`.

The historical `.repoworkflow/log.md` is legacy audit data.  Preserve it
unchanged and do not add new published-lane reports there.

## Record path

Each worker/run selects one path before creating its report:

`lane-<lane>-<issue-sequence>--<uuid>.md`

The lane and issue components support deterministic enumeration and grouping.
The final component is a freshly generated RFC 4122 UUID for the worker/run,
providing collision resistance independently of clocks.

Create the selected path once.  If it already exists, creation fails and the
worker selects a new UUID.  Normal workflow operations never update an existing
record.

## Invariants

- One worker/run creates its own audit record.
- Never modify another worker's audit record.
- Never combine two audit records into one.
- A committed audit record is immutable.
- Concurrent workers use different paths and do not share an append target.
- Audit evidence is not dependency, lifecycle, or provider authority.
- New records do not modify the legacy `.repoworkflow/log.md`.

The workflow requirement and concurrency verification are tracked by #250.
