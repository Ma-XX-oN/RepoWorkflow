# RWF #677 — October 20 assembled convergence checkpoint

State: INCOMPLETE.  Integration PR #685 remains draft and unmerged.
No security enforcement, protected publication or leaf-branch edit is
authorized by this checkpoint.

## Exact owner sources copied as blobs into assembly

- #681 PR #682: `4938f73312691e7e593cd758965eb538f9e40baf`
- #683 PR #684: `9a0381261d77310ec3b8edbea65f4cef49d55de5`
- #103 PR #679: `d6acd97219ac45a90634d0a8c0b90780e9b7e5ff`
- #109 PR #680: `164750caf97dcd0185c76346d5bcad216dec1439`
- #677 existing assembly baseline: `fa1dae1a85f141432f22aefcc758fe986874b594`

The provider v2 operation grammar now includes immutable terminal
records, independently readable MIT deferral/resume events, destination
acceptance and auditable retirement.  The executor's new provider
pipeline, integration workspace, identity/evidence/retirement helpers
and tests were brought into this **assembly branch only**.  The producer
and retirement owner sources were also reconciled as exact file blobs.

The full tests catalogue retains the pre-existing #677 graph test
registration and adds 22 distinct owner-specific test entries.  The
assembled push probe runs focused interface suites and full unittest
discovery.  A source-accurate CI PASS and genuine live-provider
assembled acceptance must be established independently.

## Direct completion graph (authoritative ticket CSV)

- #103 <- #84, #681
- #109 <- #83, #103, #108, #118, #681, #683
- #583 <- #109, #582
- #677 <- #83, #84, #102, #108, #109, #583

The unchanged CSV material blob is
`0d2cc6494d38d059f8bd513db0674f18e16c36ba`.
Deferred #85/#86/#676 security is not asserted complete.

## Acceptance ledger

| Scope | Classification |
| --- | --- |
| Direct CSV dependency parity | PASS — exact known owner contracts |
| 272-ticket cycle and missing-ID test | REGISTERED; rerun on new source |
| Provider/executor/producer source interop | ASSEMBLED; CI not yet GREEN |
| Invalid terminal and MIT deferral/restart negatives | TESTS PRESENT; live system pending |
| Exact-source three-platform regression/integration | PENDING |
| #109 executor final mutation/provider acceptance | NOT COMPLETE |
| #583 independent 14 remaining executor cases | NOT COMPLETE |
| Full real-provider PRELIM -> INT-ATTEMPT -> retire | NOT CERTIFIED |
| Final #677 DONE gate | BLOCKED by #109, #583 and provider acceptance |

Do not promote mocked tests, historical exact-SHA jobs or an isolated
owner's hosted PASS to this assembled revision.  No merge, protected ref
mutation or stable tag is part of this work.

## First assembled hosted run — non-GREEN

At source `aa6901eaa280afb351fc64ad5bddee4370de61e2`,
run 39506429246 FAILED in both focused and full-regression jobs.
The provider log identifies `PipelineTests.run()` shadowing the
`unittest.TestCase.run()` framework entry point.  #109 PR #680 fixed
the fixture in its separate owned branch.  The source blob is imported
on #677 assembly; this is not owner transfer.  New hosted testing is
required.  Neither prior job is a PASS.

## Previous exact-source acceptance — terminal GREEN

Source `4491be28b0abb74e6bcd51197495addb6f000462` is genuinely
hosted certified for its own scope.  #677 assembly probe
`39506896851` completed SUCCESS in both focused and full regression
jobs; 2416 unittest cases ran, 14 historical skips, zero final suite
failures.  The exact-source integration request `a72bc1d6656b76e23f034d9f44fba2e2324105a4`
ran `39507229178` SUCCESS: 2416 tests, 14 skips, all nine
Ubuntu/Windows/macOS probes PASS, validator PASS, publish PASS and
read-only results PASS.  Stage artifact 12304482579 and provider artifact
12304957169 were published.  No actual end-to-end authenticated provider
integration/retirement was thereby certified.

## New owner source reconciliation

#109 PR #680 advanced to exact `5273b33564b3546b3cc68834f1359c57913247df`.  Its
provider-pipeline pre-lease identity verification and fail-closed
cross-submission negatives replace the older #109 pipeline snapshot here.
The source is imported as exact blobs and focused tests are expanded.
The latest source requires its own exact-SHA hosted results; do not treat
previous integration PASS as certification of this changed code.
