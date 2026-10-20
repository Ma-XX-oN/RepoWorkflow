# October 17 PRELIM READY Producer Migration — #683

Status: **PARTIAL — NOT DONE**. This document is a durable handoff and
does not replace source or provider acceptance.

## Implemented on draft PR #684

- `prelim_ready.py`: provider-atomic create-only READY ref and strict
  remote readback. Duplicate ref, including matching SHA, is rejected unless
  an independently persisted matching request-ID event proves replay.
- `prelim_ready_bridge.py`: conservatively convert a prior verified #82
  READY attempt's exact SHA, not a regenerated candidate.
- `prelim_ready_recorded.py`: load/restore #82 durable attempt record,
  confirm owner, remote legacy candidate and source identity, then call
  provider-atomic publication. `publish_recorded_ready_certified` additionally
  requires published #102 PASS evidence.
- `prelim_ready_authority.py`: verify #102 published PASS record, exact
  source/base/candidate SHA, immediate parent and regression/integration
  terminal tags pointing to the candidate.
- `prelim_integration.py:submit_ready_prelim`: explicit branch-as-READY
  submission path. Unlike old `request_prelim_integration`, it does not
  create an integration PR, queue marker or secondary submission branch.

## Evidence

- Independent draft PR #690 test workflow 39075451160: 43/43 PASS
  before latest test registration. It covered provider create-only, legacy
  record conversion, #102 terminal authority and new submission API.
- Disposable authorized private repo `Ma-XX-oN/Disposable-000`:
  `PRELIM-issue-123/main-44444444-4444-4444-8444-444444444444`
  created at `b411d215bec5c62c8a3ca3062ec8f8743f2d7299`.
  Creating same branch at same SHA a second time failed HTTP 422
  `Reference already exists`; compare readback status identical.
  This is real-provider **create-only collision PASS**, not complete
  credentials/CAS/certification. Temporary branch remains for authorized
  safe cleanup.
- Assembled PR #685 contains the #683 code and new focused groups; hosted
  run #39075634246: 160 focused tests PASS at exact source
  `6064fd8de3b4e541e952cf9a5c3b7b20fd41fd6e`,
  full regression pending terminal result at this checkpoint.

## Known remaining functional work

1. Replace legacy #82's hard-coded `prelim-main-<GUID>`/main base and
   obsolete remote `prelim-state/<GUID>` publication in production
   producer path. Current adapter converts verified historical attempts;
   it is **not yet the new standalone first-use producer**.
2. Implement destination-qualified preparation against the ticket's
   current parent rather than assuming `main`.
3. Guarantee restart/recovery without changing the exact published
   candidate SHA; maintain current #102 candidate-specific evidence.
4. Wire actual CLI/public workflow command through new submission API
   without bypassing issue-ownership or provider authorization.
5. Obtain full issue-scoped and hosted independent acceptance on first-time
   offline publication, different umbrellas/same destination, source drift,
   parent drift, lost provider responses, and live provider readback.
6. #681 must independently supply provider-authoritative coordinator
   destination CAS, durable attempt outcomes and INT-ATTEMPT orchestration;
   #109 executor and #677 assembled certification are downstream.

No merge, production tag or deferred #85/#86/#676 security activation.
