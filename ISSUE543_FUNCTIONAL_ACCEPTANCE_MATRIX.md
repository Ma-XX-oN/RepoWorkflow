# Issue #543 — functional acceptance ledger (V3)

## Authoritative latest certified source — integration disposition (2026-10-11)

**Certified functional source (exact immutable material inputs):**
`2c8b0f9d5e63f2d0ceb5d602e7778796fb0dde28`.
**Certification verdict for that source: 28 FUNCTIONAL PASS, 0 FAIL,
0 FUNCTIONAL INCOMPLETE, 1 SECURITY-DEFERRED (#85 / M24).**
This is *not* a certification of changes introduced by any later integration,
rebase, merge, retargeting, or upstream source reconciliation.

**Current PR #567 metadata when recorded:**
- PR base: `issue-543-on-demand-ci-certification` at
  `e34853b2394047c2a05e6d6dd2e3638ff3d91a27`.
- PR head: `issue-543-unified-hosted-certification-probe` at
  `a6806d7d68c4d5191f49eff51de6bb4146c60db7`.
  This head is the *evidence-publication commit*, **not** the tested source.
- GitHub mergeability `false`, `mergeable_state=dirty`, DRAFT.
  The branch histories diverged at
  `e4f62dd73c87e33166c84540e00a77df0dfa16ce`;
  PR head is 212 commits ahead and 189 behind its **PR base**, not main.
  All 28 material source-conflict overlaps and missing upstream contracts
  require explicit integration reconciliation before any integration verdict.
- No merge, force/rebase, production activation, protection mutation, or tag
  is authorised. #85 remains **SECURITY-DEFERRED**; #86 retains protected
  production-release certification.

### Exact source-to-provider evidence ledger

| Stage / scope | Tested source SHA | Invocation SHA | GitHub Actions run | Immutable artifact ID | Evidence-publication commit | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Full regression | `2c8b0f9d5e63f2d0ceb5d602e7778796fb0dde28` | `e75161b3b8492d8643bd499aedf4ee73fa20ff74` | 38116994497 (1,134/1,134) | 11694216394 | `86845af8604f0b119ba1ed06240b59e4453dfc6d` | PASS |
| Full integration / nine OS probes | `2c8b0f9d5e63f2d0ceb5d602e7778796fb0dde28` | `6eed56a250a27017742acad088bf4ddec3923207` | 38116985364 (1,134/1,134; 9/9 platform) | 11694476097 | `a6806d7d68c4d5191f49eff51de6bb4146c60db7` | PASS |
| GREEN authenticated replay | `2c4dacb52f94f0f8c3decc9ad2b768953a4e074d` | `1fd08d487405517225aedc556b84a962e0b0c857` | 38115919788 (`reused=true`) | 11692429962 | `fc3f3caca0a45765d46be68850613072ea6caadf` | PASS at predecessor implementation; material binaries matched final source |
| Independent 38-test acceptance | `7dbb05b2601125356b3f4d84622f8fe3b7d59c1e` (test-only descendent of `2c4dac...`) | `0ccad6ccbfc8fdb822a07404e8689dfa77d80a9b` | 38116877362 (38/38, no skip) | 11694225560 | `0a3ce79d529b815ed619096b51d66c43794b802e` | PASS for functional source |
| Declared RED | `e720c95f36308d47c83568dce3e3b41788e76797` (RED fixture descendent of `2c4dac...`) | `ad8ad8d50c8887646a6296ac99566c9a3e909dc3` | 38116126460 (exit 1 correctly RED) | 11692879885 | `76704ab9899d6d26d42411b6e3e011f05a946779` | PASS for fixture |
| Temporary / original #629 harness | `ca2ed45abf602a117cc4a89269cadfc9b6205a30` (test-only descendent of `2c4dac...`) | `f9301d715a1b0e112a29c6dc1f94b18b05677313` | 38116026636 (55 PASS, 14 SKIP) | 11693585288 | `30d8ec4a8adf05bd032fc1e169a79886bb7ea186` | Executed; 14 skipped checks remain SKIPPED, not provider PASS |

All six artifact IDs were checked as unexpired provider results;
their per-run identity, SHA and publication links are separate fields.
The immutable final regression digest is
`sha256:d38577762b51a22b2ae6401d0c56ba5521aa1740b15083318197ed03bd2eb2a8`;
the integration digest is
`sha256:14eb9a9e29acc2bd5dbc53e001edab6a37eb0e3492bfb20a7e1184bc385714dc`.
The independent acceptance digest is
`sha256:ecdd505673690bd9f8516d61e9a9535881fc1f244967d84c1273865e948cc9a1`.

**Integration disposition: BLOCKED — content and ancestry reconciliation.**
The certified functional source is GREEN, but the PR is not a mergeable
integration candidate. Its target branch has newer contracts from #552/#547
that are absent or differ on the certified branch. Reconcile and retest the
resulting exact integrated material source before describing it as GREEN.
Security #85 remains DEFERRED and is not a functional prerequisite.

---


## Historical certification snapshot (superseded for final-source identification)

The evidence below records earlier *actual* certified source and provider
runs. It remains historically valid for those immutable revisions, but the
above ledger is authoritative for the **latest certified** source.

## Earlier exact revision and evidence boundary

- Repository: `Ma-XX-oN/RepoWorkflow`; current integration PR [#567](https://github.com/Ma-XX-oN/RepoWorkflow/pull/567).
- Original lane audit base: `dcdaea2db881b4075cbd87ab9d225d5fe8ae4bf2`.
- Final functional implementation source: `e47cfd2dd5a3598f748bb8e9be4414858e490fdb` (hosted tested).
- Final invocation `09559dc16d6c608c7afe017cae10c653832a3d60`; successful publication commit `741d24190bff50855921225d1f689f4aaebebd25`.
- Hosted final integration run `38114398190`: 1,118 tests PASS, 9/9 Ubuntu/Windows/macOS jobs PASS; immutable artifact `11692917496`.
- Hosted regression `38114405143`: 1,118 tests PASS, artifact `11692588205`. GREEN `38114696089` and reused retry `38114733164`. RED `38114648490` uses a derived fixture commit with the same implementation; temporary `38114658271` similarly.
- Historical runs on different source revisions are contextual evidence only, never final exact-source certification.
- #85 protected-main and production controls are **SECURITY-DEFERRED**, not functionally accepted. No merge, release tag, or production activation authorised.

## Independent acceptance matrix

| ID | Requirement | Status | Evidence / outstanding work |
|---|---|---|---|
| M01 | Six public test families and spelling | **PASS** | Six public stage CLI probes, local #629 tests. |
| M02 | Single persisted RED selection; zero one many invalid | **PASS** | Committed RED/GREEN selection tamper/deletion regressions, final source. |
| M03 | Stage help and --remote option grammar | **PASS** | Stage help and --remote grammar probes; Bash double-tab timing regression. |
| M04 | Superseded validate commands absent | **PASS** | Legacy validate commands rejected by CLI tests. |
| M05 | Dedicated marker stage and pre-invocation tip | **PASS** | Committed HEAD invocation marker; provider stage plan success. |
| M06 | Missed invocation retry binds immediate previous tip | **PASS** | GREEN retry 38114733164; temporary retry 38114232821, both exact-source-bound. |
| M07 | No paid testing on ordinary push | **PASS** | GitHub Actions head_sha search found zero runs for ordinary source commit 1143dbd44c01e7b5be9b16fc2f21ee2e49ed0ad2 and documentation commit d903ae657ad9e2708ee33f55cd05d42443a30459; dedicated .ci/run invocation 988e050ab0a6c83aadd74bc9615c0bcd0960ad29 dispatched 38115394811. Workflow paths: .ci/run only. |
| M08 | Remote results reading triggers no new run | **PASS** | Hosted validate jobs ran read-only remote-results retrieval. |
| M09 | Local and hosted stages select equivalent tests | **PASS** | PASS: live provider run 38116877362, 5/5 immutable-artifact selection parity tests. RED and GREEN committed single selection; temporary exact sorted catalogue groups (10); integration four fixed groups; regression aggregate, all bound to source commits. |
| M10 | Canonical per-issue testing log write | **PASS** | Canonical per-issue JSONL in provider commits, immutable archives. |
| M11 | Local results reads canonical log | **PASS** | Local results parser and malformed-tail rejection tests. |
| M12 | Remote results retrieves provider records | **PASS** | Hosted remote retrieval after provider publication; verified logs. |
| M13 | No one many invalid for each stage | **PASS** | PASS: live provider run 38116877362, 21/21 real-Git CLI tests, zero/one/many/invalid decision classes incl. RED/GREEN no-selection SKIPPED without dispatch, malformed, unknown, duplicate and multi-group rejection, temporary 0/1/many/failure, results 0/1/many/invalid; full regression/integration positive provider runs 38115863747 and 38115856141. |
| M14 | Malformed or stale RED selection rejected | **PASS** | Uncommitted, deleted, malformed selection rejected against HEAD. |
| M15 | Missing selection warns and records SKIPPED not PASS | **PASS** | Never-configured RED/GREEN selection yields logged SKIPPED. |
| M16 | Temporary catalogue path and cleanup | **PASS** | Temporary groups and cleanup tested; provider 38114658271. |
| M17 | Expected RED vs unexpected exit and infrastructure failures | **PASS** | RED provider 38114648490 classified declared exit 1 as RED, no fake zero-exit. |
| M18 | Unchanged accepted GREEN PASS actually bypasses subprocess | **PASS** | GREEN first 38114696089 reused=false, retry 38114733164 reused=true; temporary retry similarly. |
| M19 | Changed inputs invalidate applicable cached evidence | **PASS** | Temporary changed-input 38114304426: two groups rerun, both reused=false. |
| M20 | Exact candidate and catalogue SHA binding | **PASS** | Provider invocation/candidate SHA and catalogue binding, retry lineage negative tests. |
| M21 | Reject failed missing stale or replayed evidence | **PASS** | PASS: live provider run 38116877362, shared 12/12 provider-negative tests (M21/M28): stale invocation/source, replays of stage, catalogue, group and reuse lineage, missing run, failed plan and malformed selection all refused. Authentic immutable success accepted. |
| M22 | Reject forged/malformed external evidence | **PASS** | Independent forged group/PASS catalogue/reuse mismatch tests fail closed; immutable provider ZIP diagnostic 38115761761 successfully downloaded and authenticated the real 38115545410 artifact; provider metadata/run identity/record equality are checked before reuse. |
| M23 | Linux Windows and macOS hosted matrix | **PASS** | Final integration run 38114398190: 1118/1118 tests and all 9 platform jobs PASS. |
| M24 | Protected main refuses direct push bypass force delete | **SECURITY-DEFERRED** | SECURITY-DEFERRED (#85): protected-main direct push/bypass/force/delete controls. |
| M25 | Stale destination race rejects later candidate atomically | **PASS** | Real GitHub test-only two-actor atomic expected_sha probe: stale expected base 1143dbd... rejected candidate 44bc9a3d..., target preserved 9c13b270...; same descendant with correct expected SHA accepted. Local publisher stale branch test passes. Production protection is separately #85 deferred. |
| M26 | Reconcile required checks and documentation | **PASS** | PUBLIC_WORKFLOW.md and WORKFLOW_INTEGRATION.md reconciled with authenticated immutable artifacts, preserved Self CI, correct public rwf test interface and explicit #85 security deferral; canonical 29-row matrix repaired. |
| M27 | Provider immutable artifact lookup | **PASS** | Immutable artifacts for all five stages; final integration artifact 11692917496, readback verified. |
| M28 | Incomplete failed and unavailable provider outcomes | **PASS** | PASS: same 12/12 real-provider negative suite (38116877362): incomplete RED run 38115556576, failed selection 38115630268, failed plan 38115957182, nonexistent provider run and simulated transport outage all fail closed without PASS fabrication. |
| M29 | Source-mixed request and uncommitted marker tamper | **PASS** | Source-mixed commits and uncommitted marker tampering rejected by real-Git tests. |

## Remaining functional provider work

All **28 functional criteria are PASS**. M09/M13/M21/M28 are supported by independently executed GitHub Actions run 38116877362: 38/38 non-skipped tests in three stage groups, immutable artifact 11694225560 (SHA256 ecdd505673690bd9f8516d61e9a9535881fc1f244967d84c1273865e948cc9a1). The test-only candidate 7dbb05b2601125356b3f4d84622f8fe3b7d59c1e descends directly from tested functional implementation 2c4dacb52f94f0f8c3decc9ad2b768953a4e074d, with additional tests/temporary catalogue only; no replacement implementation source. Protected-main required checks remain **SECURITY-DEFERRED** under #85 and production certification #86. No merge, tag or production activation.

**Matrix count:** 28 FUNCTIONAL PASS, 0 FAIL, 0 FUNCTIONAL INCOMPLETE, 1 SECURITY-DEFERRED (#85). The final documentation update itself is not an on-demand source-execution PASS; perform exact new-tip regression/integration verification separately as a closure cross-check.
