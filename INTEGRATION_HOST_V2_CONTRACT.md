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

## October 19 — provider read/write implementation checkpoint

The original October 18 "not implemented" statements above are historical
checkpoints, not the current executable inventory.  The unmerged development
adapter now exposes `lease.read` / `lease.cas`, full immutable
`attempt.read` / guarded `attempt.record`, and separate per-ref immutable
`retirement.read` / guarded `retirement.record` evidence.  The latter
requires an independent deletion verifier and does **not** itself delete a
ref or authorize an integration.  Terminal records include provider
operation ID, umbrella, expected and observed destination SHAs, exact
PRELIM/INT SHA identities, landed SHA only on an integrated result, and
immutable evidence ID.  Deferred MIT remains a resumable-event problem
owned by #109; it is not safe to finalize as a terminal tag.

New `destination.read` is strictly read-only and returns the authenticated
repository's exact current destination ref/SHA and the unparsed policy bytes
obtained using that exact SHA as the GitHub Contents API `ref`.  Returned
`policy_present=false, policy_text=null` means absent; present with
`policy_text=""` means explicitly empty.  Consumers #108/#109, not the
provider, parse immediate-child allow-list semantics.  The adapter rereads
the destination SHA and refuses a mixed snapshot when it changes mid-read.
A provider read must respond `unchanged`, never `applied`.

Git-protocol mutations are bound to the provider's authenticated full repo
identity and to matching effective fetch/push URLs.  INT-ATTEMPT and lease
CAS have independent stale-writer, forged-repo and lost-response tests; the
retirement audit tests reject conflicting event IDs and missing verified
terminal provenance.

**Not certified:** live disposable GitHub CAS/tag/retirement acceptance;
deployment of independent evidence and deletion verifiers; coordinator
crash/restart with deferred MIT; final destination-tip acceptance under
#104/#542; complete producer/executor/retirement path under #683/#109/#103;
and #677's independent assembled certification.  Existing v1 contract,
protected branches, release tags and hard security gates remain unchanged.


## October 20 — real disposable provider and independent-verifier continuation

Entries above are historical, not exact-current-source PASS. Existing open
draft PR #682 and v1 contract are unchanged; production destination and
stable release refs were not updated.

Implemented in #681 source:

- RWF_REPO_HOST_INTEGRATION_EVIDENCE_COMMAND specifies one external,
  absolute-path verifier executable, outside the unreviewed checkout.
  Before terminal, MIT deferred/resume and retirement audit publication,
  the v2 executable authenticates actor and validates fresh, strict,
  request/record-digest-bound, repository/operation/request/actor-scoped
  independent evidence. Missing, revoked, stale or forged evidence refuses.
  This is a verifier consumer, not a production approval issuer.
- Interrupted INT-ATTEMPT creation can now resume once its identical
  request reservation is persisted but the worker crashed before ref creation.
  Changed-source replay with the same reservation is refused.
- Lost-ACK INT-ATTEMPT push reconciles only when provider readback exactly
  matches new target SHA; competing/stale outcomes remain refused.
- Resumable MIT deferral remains separate from immutable terminal disposition.
  Same-generation revocation overrides approved, while separately authorized
  later generations can resume; no second READY queue is created.

Real disposable GitHub provider acceptances:

- 39298257126: real INT ref create/CAS, stale writer rejection, destination
  generation lease PASS.
- 39298816723: real terminal persistence, PRELIM and INT-ATTEMPT conditional
  retirement and independently read back audits PASS.
- 39453443687: real provider MIT persistence, lost ACK, revocation, fresh
  backend replay and cleanup PASS.
- 39454041162: v2 ref create using independent sandbox #80 authorization,
  absent/revoked/forged/stale/foreign actor denials, replay and cleanup PASS.
- 39454729185: full v2 executable MIT defer/resume/revoke with separately
  executable independent authorization and evidence verification, fresh
  restart and negative forged-evidence acceptance PASS.
- 39455594549: real persisted reservation, separate-provider restart after
  crash, exact replay, changed-source denial and cleanup PASS.

Every sandbox run confirmed private Disposable-000 main unchanged. All
disposable test-verifier executables are isolated authority fixtures, not
deployment of an independent production grant/revocation service.

