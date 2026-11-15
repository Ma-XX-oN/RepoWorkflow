# RWF #109 single-PRELIM implementation checklist

Base: add058f5f4139f6e9cbe5103cbc84c760f6f0404.
Branch: issue-109-single-prelim. Governing contract: SINGLE_PRELIM_WORKFLOW.md.
Status: WIP; no full workflow acceptance or production activation claimed.

- [x] Read current source, operator decisions and execution rules.
- [x] Create deferred independent RED-selector issue #828; leave repairs out.
- [ ] Record #828 in canonical ticket state, commit and read back.
- [ ] Update authoritative contracts/tickets preserving historical requirements.
- [ ] Reconcile accepted #660 source and catalogue/manual remote conflicts.
- [ ] Separate submission eligibility from merge eligibility in planner.
- [ ] Classify current, stale-latest and superseded PRELIM submissions.
- [ ] Replace INT-ATTEMPT creation/consumption with one PRELIM path.
- [ ] Bind normal public done to real provider and completion machinery.
- [ ] Keep source identity/version stable across report commits and resumes.
- [ ] Replace success with same-source CI-FAIL on subsequent test failure.
- [ ] Implement manual index/name selection and shell progress.
- [ ] Implement remote conflict email plus durable handoff.
- [ ] Register/run contract-derived tests through catalogue selection.
- [ ] Verify real disposable workflow and native platform requirements.
- [ ] Supply independent #703/#583/#677 acceptance handoffs.

## Execution findings

The assembly lacks AGENTS.md, AGENT_EXECUTION_STANDARD.md and BEST_PRACTICES.md;
their current origin/main copies were read through Git. The public CLI has
only injected done_executor support. The planner blocks on missing validation.
Provider modules assume separate immutable PRELIM/mutable INT-ATTEMPT refs.
The catalogue and accepted main disagree about invariant stage semantics;
source refresh must preserve both required coverage and manual/RED behavior.
