# RWF #109 single-PRELIM implementation checklist

## Final completion — 2026-11-16

**Status: #109 CLOSED — approved functional scope verified.** #701/#702 are
also closed after resolving their audited gaps. #700 was already closed;
#703 remains open only for its separately owned live-provider certification.

- [x] Preserve the supplied nonblank MIT operator and evidence-reference values exactly; verify the registered result suite.
- [x] Update obsolete completion/INT-ATTEMPT expectations to the approved grammar and single-PRELIM model without dropping negative assertions.
- [x] Commit and publish the Q/R implementation and documentation, preserving deferred #828/#829 scope.
- [x] Verify the final exact source through catalogue-selected native Linux/macOS/Windows checks.
- [x] Record source/results and downstream handoffs on #109; close #109 when its functional scope is verified.

The separate #703/#583/#677 certification tickets do not block #109 completion.
Existing adversarial-security deferrals remain in force. No production merge or deployment is part of this completion.

Published source: `372ec0e46c8b52f90d312edc0bd8688b28f48036` on
`issue-109-single-prelim`. Local catalogue-selected correction checks: 31 MIT
result, 4 real Bash completion and 13 MIT negative checks PASS. The preservation
regression was observed failing before the two-value persistence fix.

Final native matrix: [43887650727](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43887650727),
workbench commit `dba47fa12680252492ad5ff84041d6ef9597c888`, pins that exact
RWF source and resolves all 52 selected groups through `.ci/tests.json`.
All three native jobs completed SUCCESS: Linux, macOS and Windows each ran
52 catalogue groups / 703 test executions, with zero failures, errors or skips
(2,109 executions across the matrix). Job IDs: Linux `133370021813`, macOS
`133370021196`, Windows `133370021594`. Terminal job logs and all 52 successful
group return codes were read back. Only documentation checkpoints changed
after the tested source; no implementation or test code changed.

The source/results handoff is published on #109 and the covered MIT tickets.
#583/#677 consume this completed implementation for downstream certification;
their closure is not a #109 prerequisite. #828/#829 remain deferred. No
production main merge, protected release, live email or deployment is claimed.

## Q/R implementation alignment — earlier local checkpoint

- [x] Prepare first implementation as Q=1/R=0; changed implementation advances Q and resets R.
- [x] Advance R only for the same implementation reconstructed against a newer parent.
- [x] Preserve counters on failures, unchanged resumes, report commits and additional test runs.
- [x] Verify source correction, parent-only progression, combined changes and resume behavior with registered tests.
- [x] Preserve deferred #829 naming work and existing documentation edits.

Scope: issue-109-single-prelim worktree; no branch-naming extension or unrelated selector repairs.

Source: uncommitted Q/R changes over b69565a810f0f52ed5da069888d1e967d56649d6.
Native Windows checks: 10 submission tests PASS; adapter/failure transitions
34 PASS and one existing unsupported-symlink SKIP; engine/manual-result checks
46 PASS; 34 issue-start/terminal/completion workflow checks PASS; 17 consumer
checks PASS, including parent-reintegration/resume. Total: 141 PASS, one
existing unsupported-symlink SKIP. Python compilation and whitespace checks PASS.
Logs: rwf-qr-submission-final.log, rwf-qr-adapters.log,
rwf-qr-manual-engine.log, rwf-qr-consumer-final.log and rwf-qr-workflow.log
under the system temporary directory. Q/R alignment is complete in this
working tree; changes remain uncommitted. Native Linux/macOS runs were not
performed for this update. Deferred naming work remains owned by #829.

Base: add058f5f4139f6e9cbe5103cbc84c760f6f0404.
Branch: issue-109-single-prelim. Governing contract: SINGLE_PRELIM_WORKFLOW.md.
Earlier checkpoint status: version-only implementation READY for review; focused native checks PASS.
The title/extra naming extension is explicitly deferred to follow-up #829.
No full independent-ticket acceptance or production activation is claimed.

## Active continuation requirements

