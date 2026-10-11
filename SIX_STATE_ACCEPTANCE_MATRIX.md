# Six-State Lifecycle Independent Acceptance Matrix

Status: normative black-box acceptance contract for #579 and consumers
#580–#583.  Read with [SIX_STATE_LIFECYCLE.md](SIX_STATE_LIFECYCLE.md),
[ISSUE_LIFECYCLE_STATE.md](ISSUE_LIFECYCLE_STATE.md),
[TICKET_STATE.md](TICKET_STATE.md), and
[STATE_CONCURRENCY.md](STATE_CONCURRENCY.md).

This matrix defines expected observations independently of implementation
details.  It does not assert that a test has passed.  Each implementation
worker must record the exact candidate, test command, and result against
these IDs before declaring acceptance.  Historical schema-1/2 behaviour
is preserved as history; it does not license new schema-3 shortcuts.

## 1. Transition oracle

The complete allowed *state-changing* transition set is:

- T01: not_started + start -> active. Evidence: authorized work start
- T02: active + submit-review -> in_review. Evidence: exact submitted candidate
  and review/validation request
- T03: in_review + accept -> accepted. Evidence: required review and validation
  PASS for same exact candidate
- T04: in_review + reject/reopen -> active. Evidence: rejection or invalidated
  review evidence recorded
- T05: accepted + reject/reopen -> active. Evidence: acceptance
  invalidation/rejection recorded
- T06: active + abort -> aborted. Evidence: authorized abandonment and durable
  reason/evidence
- T07: aborted + re-enter -> active. Evidence: authorized new work generation;
  history retained
- T08: accepted + complete -> completed. Evidence: current exact-candidate
  acceptance and separate integration/authorization gates

All other state/request pairs, including same-state repeats, fail closed
without appending a lifecycle transition.  An exact replay of an already
committed request may return an explicitly proven idempotent result, but must
not create a second event or increment the revision.  A changed request,
candidate, expected revision or underlying evidence is not that replay.
Completion is terminal; there is no implicit reopen from completed.
Abort from in_review first requires a legal return to active.

**Matrix test method:** execute each of the eight requests against each
of the six initial states: 48 pairs.  T01–T08 must produce the listed
successors; the other 40 must preserve state, history and revision and return
a rejected/explicitly proven idempotent outcome.  Test the complete request
shape, including mandatory evidence, in each positive row; reject missing,
stale, mismatched and forged inputs independently.  Verify the authoritative
persisted record after each attempt, not only the return code.

## 2. Lifecycle history and evidence oracle

- L01: no record, history proven absent. Expected: normalized not_started; no
  fabricated historical transition
- L02: missing record known to have existed. Expected: recovery failure, never
  not_started
- L03: schema 1 empty history. Expected: read safely; first successful write
  upgrades to 3 without fabricated events
- L04: schema 1 legacy active→accepted. Expected: preserve original event
  names/from/to/sequence; do not invent submit-review
- L05: schema 2 with high-risk aliases. Expected: preserve sorted aliases,
  history and issue identity on upgrade
- L06: schema 1/2 zero, one and many events. Expected: immutable historical
  prefix, exact sequence continuity and correct legacy_event_count
- L07: repeated read/write after upgrade. Expected: deterministic round-trip;
  no spurious event or revision increment
- L08: first start→review→accept→complete. Expected: four appended events;
  correct candidate and transitions
- L09: review rejection→resubmit→accept. Expected: prior rejected evidence
  retained; only new candidate/current evidence accepted
- L10: accepted candidate changed. Expected: no completion with stale
  acceptance; explicit return to active and revalidation
- L11: abort→re-enter→abort. Expected: both generations visible; never erase
  abandoned history
- L12: illegal transition or failed validation. Expected: no fabricated
  same-state event or lost audit history
- L13: provider open/closed × all six states. Expected: provider status alone
  changes neither lifecycle nor dependency satisfaction
- L14: completed vs accepted vs aborted. Expected: dependency_satisfied true
  only for completed, independent of local claims
- L15: lost clone/worktree/session. Expected: committed history reconstructs;
  no recreated claim/session/current-work ownership
- L16: malformed/unsupported/truncated/conflicting history. Expected: reject
  without replacing it with default state
- L17: exact candidate mismatch on submit/accept/complete. Expected: reject
  without modifying state, history or revision
- L18: changed review/validation evidence after acceptance. Expected: stale
  evidence cannot authorize completion
- L19: stale relationship revision when consumed. Expected: reject or recompute
  against a validated new snapshot before publishing
- L20: candidate has no required manual test. Expected: no invented MIT
  requirement; all declared ART/AIT evidence still mandatory

Generic record revisions and provenance belong to the canonical envelope.
History events retain their historical schema representation; normalization
applies to interpretation, not retroactive mutation.

## 3. Concurrency, atomicity and recovery oracle

- C01: create from absent record. Expected: revision 0 and one canonical issue
  identity
- C02: update at expected revision N. Expected: complete next record at N+1;
  readback matches
- C03: stale N after another writer reaches N+1. Expected: conflict; no
  overwrite, no silent retry
- C04: two workers race the same lifecycle revision. Expected: at most one
  publishes; loser rereads/recomputes
- C05: independent issues written concurrently. Expected: no global issue lock;
  each CAS independent
