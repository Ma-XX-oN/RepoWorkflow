# Six-State Ticket Lifecycle and Graph Status Contract

Status: implementation contract for #577, specified in #579.

## 1. Source of truth

The canonical lifecycle store and its append-only transition history are the
sole authority for issue lifecycle state and dependency satisfaction.
`.repoworkflow/tickets.csv` contains a materialized, validated state
projection for offline graphing. It must not independently advance state.

Normal graph rendering reads stored state from tickets.csv without refreshing
lifecycle records. This is an intentional offline snapshot, which can be older
than canonical lifecycle history. The CSV projection carries the revision of
the lifecycle snapshot it represents; malformed or internally inconsistent
snapshots fail closed. Only an explicit --current operation refreshes each
displayed ticket state from authoritative lifecycle records and updates CSV.
Refresh is transactional: either the entire requested state snapshot is written
and verified, or the previous CSV snapshot is preserved. No partial update
counts as successful refresh.

GitHub issue `open` / `closed` is separate provider status; it cannot
overwrite or satisfy an RWF lifecycle. Worktree-local `current` or selected
issue is navigation state, not the state of every graph node.

## 2. States and status glyphs

| State | Glyph | Meaning |
| --- | --- | --- |
| `not_started` | ○ | No successful work start |
| `active` | ● | Implementation/rework underway |
| `in_review` | ◎ | Review or required validation pending |
| `accepted` | ✓ | Review and acceptance validation passed |
| `completed` | ♥ | Durable workflow completion |
| `aborted` | ✕ | Work abandoned without completion |

`completed` is the sole dependency-satisfying state. `accepted` must not
satisfy a dependency. `ready` and `blocked` remain derived classifications
of `not_started` or `aborted` from direct dependency state; they are not
additional lifecycle states. Glyphs must be one terminal cell, in a
monochrome-compatible presentation, tested on supported platforms.

## 3. Transitions

| From | Event | To |
| --- | --- | --- |
| `not_started` | `start` | `active` |
| `active` | `submit-review` | `in_review` |
| `in_review` | `accept` | `accepted` |
| `in_review` | `reject/reopen` | `active` |
| `accepted` | `reject/reopen` | `active` |
| `active` | `abort` | `aborted` |
| `aborted` | `re-enter` | `active` |
| `accepted` | `complete` | `completed` |

Only these transitions are legal. A validation failure during active work
records validation evidence without making a fictitious same-state lifecycle
transition. Entry to `in_review` requires an exact candidate and a submitted
review or pending validation request. `accept` requires authoritative
successful exact-candidate review and required validation evidence. Completion
requires the separately defined integration and authorization gates.

An interrupted review must use `reject/reopen` to return to active before
aborting; a new abort transition from `in_review` is not implicit.

## 4. Schema upgrade and history

Define lifecycle schema version 3 to represent the six states.
Versions 1 and 2 remain readable. Project old `unstarted` to
`not_started` only after the canonical reader proves that no successful
start or lost historical record exists. Preserve original append-only history
and original event names for pre-migration records; presentation normalization
must not silently rewrite history. A successful version-3 write retains the
historical event sequence and emits the new version. Older `active -> accepted`
records remain valid historical transitions, but new version-3 transitions
follow the table above. No invented `submit-review` event is inserted into
legacy history.

All writes check the expected revision and fail closed on stale inputs.
Missing a record that previously existed is corruption/recovery, not
`not_started`.

## 5. CSV state projection

Current three-column CSV format:
`issue,title,dependencies`.

New format:
`issue,title,dependencies,state,state_revision`.

The fourth field must be one of the six canonical state identifiers; the fifth
records the lifecycle revision sampled during explicit refresh (empty only
for a provably not-started issue). No
empty or unrecognized value is accepted for fully migrated records. Migration
must read canonical lifecycle authority for each ticket, refuse inconsistent
history or unreadable state, and write a complete verified snapshot. The
refresh binds the projection to the lifecycle revisions sampled during that
refresh. The stored state does not promise live freshness between refreshes.

Title remains provider-owned; dependency synchronization retains its existing
explicit authority by direction. Neither `from-tickets` nor `to-tickets`
may treat provider open/closed state as the RWF lifecycle or push a lifecycle
transition by copying the CSV status cell.

Three-way ticket-CSV merges preserve semantic title/dependency rules and
reject divergent state projections unless they reconcile against authoritative
lifecycle revisions. No last-writer-wins state merges.

## 6. Graph `--current`

Normal graph commands render every visible ticket's stored state and glyph
from tickets.csv without a lifecycle refresh, provider call or write.
The --current switch explicitly reads canonical lifecycle state, refreshes
the corresponding CSV state projection, verifies the persisted update and then
renders the refreshed values. It must not modify relationships, titles,
worktree selection or lifecycle transitions. Failure to read canonical state
or commit the full refresh leaves the original CSV intact and reports an error.
A valid historical absence proven by the lifecycle store is not_started.
Do not infer fresh lifecycle truth from a stale cached CSV snapshot.

## 7. Verification gates

Independent black-box tests derive all transitions and rejected transitions
from this table; use distinct structural/implementation tests. Cover legacy
history with and without prior accepted events, all six states, exact candidate
and stale revisions, restart, abort/re-entry and review rejection, invalid
transition recovery, and dependency satisfaction.

CSV tests cover zero/one/many tickets, strict schema versions, migration,
round-trip, atomic failure/retry, provider sync independence, concurrent
updates, three-way merge, cross-clone refresh and authoritative revision
binding. Graph tests cover all glyphs, terminal widths/platforms, no-colour,
normal-mode read-only behaviour, explicit --current update/readback/failure
atomicity, and all supported graph layouts.

Do not certify until issue-focused, regression, integration and repository CI
checks are GREEN for the exact implementation candidate.