The operator explicitly deferred adversarial security work. External verifier
programs and symlink attack certification do not block functional completion.

Continuation implementation includes the default native dispatch, ordinary
three-platform Actions worker, immutable report exchange, configured consumer
environment adapter, exact-parent atomic acceptance, canonical lifecycle and
completion receipts. Existing provider verifier hooks remain available to
their original callers; native completion does not require installing them.
The operator approved outgoing SMTP implementation after automatic approval
review rejected the initial addition. The client is implemented; delivery
failures are retained in the immutable conflict receipt. No live email has
been sent during implementation checks.

Latest completed functional run: 10 checks PASS (actual local bare Git,
executable catalogue tests, public worker CLI, SMTP transport fixtures).
Further checks cover push-time parent races, lost acknowledgements,
configured environments, and durable conflict notification idempotence.
These results do not claim live GitHub or native three-platform acceptance.
Historical prerequisite statements below are superseded by this active scope.

- [x] Connect native hosted done to actual catalogue execution and Git acceptance.
- [x] Select the latest numeric submission, rebuild stale parent inputs before tests.
- [x] Reuse applicable group/platform PASS; stop current-source failures.
- [x] Retain per-platform reports and require externally recorded manual results.
- [x] Complete parent update and PRELIM retirement with expected-old Git leases.
- [x] Persist completion/lifecycle provenance without inventing test PASS.
- [x] Send remote conflict email through an outgoing client and retain failed delivery.
- [x] Preserve the version after manual FAIL; prepare another only after source changes.
- [x] Publish external manual verdicts from any matching checkout and resume pending CI.
- [x] Exercise the actual default path and update current documentation.
- [x] Defer the new start/branch naming extension to #829; preserve operator WIP.

## Final version-only implementation verification

Code revision: `20aef015e94c257bae60dfa7e154d807eb7d1aae`, published on
`issue-109-single-prelim`. Native workbench invocation:
`Ma-XX-oN/Disposable-001` commit `275d857fa3725dabed3905da4dca84a790db9529`.
[Run 43757653797](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43757653797)
completed SUCCESS with the exact RWF source SHA asserted on every platform.

| Platform | Native job | Selected checks | Result |
| --- | --- | --- | --- |
| Linux | 132945165430 | 160 | PASS, no skips |
| macOS | 132945165718 | 160 | PASS, no skips |
| Windows | 132945165752 | 160 | PASS, no skips |

The nine registered groups cover source/version identity, latest PRELIM
selection, real Git publication/retirement, executable catalogue tests,
environment checks, missing-platform waits, external manual verdict exchange
from an arbitrary branch, prompt hooks, parent races, lost acknowledgements,
completion/lifecycle records, outgoing SMTP transport fixtures and CI dispatch.
These are focused native checks, including disposable bare Git providers;
they do not claim a live protected-parent merge, a sent live email, the full
unmodified suite, or independent #703/#583/#677 acceptance. No parent ref was
updated and no ticket was closed. RED selector repair #828 remains deferred.

