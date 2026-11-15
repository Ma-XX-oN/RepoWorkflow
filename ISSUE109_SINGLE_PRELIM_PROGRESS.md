# RWF #109 single-PRELIM implementation checklist

Base: add058f5f4139f6e9cbe5103cbc84c760f6f0404.
Branch: issue-109-single-prelim. Governing contract: SINGLE_PRELIM_WORKFLOW.md.
Status: WIP; no full workflow acceptance or production activation claimed.

- [x] Read current source, operator decisions and execution rules.
- [x] Create deferred independent RED-selector issue #828; leave repairs out.
- [x] Record #828 in canonical ticket state, commit and read back (767f8f27).
- [x] Update authoritative contracts/tickets preserving historical requirements.
- [x] Reconcile accepted #660 source and catalogue/manual remote conflicts.
- [x] Separate submission eligibility from merge eligibility in planner.
- [x] Classify current, stale-latest and superseded PRELIM submissions by numeric version.
- [x] Name branches PRELIM-issue-N.<rest-of-version>; remove predecessor ordering.
- [x] Replace INT-ATTEMPT creation/consumption with one PRELIM path.
- [ ] Bind normal public done to real provider and completion machinery.
- [x] Keep source identity/version stable across report commits and resumes.
- [x] Replace success with same-source CI-FAIL on subsequent test failure.
- [x] Implement manual index/name selection and shell progress.
  Opt-in Bash, PowerShell and Zsh hooks are supplied. Actual Bash and
  PowerShell execution passed locally; native Zsh verification remains open.
- [ ] Implement remote conflict email plus durable handoff.
- [x] Register/run contract-derived tests through catalogue selection.
- [ ] Verify real disposable workflow and native platform requirements.
- [ ] Supply independent #703/#583/#677 acceptance handoffs.

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