- C06: crash before atomic record publish. Expected: complete old value
  remains; staged bytes not authority
- C07: crash after publish before acknowledgment. Expected: replay proves
  already-applied identity; no duplicate event
- C08: multi-record prepared transaction interrupted. Expected: prepared is not
  success; recovery revalidates read set
- C09: committed transaction partially materialized. Expected: recovery
  idempotently finishes complete committed successor
- C10: aborted transaction. Expected: no successor exposed; safe cleanup only
  of proven staging material
- C11: conflicting/changed transaction inputs. Expected: fail closed; preserve
  diagnostic and prior authoritative state
- C12: two independent clones publish conflicting revisions. Expected: shared
  integration rejects stale second candidate
- C13: writer/session missing or invalid. Expected: mutation rejected; no
  authoritative state change

An operation must not claim a completed transition on a partially published
multi-record result.  Do not infer global exclusivity from clone-local locks.

## 4. CSV projection and semantic merge oracle

- P01: legacy issue,title,dependencies CSV. Expected: parsed without invented
  cached lifecycle state; graph uses ?
- P02: initial refresh for zero/one/many rows. Expected: five-column canonical
  header; exact normalized rows/readback
- P03: proven absent lifecycle record. Expected: not_started with empty
  state_revision
- P04: existing lifecycle record. Expected: recognized state and exact sampled
  authoritative revision
- P05: unsupported/empty/malformed migrated state. Expected: reject rather than
  infer a state
- P06: mixed revisions across tickets. Expected: one validated snapshot;
  explicitly sampled per-ticket revisions
- P07: authoritative state changes after refresh. Expected: offline CSV remains
  an identifiable older snapshot
- P08: refresh encounters unreadable lifecycle. Expected: no partial CSV write,
  failure diagnostic
- P09: lifecycle changes while refresh reads/publishes. Expected: detected
  conflict/restart, never mislabelled current
- P10: concurrent CSV writers. Expected: exact read/compare/publish; stale
  writer rejected
- P11: failed CSV write or interrupted publication. Expected: previous valid
  CSV survives; readback before success
- P12: provider title/dependency sync. Expected: original authority rules
  retained; no lifecycle mutation
- P13: provider closed with RWF active. Expected: active retained; no inferred
  completed state
- P14: merge one-sided title/dependency change. Expected: existing semantic
  merge policy retained
- P15: divergent state/revision projections. Expected: authoritative
  reconciliation or conflict; no last-writer-wins
- P16: stale/unsupported schema on one merge side. Expected: fail closed; no
  silent downgrade to three columns
- P17: clone restart and clone-to-clone transfer. Expected: committed lifecycle
  record and cached revision reconstruct exactly
- P18: duplicate/unknown issue IDs, invalid dependencies. Expected: canonical
  graph validation fails before committing a projection

CSV columns are exactly
`issue,title,dependencies,state,state_revision` after explicit migration.
Rows and dependency lists retain canonical numeric order.  The empty revision
exception applies *only* to a proven never-started issue.  A projection is
not an authority for transitions, nor a guarantee of live freshness.

## 5. Graph and public-command oracle

- G01: ordinary lanes view/select. Expected: cached CSV only; no
  network/lifecycle read/write
- G02: legacy three-column rows. Expected: unknown glyph ?; never treat absence
  as completed
- G03: six statuses. Expected: ○ ● ◎ ✓ ♥ ✕, each matching its named state
- G04: ready and blocked, same state. Expected: readiness remains independently
  derived from direct dependencies
- G05: --current with no/one/many displayed nodes. Expected: authoritative
  states refreshed, saved, verified, then rendered
- G06: --current provider unavailable. Expected: no provider issue-state
  dependency or implicit remote fetch
- G07: --current authoritative error. Expected: old CSV unchanged; visible
  error, no partial graph success
- G08: --current plus title/dependency changes elsewhere. Expected: state
  refresh never rewrites titles, dependencies, or topology
- G09: --legend absent/present. Expected: absent by default; appended six-state
  legend only when requested
- G10: --legend with --json/--count. Expected: incompatible non-graph modes
  rejected
- G11: --legend with --current/debug/lane filter. Expected: coherent graph
  first, legend below, no semantic side effects
- G12: empty, mixed, long-title and all supported layouts. Expected:
  deterministic spacing, order, and one-cell glyph alignment
- G13: monochrome, Linux/Windows terminals. Expected: glyphs/unknown marker and
  accessible labels remain distinguishable
- G14: current-worktree pointer differs from graph states. Expected: graph
  renders per-ticket state; navigation pointer not authority
- G15: repeated --current with unchanged authority. Expected: deterministic
  serialized projection; no lifecycle mutation

## 6. Closure evidence ledger

For each applicable row, record:

`ID | exact source SHA | independent test command | persisted/provider
readback | PASS/FAIL/INCOMPLETE | evidence URL`

This specification has no execution result.  A contract review can check
that each expected result is complete and non-contradictory; only #580–#583
implementation and certification can supply actual execution evidence.
Cross-products worth explicitly retaining: source state × operation,
provider open/closed × lifecycle state, cache age × revision conflict,
schema version × event cardinality, and graph mode × output format.

#579 is specification-only.  No source-code implementation, production tag,
merge, or runtime certification is authorized by accepting this matrix.
