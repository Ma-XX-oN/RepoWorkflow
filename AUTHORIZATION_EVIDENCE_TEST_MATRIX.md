# Authorization Evidence Acceptance Matrix

Contract: `AUTHORIZATION_EVIDENCE_CONTRACT.md` (#80).  Each scenario is
an independently specified black-box expectation, not a claim that the
runtime implementation already passes.  Consumers must link test names,
exact candidate SHA, provider authority and results to each row.
A01 — Valid verified developer issue.update in exact issue scope
  Expected: allow

A02 — Developer requests pull_request.merge without its capability
  Expected: deny

A03 — CI runner has green tests but requests remote finalizer merge
  Expected: deny

A04 — Security administrator lacks separately granted merge role
  Expected: deny

A05 — Verified finalizer with exact merge grant and fresh provider principal
  Expected: allow

A06 — Finalizer local claim lacks provider-authenticated principal
  Expected: deny

A07 — Writer/session ID supplied without actor authentication
  Expected: deny

A08 — Git author identity matches claimed privileged role
  Expected: deny

A09 — One-time grant permits first exact protected operation
  Expected: allow

A10 — Replay same completed request ID and identical semantic request
  Expected: unchanged

A11 — Replay request ID with different candidate or operation
  Expected: conflict

A12 — New request with exhausted one-use grant
  Expected: deny

A13 — Standing policy max_uses null independently proven
  Expected: allow

A14 — Null scope with no verified wildcard policy
  Expected: deny

A15 — Scope changed to another issue
  Expected: deny

A16 — Scope changed to another integration
  Expected: deny

A17 — Candidate SHA changes after grant
  Expected: deny

A18 — Destination SHA changes after grant
  Expected: deny

A19 — Repository identity changes after grant
  Expected: deny

A20 — Major release attempted with only patch authorization
  Expected: deny

A21 — Major release with explicit verified major-class grant
  Expected: allow

A22 — Current trusted time before not_before
  Expected: deny

A23 — Current trusted time equals not_before
  Expected: allow

A24 — Current trusted time just before expires_at
  Expected: allow

A25 — Current trusted time equals expires_at
  Expected: deny

A26 — Revoked grant read from stale cache
  Expected: deny

A27 — Revocation and consumption race one revision
  Expected: one canonical winner

A28 — Two writers consume same one-use grant
  Expected: one successful consumption

A29 — CAS attempts replacement of stale revision
  Expected: conflict

A30 — Independent grant keys mutated by independent writers
  Expected: independent success

A31 — Prepared multi-record transaction after crash
  Expected: not authorized

A32 — Committed transaction replay after restart
  Expected: no double consumption

A33 — Unknown provider outcome before completion evidence
  Expected: reconcile or deny

A34 — Changed issuer policy revision after evaluation
  Expected: re-evaluate

A35 — Expired actor authentication though grant is active
  Expected: deny

A36 — Unverifiable issuer delegation
  Expected: deny

A37 — Delegation weaker than requested capability/scope
  Expected: deny

A38 — Missing authoritative revocation service
  Expected: deny

A39 — Malformed JSON or unknown schema version
  Expected: deny

A40 — Unexpected record field / invalid boolean-as-number
  Expected: deny

A41 — Incorrect candidate SHA shape
  Expected: deny

A42 — Duplicate or unsorted capability set
  Expected: deny

A43 — Unauthorized non-atomic provider merge despite grant
  Expected: deny

A44 — Authenticated evidence missing for check.publish
  Expected: deny

A45 — Reconstruct clone solely from local session/claim
  Expected: deny

A46 — Durable history and trusted proof uniquely determine prior fact
  Expected: historical only

A47 — Repeated recovery on same committed consumption
  Expected: no revision increase

A48 — Zero grants available for requested action
  Expected: deny

A49 — Multiple grants with conflicting issuer revocation facts
  Expected: deny

A50 — Immutable audit records include decision bindings, no secrets
  Expected: required

## Structural and provider verification

Beyond the black-box rows, verify strict schema validation, exact CAS
read/write-set checks, non-secret audit output, durable transaction atomicity,
and adapter-side use of independent authority.  Exercise real provider
permissions and protected-main refusal separately from mock testing.

A GREEN documentation/classification job is not evidence of operational
authorization enforcement.  Do not report implementation DONE from this
matrix alone.
