# Six-State Ticket Lifecycle and Graph Status Contract

Status: implementation contract for #577, specified in #579.

## 1. Source of truth

The canonical lifecycle store and its append-only transition history are the
sole authority for issue lifecycle state and dependency satisfaction.
`.repoworkflow/tickets.csv` contains a materialized, validated state
projection for offline graphing. It must not independently advance state.

The CSV projection must be tied to the exact authoritative lifecycle revision
for every represented issue. A consumer must reject stale, mismatched, missing,
or malformed state rather than silently trusting the projection. Lifecycle and
ticket-state changes requiring both stores use a recovery-safe transaction:
they either produce a consistent committed snapshot or explicitly stop with
a recoverable incomplete state. No partial update counts as completion.

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
`issue,title,dependencies,state`.

The fourth field must be one of the six canonical state identifiers; no
empty or unrecognized value is accepted for fully migrated records. Migration
must read canonical lifecycle authority for each ticket, refuse inconsistent
history or unreadable state, and write a complete verified snapshot. The
transaction also binds each projection to authoritative lifecycle revisions
via the versioned synchronization evidence; a naked `state` cell is not
sufficient evidence of freshness.

Title remains provider-owned; dependency synchronization retains its existing
explicit authority by direction. Neither `from-tickets` nor `to-tickets`
may treat provider open/closed state as the RWF lifecycle or push a lifecycle
transition by copying the CSV status cell.

Three-way ticket-CSV merges preserve semantic title/dependency rules and
reject divergent state projections unless they reconcile against authoritative
lifecycle revisions. No last-writer-wins state merges.

## 6. Graph `--current`

The switch annotates every displayed ticket with its authoritative lifecycle
state and the glyph in section 2. It must not change dependency edges, node
order, routing, or selected-worktree context. Without the switch, graph output
must remain backward compatible. It is read-only: no provider calls, writes,
implicit refresh, or lifecycle transitions.

Missing, stale, inconsistent or corrupt authoritative state must produce an
explicit diagnostic rather than a falsely complete graph. A valid absence
historically proven by the lifecycle store is `not_started`.

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
read-only behaviour, all supported graph layouts, and legacy output without
`--current`.

Do not certify until issue-focused, regression, integration and repository CI
checks are GREEN for the exact implementation candidate.
