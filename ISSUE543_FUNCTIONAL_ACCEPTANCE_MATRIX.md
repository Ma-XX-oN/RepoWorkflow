# #543 — assembled functional acceptance matrix (V3)

## Revision identity and evidence separation

- Integration base: PR #567 at `dcdaea2db881b4075cbd87ab9d225d5fe8ae4bf2` (original lane A/B/C audit target).
- Current integrated implementation: PR #567 `issue-543-unified-hosted-certification-probe`, source and test fixes committed in this execution. The exact new HEAD must be taken from GitHub when hosted testing is invoked.
- Isolated local test worktree was recreated from the supplied exact-revision archive. Production-source blob hashes and registered tests were checked against GitHub after publication. Its synthetic local Git commit is **not** an upstream provider candidate SHA.
- Historical hosted C evidence uses source `51453681a69b8ecddc804f4c25202f95863376ec` (runs 37970407930 integration, 37971235736 regression); it **does not certify** the current PR head.
- Lane A: 144/145 existing PASS, #629 34 PASS/1 ERROR at original pinned source; RED, selection and marker defects reproduced, corrected and retested locally.
- Lane B: legitimate historical retry parent differs from original candidate; missing immutable artifact in original PR #567; corrections staged but provider unverified.
- Lane C: historical 1,099 regression/integration tests PASS, renderer PASS, Ubuntu/Windows/macOS probes 3/3 each PASS; current pinned head had Self CI 37972227171 action_required/no jobs.
- #85: SECURITY-DEFERRED; no main protection/production activation, merge or release authorised.

## Contract-by-contract status

