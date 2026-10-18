# Integration host V2 — #681

Status: DRAFT, PARTIAL. Existing repo-host v1 six-operation protocol remains unchanged.

## Operations

- `refs.list`: discover exact READY PRELIM refs; require complete provider pagination.
- `ref.create`: idempotently create an INT-ATTEMPT ref, not a PRELIM ref.
- `ref.cas`: update only an INT-ATTEMPT ref with expected-old SHA.
- `lease.read` / `lease.cas`: authoritative one-active-coordinator-per-destination lease, never a clone-local lock.
- `attempt.read` / `attempt.record`: durable readback and terminal/deferred result publication.

V2 requests carry schema version, repository, operation, request ID and parameters. Strict typed results echo the same identity. UNKNOWN mutations require provider readback before any retry. Published PRELIM branches are immutable READY submissions; no separate queue branch/file.

## Verified versus outstanding

Provider-neutral protocol negative tests and mocked GitHub ref inventory/create tests passed locally. GitHub `refs.list` pagination beyond the first page, live INT-ATTEMPT creation, remote `ref.cas`, lease CAS, terminal persistence, expired-grant refusal, and hosted certification are NOT verified. The provider implementation MUST refuse unsupported operations.

Disposable repository experiment: isolated `rwf681-cas-20261017-1849` began at `b411d215bec5c62c8a3ca3062ec8f8743f2d7299` and advanced to `890d585f0ec4e74c5657bcbd25928309d76d72ab`. A mismatched expected-SHA update yielded a GitHub GraphQL error rather than a clear stale-ref rejection; readback showed the new commit persisted. Result: INCOMPLETE, not PASS. Keep disposable branch isolated until supported deletion/cleanup.

Final provider acceptance must prove destination-tip CAS at merge time, permission checks, exact candidate/test/version binding, competing writers, readback after unknown responses, deferred MIT distinct from FAIL, recovery, and safe cleanup. #85/#86/#676 hard security remains deferred. No production merge or protected tag authorization.

## October 18 — exact terminal record interoperation (#103)

The v2 protocol rejects the older three-field `{guid,status,sha}` terminal
result. `attempt.record` now takes a GUID and a full `record` including
repository identity, PRELIM ref/SHA, INT-ATTEMPT ref/accepted SHA, exact
destination ref and expected prior tip, landed SHA for integrated outcomes,
integration ID and durable terminal evidence ref. `attempt.read` returns
`{guid,record}`, where `record: null` means no persisted terminal result.
The protocol validates full field presence, SHA types, integrated-only landed
SHA, echoed identity, and repository scope. The authenticated adapter must
still implement **actual** immutable remote persistence, independent readback,
idempotency and UNKNOWN reconciliation. Until then these operations remain
unsupported by the provider executable and #681 is NOT DONE.

Provider remote attempt refs accept generic `<umbrella>` names, not only
`issue-<number>`; this matches #103's retirement scope. Require the same
umbrella, destination and GUID on both exact attempt refs at provider terminal
publication. Production cleanup additionally needs an independently persisted
ref-retirement operation/audit with expected-old SHA and fresh landing proof.
No mocked protocol reply is evidence of authenticated provider mutation.

## October 18 — provider terminal primitive (partial)

The provider v2 executable now exposes `attempt.read` and a guarded
`attempt.record` path.  The latter fails closed until an independently
trusted terminal-evidence verifier is supplied by deployment.  A separate
provider primitive creates an append-only, GUID-qualified terminal tag
whose commit records all exact identities; readback rejects changed records,
foreign repositories, missing facts and ambiguous mutation responses.

For integrated outcomes, the provider additionally checks that the exact
accepted INT-ATTEMPT SHA precedes the landed SHA, and that the landed SHA is
reachable from the current authoritative destination.  This does not grant
merge authority and does not substitute for #104/#542 acceptance-time CAS.

The `retirement_terminal_reader` callback projects the full provider
record to #103's exact nine-field retirement evidence comparison without
weakening #103's historical independent readback checks.  The source and
negative regression tests are on draft PR #682; exact-current-head hosted
CI and authenticated disposable-provider acceptance remain outstanding.

**Deferred MIT warning:** This append-only terminal record is not a complete
resumable deferred-MIT history.  #109 currently releases an attempt with
`deferred-mit` then rejects a subsequent claim for that same GUID.  That
would strand it across restarts.  Reconcile terminal versus deferred event
semantics and add restart/resume tests before enabling durable deferred
records; see #109 comment 6252852692 and #681 comment 6252857974.

Not implemented or certified: actual hosted terminal provider publication,
configuring the trusted evidence verifier, destination lease CAS,
authenticated ref retirement operations/audit, final destination merge CAS,
and #109/#103 end-to-end integration.  #85/#86/#676 remain deferred.