An operator edit discovered after verification changes the governing naming
text to `PRELIM-issue-N.<rest-of-version>-<title>[-<extra>]` and refers to
versioned issue branch names produced by `rwf start`. The edit is preserved
unstaged. The verified code implements the prior version-only rule. The
operator explicitly deferred both the optional start argument and issue/PRELIM
branch naming changes to [#829](https://github.com/Ma-XX-oN/RepoWorkflow/issues/829).
The new ticket is recorded in the canonical CSV without dependency edges;
it does not block or expand this implementation.

Expanded functional run: 16/16 PASS, including actual parent advancement at
the atomic push boundary, successful publication with lost acknowledgement,
external manual-result exchange, configured environment execution/reuse and
durable conflict notification idempotence. The first expanded run had one
test-fixture error from treating subprocess.CompletedProcess as a dataclass;
the corrected run passed all 16. Logs: Temp/rwf109-final-native.log and
Temp/rwf109-final-native-corrected.log. Exact-source native matrix verification
uses the authorized public Disposable-001 workbench and catalogue selection.

Native workflow source snapshot `2e91618ed9d9928762b2245631b769ef48a414d0`
is published on `issue-109-single-prelim`; no parent branch was updated.
The subsequent shared-CLI sweep exposed uppercase SKIPPED reports being
misclassified as material source. Report recognition accepts the canonical
emitter's spelling; RED selector behavior remains outside this change.
Manual-result checks: 30 PASS after completing the unchanged-version default
failure handler and its canonical CI-FAIL evidence. Workflow dispatch has a
dedicated empty-success response path; ordinary JSON endpoints retain their
existing response requirement. Final catalogue and native matrix checks follow
the resulting source revision rather than the earlier snapshot.

Exact-source native run 43755561389 at `9d63970e`: Ubuntu and macOS passed all
selected groups. Windows passed source classification, then failed two SMTP
transport fixtures during real SSL-context initialization despite mocked SMTP.
Those fixtures isolate SSL-context creation along with the mocked outgoing
transport; production certificate verification and expected results are unchanged.
No platform skip or alternate expectation was added. Final-source rerun follows
the manual-verdict delivery handoff: each verdict publishes a real report;
the final PASS or FAIL dispatches CI, and report-tag pushes also wake the worker.
The updated arbitrary-branch manual report/acceptance check passed in the
16-case functional group. Standalone CLI verification exposed an eager
provider-adapter import; loading it only for an actual submitted CI attempt
preserves standalone manual testing. Corrected reruns: manual CLI 17 PASS,
native submission 7 PASS (Temp/rwf109-manual-cli-resume-fixed.log).

Implementation snapshot: `934131a70176fd2cb9753258faa2011eb20ce972`.
Post-commit catalogue verification at that SHA: 21 single-PRELIM checks,
7 native submission checks and 2 concurrent bare-Git publication checks PASS
(30 total), captured in local Temp/rwf109-committed-source.log. This following
checkpoint commit changes documentation only. The isolated worktree is
clean after checkpointing; no implementation branch push or merge occurred.

- [x] Read current source, operator decisions and execution rules.
- [x] Create deferred independent RED-selector issue #828; leave repairs out.
- [x] Record #828 in canonical ticket state, commit and read back (767f8f27).
- [x] Update authoritative contracts/tickets preserving historical requirements.
- [x] Reconcile accepted #660 source and catalogue/manual remote conflicts.
- [x] Separate submission eligibility from merge eligibility in planner.
- [x] Classify current, stale-latest and superseded PRELIM submissions by numeric version.
- [x] Name branches PRELIM-issue-N.<rest-of-version>; remove predecessor ordering.
- [x] Replace INT-ATTEMPT creation/consumption with one PRELIM path.
- [x] Bind normal public done to ordinary Git/CI completion machinery.
- [x] Keep source identity/version stable across report commits and resumes.
- [x] Replace success with same-source CI-FAIL on subsequent test failure.
- [x] Implement manual index/name selection and shell progress.
  Opt-in Bash, PowerShell and Zsh hooks are supplied. Actual Bash and
  PowerShell execution passed locally; native Zsh verification remains open.
- [x] Implement remote conflict email plus durable handoff.
- [x] Register/run contract-derived tests through catalogue selection.
- [x] Verify the selected completion checks on the real disposable native matrix.
- [x] Supply the #109 implementation/evidence handoff for separately owned #703/#583/#677 certification; their independent acceptance remains downstream.

## Execution findings

Current continuation: all 66 selected #109/#683/provider/retirement catalogue
groups have passing local results after repairs. Manual launcher/prompt checks
17 PASS, including actual Bash and PowerShell hooks; manual results 29 PASS.
The broad sweep initially had 11 failing groups; their corrected reruns are
captured in rwf109-sweep-fixes.log, rwf109-adapter-fixes.log and
rwf109-final-remaining.log under the local Temp directory. These are local
fixtures, including real bare Git operations; they are not authenticated
live-provider or multi-platform acceptance.

Current version checks: engine preparation 13 PASS, terminal phases 12 PASS,
hosted identity 51 completed with two existing skips, real consumer verifier
16 PASS and local terminal 6 PASS. The terminal-tag group completed 39 cases
with three existing skips and one Windows WinError 1314 symlink-fixture error;
that group is not GREEN. No assertion or privilege requirement was removed.
The corresponding log is rwf109-final-version.log. Native/provider acceptance
must resolve that environment limitation, not reinterpret it as PASS.

The approved version-only naming/selection rule was added explicitly to
the current contract preambles of issues #108/#109/#681/#683/#103/#677;
each complete body was read back and compared after the update. Historical
requirements were retained, and no ticket was closed.

Native public local done now publishes PRELIM and provenance with deferred
tests, reports submitted rather than DONE, and preserves the parent. Seven
real local Git checks cover unchanged resumes, version advancement after
source changes, stale-parent reconstruction, current-source FAIL refusal,
and durable conflicts. Deferred provider certification runs before the
unchanged strict merge executor, which still requires a fully allowed fresh
plan, current admission and expected-old parent SHA. Preparation from a
different checkout preserves an already-current pinned source and version.
The reviewed attempt
to relax that executor gate was rejected; no such relaxation was applied.

Outstanding implementation: bind the hosted public completion command to
the protected server coordinator, connect stale selected PRELIM reconstruction
to that server loop, and implement remote conflict email using its authorized
notification service. Authorization and integration-evidence verifier commands
are both absent from this checkout's environment. A workbench/configuration
reference has been requested; no secrets, production activation or fabricated
authority are required. Independent #703/#583/#677 acceptance remains open.
The historical handoff and acceptance ledger confirm that the independent
release/MIT issuer and trusted server runtime were not installed. They also
identify public Disposable-001 as a historical native testing workbench;
its old tests and triggers do not certify this unpublished implementation.

Latest operator corrections govern this continuation: branch names contain
the issue-version suffix only, with no destination or GUID. Select the highest
numeric version per issue before consulting outcomes; ignore all older
versions even if the latest fails. Copy a stale selected PRELIM to the exact
parent tip before testing. A current candidate reuses applicable PASS results.
The October 22 manual CLI specification selects and presents a manual case;
the external tester records succeeded/failed. No executable manual harness
has been newly required by this conversation.

At the initial assembly revision, AGENTS.md, AGENT_EXECUTION_STANDARD.md and BEST_PRACTICES.md were absent;
their current origin/main copies were read through Git. The public CLI has
only injected done_executor support. The planner blocks on missing validation.
Provider execution modules still assume separate immutable PRELIM/mutable INT-ATTEMPT refs.
The catalogue and accepted main disagree about invariant stage semantics;
source refresh must preserve both required coverage and manual/RED behavior.

Initial contract/classification checks: 9 new and 28 existing planner tests PASS
through registered groups. Repeated after resolving the origin/main merge,
with the same counts and results. This proves isolated policy only; concrete
provider scheduling and full native/disposable acceptance remain incomplete.

Accepted main was reconciled in merge commit 40abaa4f. Engine/consumer
preparation share version_evidence.py; generic aggregate result publication
shares fixed-target terminal publication. Registered consumer verifier checks:
16 PASS; local terminal checks: 6 PASS. Tag group: 39 executed, 1 existing
Windows symlink privilege error and 3 skips; remaining behavior passed.

Provider generation scheduling reads immutable receipts through submission.read.
Receipt publication atomically creates PRELIM plus provenance, retains source
objects on unchanged retry and does not assert test PASS. Registered checks:
21 policy/source/publication/provider cases, 11 scheduling cases and 7 queue
cycle cases PASS. These include actual local bare-Git publication fixtures,
not genuine remote provider certification.

A GitHub checkpoint comment was rejected by automatic approval review because
it contained internal implementation status and a local filesystem path.
No comment was posted; do not retry that disclosure through another tool.
