# Authorization Evidence Acceptance Matrix

Contract: `AUTHORIZATION_EVIDENCE_CONTRACT.md` (#80).  Each scenario is
an independently specified black-box expectation, not a claim that the
runtime implementation already passes.  Consumers must link test names,
exact candidate SHA, provider authority and results to each row.

| ID | Stimulus / condition | Expected |
| --- | --- | --- |
| A01 | Valid verified developer issue.update in exact issue scope | allow |
| A02 | Developer requests pull_request.merge without its capability | deny |
| A03 | CI runner has green tests but requests remote finalizer merge | deny |
| A04 | Security administrator lacks separately granted merge role | deny |
| A05 | Verified finalizer with exact merge grant and fresh provider principal | allow |
| A06 | Finalizer local claim lacks provider-authenticated principal | deny |
| A07 | Writer/session ID supplied without actor authentication | deny |
| A08 | Git author identity matches claimed privileged role | deny |
| A09 | One-time grant permits first exact protected operation | allow |
| A10 | Replay same completed request ID and identical semantic request | unchanged |
| A11 | Replay request ID with different candidate or operation | conflict |
| A12 | New request with exhausted one-use grant | deny |
| A13 | Standing policy max_uses null independently proven | allow |
| A14 | Null scope with no verified wildcard policy | deny |
| A15 | Scope changed to another issue | deny |
| A16 | Scope changed to another integration | deny |
| A17 | Candidate SHA changes after grant | deny |
| A18 | Destination SHA changes after grant | deny |
| A19 | Repository identity changes after grant | deny |
| A20 | Major release attempted with only patch authorization | deny |
| A21 | Major release with explicit verified major-class grant | allow |
| A22 | Current trusted time before not_before | deny |
| A23 | Current trusted time equals not_before | allow |
| A24 | Current trusted time just before expires_at | allow |
| A25 | Current trusted time equals expires_at | deny |
| A26 | Revoked grant read from stale cache | deny |
| A27 | Revocation and consumption race one revision | one canonical winner |
| A28 | Two writers consume same one-use grant | one successful consumption |
| A29 | CAS attempts replacement of stale revision | conflict |
| A30 | Independent grant keys mutated by independent writers | independent success |
| A31 | Prepared multi-record transaction after crash | not authorized |
| A32 | Committed transaction replay after restart | no double consumption |
| A33 | Unknown provider outcome before completion evidence | reconcile or deny |
| A34 | Changed issuer policy revision after evaluation | re-evaluate |
| A35 | Expired actor authentication though grant is active | deny |
| A36 | Unverifiable issuer delegation | deny |
| A37 | Delegation weaker than requested capability/scope | deny |
| A38 | Missing authoritative revocation service | deny |
| A39 | Malformed JSON or unknown schema version | deny |
| A40 | Unexpected record field / invalid boolean-as-number | deny |
| A41 | Incorrect candidate SHA shape | deny |
| A42 | Duplicate or unsorted capability set | deny |
| A43 | Unauthorized non-atomic provider merge despite grant | deny |
| A44 | Authenticated evidence missing for check.publish | deny |
| A45 | Reconstruct clone solely from local session/claim | deny |
| A46 | Durable history and trusted proof uniquely determine prior fact | historical only |
| A47 | Repeated recovery on same committed consumption | no revision increase |
| A48 | Zero grants available for requested action | deny |
| A49 | Multiple grants with conflicting issuer revocation facts | deny |
| A50 | Immutable audit records include decision bindings, no secrets | required |

## Structural and provider verification

Beyond the black-box rows, verify strict schema validation, exact CAS
read/write-set checks, non-secret audit output, durable transaction atomicity,
and adapter-side use of independent authority.  Exercise real provider
permissions and protected-main refusal separately from mock testing.

A GREEN documentation/classification job is not evidence of operational
authorization enforcement.  Do not report implementation DONE from this
matrix alone.