Uncertified remains: actual production trust deployment; provider destination
integration with exact pre-write expected-old SHA and current eligibility/
policy rechecks (#104/#542); assembled #109 tested producer/executor path;
#103 retirement using true #109 landed integration; and #677 independent
end-to-end certification. Prior green CI is not the final source candidate.
#683 is an independent producer and must not block #681 provider testing.
#85/#86/#676 adversarial protected-production enforcement is deferred.


## October 20 — authenticated destination acceptance provider (#681)

This section freezes the *additive* provider v2 acceptance contract. No
change to the existing v1 six-operation transport, PRELIM READY admission,
producer ownership or #109 planner/executor API is implied.

The new provider request `destination.accept` takes exactly one `record`
containing:

- `repository`, `destination`, `int_attempt_ref`, `accepted_sha`;
- `expected_destination_sha`, `proposed_sha`, `guid`;
- `lease_generation`, `holder`, `authorization_ref`, `evidence_ref`;
- `operation_id` (must match the transport `request_id`).

The successful provider result is `destination`, `expected_sha`,
`landed_sha` and `operation_id`, with `landed_sha=proposed_sha`.
This is a functional provider primitive, not permission to merge. It requires
a separately authenticated #80 permission verdict and an out-of-checkout
independent evidence-verifier verdict bound to exact request, record, actor
and repository. Its verifier issuer is a deployment responsibility external
to this source; no untrusted client-provided PASS is accepted.

The provider independently checks authenticated Git remotes, the current
destination SHA/policy snapshot, current exclusive destination lease
generation/GUID/holder, immutable INT-ATTEMPT ref/accepted SHA, local proposed
commit existence and destination ancestry. Before the Git-protocol
expected-old-SHA remote update it persists an immutable operation-intent
tag, bound to canonical request digest, provider actor, GUID, accepted source,
expected old SHA, proposed landed SHA and exact operation identity.

A lost ACK is reconciled only when a fresh provider read proves the exact
landed SHA, unchanged authoritative lease, and matching persisted operation
intent under renewed independent authorization. A fresh process does not
need a local candidate to read that proof. Other tips, stale permissions,
foreign actors and conflicting intents remain UNKNOWN or refused. The
independent verifier is checked again immediately before mutation to
reject revocation during preparation. This intent is audit evidence,
not a READY queue or proof by itself of an integration landing.

Provider evidence:
- Disposable-000 real destination acceptance and stale second contender
  [run 39459815265](https://github.com/Ma-XX-oN/Disposable-000/actions/runs/39459815265)
  PASS using source `b4316a2a3c84b65311e8bd00f2cb492f39e35223`.
- External verifier/no-grant rejection, permitted first CAS, stale retry
  refusal, destination lease binding, verified source and real cleanup PASS.
  The production default branch was untouched; isolated disposable destination
  was deleted. Earlier sandbox remote-binding test failure 39459642054
  was corrected before the successful run, not reclassified as PASS.
- Issue-681 destination provider-neutral and negative acceptance cases are
  registered under `issue-681-destination-accept` and hosted with the
  repository regression catalogue.

Not asserted here: production deployment of independently protected
authorization/evidence issuance; #109's actual ART/AIT/MIT certification
and source-to-landed promotion; #103's retirement of a real #109 attempt;
#677 assembled downstream conformance; or activation of hard security
#85/#86/#676. #683 is independently owned and not a prerequisite of
#681 provider-primitive acceptance.


## October 20 — operation-intent recovery and real provider acceptance

Commit `5e1f52ac19cc8028ec9151ba7a6888db89f6b398` adds the
immutable per-request intent tag and independent authorization recheck.
The tag is scoped by SHA-256 of repository plus a NUL separator plus the
operation ID; it is not an integration queue or a terminal PASS.

Independent Disposable-000 provider runs:

- 39465051536: real successful destination update with lost Git ACK,
  exact intent readback, fresh-process recovery and conflicting-operation
  rejection; isolated refs cleaned and default main unchanged.
- 39465418619: persisted intent, interrupted pre-push worker, fresh
  provider restart, lost ACK, exact readback and cleanup.
- 39465820919: revocation between intent publication and the mutation
  was refused before changing destination; authorized retry, lost ACK,
  restart and cleanup passed.
- 39466294625: one real disposable sequence chaining destination CAS,
  terminal ledger and per-ref retirement. Its terminal provider result
  must be checked before marking this assembled fixture PASS.

The external verifiers in Disposable-000 are independent test fixtures,
not deployment of a production protected #80 issuer. Hard security
#85/#86/#676 is deferred, never claimed PASS. The #109 scheduler and
#103 final cleanup, #677 downstream assembly and independently owned #683
retain their own contracts.