| ID | Requirement | Final status | Evidence / outstanding work |
| --- | --- | --- | --- |
| M01 | /S/i/x/ /p/u/b/l/i/c/ /t/e/s/t/ /f/a/m/i/l/i/e/s/ /a/n/d/ /s/p/e/l/l/i/n/g/ | **PASS (local)** | Six-stage CLI smoke tested locally (#629/CLI); exact published code matched isolated source blobs. |
| M02 | /S/i/n/g/l/e/ /p/e/r/s/i/s/t/e/d/ /R/E/D/ /s/e/l/e/c/t/i/o/n/;/ /z/e/r/o/ /o/n/e/ /m/a/n/y/ /i/n/v/a/l/i/d/ | **PASS (local)** | Committed-selection modification and deletion tests now pass on corrected source (6 local tests). |
| M03 | /S/t/a/g/e/ /h/e/l/p/ /a/n/d/ /-/-/r/e/m/o/t/e/ /o/p/t/i/o/n/ /g/r/a/m/m/a/r/ | **PASS (local)** | Help/--remote grammar local #629 probes PASS; Windows/macOS current untested. |
| M04 | /S/u/p/e/r/s/e/d/e/d/ /v/a/l/i/d/a/t/e/ /c/o/m/m/a/n/d/s/ /a/b/s/e/n/t/ | **PASS (local)** | Legacy validate command rejected by local #629 public CLI test. |
| M05 | /D/e/d/i/c/a/t/e/d/ /m/a/r/k/e/r/ /s/t/a/g/e/ /a/n/d/ /p/r/e/-/i/n/v/o/c/a/t/i/o/n/ /t/i/p/ | **PASS (local)** | Real Git dedicated marker / original-parent contract local tests PASS. |
| M06 | /M/i/s/s/e/d/ /i/n/v/o/c/a/t/i/o/n/ /r/e/t/r/y/ /b/i/n/d/s/ /i/m/m/e/d/i/a/t/e/ /p/r/e/v/i/o/u/s/ /t/i/p/ | **PASS (local)** | Retry and tamper local #629 invocation tests PASS after committed HEAD fix. |
| M07 | /N/o/ /p/a/i/d/ /t/e/s/t/i/n/g/ /o/n/ /o/r/d/i/n/a/r/y/ /p/u/s/h/ | **INCOMPLETE** | Path-scoped trigger configured; absent current exact-candidate negative provider event ledger. |
| M08 | /R/e/m/o/t/e/ /r/e/s/u/l/t/s/ /r/e/a/d/i/n/g/ /t/r/i/g/g/e/r/s/ /n/o/ /n/e/w/ /r/u/n/ | **INCOMPLETE** | Historical hosted remote-results readback on run 37971235736 PASS; no current run. |
| M09 | /L/o/c/a/l/ /a/n/d/ /h/o/s/t/e/d/ /s/t/a/g/e/s/ /s/e/l/e/c/t/ /e/q/u/i/v/a/l/e/n/t/ /t/e/s/t/s/ | **INCOMPLETE** | Historical local/hosted parity only; new candidate not cross-certified. |
| M10 | /C/a/n/o/n/i/c/a/l/ /p/e/r/-/i/s/s/u/e/ /t/e/s/t/i/n/g/ /l/o/g/ /w/r/i/t/e/ | **PASS (local)** | Local canonical per-issue JSONL PASS; hosted artifact publication pending. |
| M11 | /L/o/c/a/l/ /r/e/s/u/l/t/s/ /r/e/a/d/s/ /c/a/n/o/n/i/c/a/l/ /l/o/g/ | **PASS (local)** | Local results readback PASS; malformed trailing record withheld. |
| M12 | /R/e/m/o/t/e/ /r/e/s/u/l/t/s/ /r/e/t/r/i/e/v/e/s/ /p/r/o/v/i/d/e/r/ /r/e/c/o/r/d/s/ | **INCOMPLETE** | Historical run 37971235736 readback PASS; current candidate not exercised. |
| M13 | /N/o/ /o/n/e/ /m/a/n/y/ /i/n/v/a/l/i/d/ /f/o/r/ /e/a/c/h/ /s/t/a/g/e/ | **INCOMPLETE** | Local stage cardinalities PASS; provider-wide zero/one/many matrix incomplete. |
| M14 | /M/a/l/f/o/r/m/e/d/ /o/r/ /s/t/a/l/e/ /R/E/D/ /s/e/l/e/c/t/i/o/n/ /r/e/j/e/c/t/e/d/ | **PASS (local)** | Dirty/deleted/malformed selections fail closed in local regression tests. |
| M15 | /M/i/s/s/i/n/g/ /s/e/l/e/c/t/i/o/n/ /w/a/r/n/s/ /a/n/d/ /r/e/c/o/r/d/s/ /S/K/I/P/P/E/D/ /n/o/t/ /P/A/S/S/ | **PASS (local)** | Missing never-configured selection writes SKIPPED with no hosted request, local PASS. |
| M16 | /T/e/m/p/o/r/a/r/y/ /c/a/t/a/l/o/g/u/e/ /p/a/t/h/ /a/n/d/ /c/l/e/a/n/u/p/ | **PASS (local)** | Temporary catalogue path, cardinality and sandbox preflight locally PASS. |
| M17 | /E/x/p/e/c/t/e/d/ /R/E/D/ /v/s/ /u/n/e/x/p/e/c/t/e/d/ /e/x/i/t/ /a/n/d/ /i/n/f/r/a/s/t/r/u/c/t/u/r/e/ /f/a/i/l/u/r/e/s/ | **PASS (local)** | Positive declared RED and mismatching-declaration negative cases now PASS locally. |
| M18 | /U/n/c/h/a/n/g/e/d/ /a/c/c/e/p/t/e/d/ /G/R/E/E/N/ /P/A/S/S/ /a/c/t/u/a/l/l/y/ /b/y/p/a/s/s/e/s/ /s/u/b/p/r/o/c/e/s/s/ | **INCOMPLETE** | Local cache reuse/invalidations PASS; current provider-attested retry unverified. |
| M19 | /C/h/a/n/g/e/d/ /i/n/p/u/t/s/ /i/n/v/a/l/i/d/a/t/e/ /a/p/p/l/i/c/a/b/l/e/ /c/a/c/h/e/d/ /e/v/i/d/e/n/c/e/ | **INCOMPLETE** | Local exact SHA/catalogue invalidation PASS; historical provider 38089922564 from #541 only. |
| M20 | /E/x/a/c/t/ /c/a/n/d/i/d/a/t/e/ /a/n/d/ /c/a/t/a/l/o/g/u/e/ /S/H/A/ /b/i/n/d/i/n/g/ | **INCOMPLETE** | Lineage verifier tested against six negative/positive mocked histories; real current-SHA provider absent. |
| M21 | /R/e/j/e/c/t/ /f/a/i/l/e/d/ /m/i/s/s/i/n/g/ /s/t/a/l/e/ /o/r/ /r/e/p/l/a/y/e/d/ /e/v/i/d/e/n/c/e/ | **INCOMPLETE** | Negative local source tests PASS; assembled live provider failure/replay permutations absent. |
| M22 | /R/e/j/e/c/t/ /f/o/r/g/e/d///m/a/l/f/o/r/m/e/d/ /e/x/t/e/r/n/a/l/ /e/v/i/d/e/n/c/e/ | **INCOMPLETE** | Provider-origin checks in unit tests PASS; forged real external artifact refusal pending. |
| M23 | /L/i/n/u/x/ /W/i/n/d/o/w/s/ /a/n/d/ /m/a/c/O/S/ /h/o/s/t/e/d/ /m/a/t/r/i/x/ | **INCOMPLETE** | Lane C historic source 51453681a69b8ecddc804f4c25202f95863376ec, 37970407930 nine probes PASS (3 per OS); current source untested. |
| M24 | /P/r/o/t/e/c/t/e/d/ /m/a/i/n/ /r/e/f/u/s/e/s/ /d/i/r/e/c/t/ /p/u/s/h/ /b/y/p/a/s/s/ /f/o/r/c/e/ /d/e/l/e/t/e/ | **SECURITY-DEFERRED** | #85 protected-main enforcement, bypass and ruleset tests explicitly deferred; not functional gate. |
| M25 | /S/t/a/l/e/ /d/e/s/t/i/n/a/t/i/o/n/ /r/a/c/e/ /r/e/j/e/c/t/s/ /l/a/t/e/r/ /c/a/n/d/i/d/a/t/e/ /a/t/o/m/i/c/a/l/l/y/ | **INCOMPLETE** | Provider stale-destination dual-actor mutation has no current live demonstration. |
| M26 | /R/e/c/o/n/c/i/l/e/ /r/e/q/u/i/r/e/d/ /c/h/e/c/k/s/ /a/n/d/ /d/o/c/u/m/e/n/t/a/t/i/o/n/ | **INCOMPLETE** | Workflow/docs consistency incomplete for newly assembled source and required checks. |
| M27 | /P/r/o/v/i/d/e/r/ /i/m/m/u/t/a/b/l/e/ /a/r/t/i/f/a/c/t/ /l/o/o/k/u/p/ | **INCOMPLETE** | New actions/upload-artifact@v4 publisher committed; artifact not yet independently observed for current run. |
| M28 | /I/n/c/o/m/p/l/e/t/e/ /f/a/i/l/e/d/ /a/n/d/ /u/n/a/v/a/i/l/a/b/l/e/ /p/r/o/v/i/d/e/r/ /o/u/t/c/o/m/e/s/ | **INCOMPLETE** | Malformed/unavailable provider fake tests fail closed; actual provider-unavailable run missing. |
| M29 | /S/o/u/r/c/e/-/m/i/x/e/d/ /r/e/q/u/e/s/t/ /a/n/d/ /u/n/c/o/m/m/i/t/t/e/d/ /m/a/r/k/e/r/ /t/a/m/p/e/r/ | **PASS (local)** | Source-mixed request, worktree marker tamper and retry checks local PASS. |

## Hosted integration gate (not yet green)

Run the new exact assembled SHA through RED, temporary, GREEN, regression, integration and results --remote; confirm immutable provider artifacts, normal-push non-dispatch, authenticated retry reuse and cross-platform parity. Never count prior candidate's provider success as current-head PASS. Keep #543 OPEN until all functional requirements pass. #85 remains separately SECURITY-DEFERRED.
