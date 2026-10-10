# Issue #628 — on-demand hosted trigger acceptance matrix

This is an independent, specification-derived test plan, not hosted execution evidence.
The implementation contract is `.ci/run` containing `<stage> <full pre-invocation tip SHA>` in a dedicated request commit. The request must be rejected when its ancestry or candidate identity changes. The trigger must not run hosted tests on ordinary pushes or read-only retrieval.

| Case | Setup/event | Expected hosted test jobs | Expected decision |
| --- | --- | --- | --- |
| T00 | No `.ci/run` request event | 0 | No invocation |
| T01 | One valid dedicated marker-only request commit | 1 requested stage | Accept exact parent SHA |
| T02 | Two valid sequential requests, each with own parent | 2 corresponding invocations | Distinct request identity |
| T03 | Retry same valid request after missed delivery | 1 effective invocation per request identity | Idempotent recovery |
| T04 | Ordinary source-only push | 0 | Excluded |
| T05 | Ordinary push to `main` | 0 | Excluded |
| T06 | Ordinary push to `prelim-main` | 0 | Excluded |
| T07 | Read-only result retrieval | 0 | No mutation/trigger |
| T08 | Marker changed in worktree without request commit | 0 | Ignore mutable worktree |
| T09 | Committed malformed marker or invalid stage | 0 | Reject |
| T10 | Marker SHA differs from request's parent | 0 | Reject stale/changed candidate |
| T11 | Request commit also modifies source | 0 | Reject non-dedicated commit |
| T12 | Request parent absent or ancestry inconsistent | 0 | Reject |
| T13 | Multiple marker edits in same push | 0 unless a valid single request commit is independently established | Fail closed on ambiguous event |
| T14 | Valid marker but unexpected push ref | 0 | Exclude unapproved ref |
| T15 | Replayed webhook or duplicate delivery | 1 effective invocation per request identity | Idempotent |

## Provider evidence required before DONE

For each case record: source commit SHA, request commit SHA (if any), branch/ref, workflow ID, event/delivery ID when available, observed workflow runs and hosted job counts, provider run URL, result and collection time. Establish a zero-job observation window for negative cases and record the observation window. Distinguish workflow not triggered from workflow triggered with jobs skipped. Use the exact candidate SHA for both source and run evidence. Compare the resulting observations against the expected matrix above. Provider-backed negatives cannot be replaced by static YAML inspection.

## Test adequacy

Black-box cases: T00–T15, derived from issue #628 and prerequisite #540. Structural verification separately checks workflow event/path/ref filters, parser entry points, ancestry checks, and idempotency storage. A real provider test must not activate an unapproved workflow or merge any branch. Until provider observations and reproducible CI exist, this document is a preparatory artifact and #628 remains OPEN.
