# Issue #97 — Contract-Based Functional Acceptance Matrix

Date: 2026-10-10.  Owner: V3 claim 6099480122, draft PR #616.
Issue status: OPEN.  No merge authorized or performed.

## Requirements and ownership

Direct prerequisite: #81 (closed).  #97 implements the semantic
`repo-host` GitHub issue/PR mutation adapter.  #80 defines the
authorization evidence format; it does NOT require #97 to deploy a
production issuer.  #85 owns protected-main GitHub enforcement and
remains outside #97's completion prerequisites.

The user explicitly authorized private disposable repository
`Ma-XX-oN/Disposable-000` for issue #97 functional acceptance.
Its owner-authorized, expiring, operation/actor/ref-scoped test
authority resides on sandbox main OUTSIDE the adapter candidate,
and is checked by the shipped adapter authorization consumer.

## Independent acceptance matrix

| #81 criterion | Verified evidence | Status |
| --- | --- | --- |
| Strict JSON request/result envelope | Hosted CLI tests | PASS |
| Invalid inputs/extra keys/types | Hosted black-box tests | PASS |
| Authenticated GitHub principal | Native GH GraphQL viewer | PASS |
| Missing/invalid authority refusal | Live sandbox run 38093785174 | PASS |
| Real issue update | Live sandbox run 38095457391 | PASS |
| Issue same-ID replay | Same run before create failure | PASS |
| Remote issue readback and restoration | Sandbox issue #1 | PASS |
| Real issue comment | Two marked bot comments on #1 | PASS |
| Comment same-ID repeat | Same run before create failure | PASS |
| Changed same-ID comment refusal | Same run before create failure | PASS |
| Two independent Python comment processes | Same run, one race marker | PASS |
| Real PR creation by shipped adapter | Live run 38095457391 | BLOCKED |
| Exact source ref/SHA and draft creation | Mocks and connector | PENDING LIVE |
| Real PR update by shipped adapter | Live run 38095621430 | PASS |
| PR update replay after process restart | Run 38095621430 | PASS |
| PR changed same-ID conflict | Run 38095621430 | PASS |
| PR stale-head denial | Run 38095621430 | PASS |
| Provider readback of PR and no merge | Run 38095621430, PR #2 closed | PASS |
| Atomic request reservation | Six live tag refs and digests | PASS |
| Unknown outcome/collision reconciliation | Hosted spec tests | PASS |
| Unauthorized merge and check publish | Live run 38093785174 | PASS |
| Fail-closed cleanup | Hosted tests and live restoration | PASS |
| Cross-platform hosted regression | Exact source run listed below | PENDING |
| Server-side protected main | Owned by #85 | OUT OF SCOPE |

## Actual GitHub provider blocker

The private sandbox has admin access and runs ordinary GitHub-hosted
`ubuntu-latest` jobs.  Issue and PR-update API writes succeeded.
However actual `POST /pulls` from the sandbox-native GitHub Actions
token returned HTTP 403, with EXACT provider message:

> GitHub Actions is not permitted to create or approve pull requests.

This is independently reproduced by diagnostic run 38095551998,
not inferred from the adapter's generic `unauthorized` error.

**Smallest required administrative action:** In the *disposable*
repository only, open:

https://github.com/Ma-XX-oN/Disposable-000/settings/actions

Select `Workflow permissions` ->
`Allow GitHub Actions to create and approve pull requests` -> Save.

No offline signing ceremony, delegated role system, protected
environment, rulesets, dedicated runner, PAT, App or paid plan is
necessary to perform this owner-authorized disposable functional test.
The connected GitHub tools have no action to change the setting.

## Evidence pointers

- Ordinary mutation live run:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095457391
- PR update/restart/replay PASS:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095621430
- Real unauthorized/unsupported negative PASS:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38093785174
- Independent PR permission diagnosis:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095551998
- Source acceptance workflow:
  `.github/workflows/issue-97-platform-acceptance.yml`
- Actual sandbox end-to-end job:
  `Disposable-000/.github/workflows/rwf97-functional-acceptance.yml`

The original issue #97 and PR #616 remain OPEN/DRAFT, UNMERGED.
Once that single real-provider setting is enabled, rerun the exact
shipped adapter end-to-end and independently read all persisted PR,
comment and reservation records; if all owned requirements pass,
publish DONE, close #97 and advance through existing V3 successors.
