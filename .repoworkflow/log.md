# RepoWorkflow workflow audit log

This file is append-only.  Add new audit entries at the end; do not rewrite or
merge existing entries.

## Lane A — A.227 → A.228 — 2026-10-04

### Outcome

Lane A completed 2/2 issues.  The lane procedure was useful because checking
repository truth and performing the leaf-to-root contract synchronization
found requirements that were not visible from the original lane assignment.

### Experience

The initial repository check showed that #227 was already complete and that
#228 had acquired blocker #240.  The synchronization check then found another
missing prerequisite: conflicting legacy relationship records cannot invoke
#227 parent recovery unless migration is explicitly given the canonical work
branch identity.  The legacy relationship record itself does not contain that
identity, and deriving it from issue metadata or dependency topology would
violate the frozen recovery contract.  This was recorded as #242, documented,
implemented as a prerequisite contract, and added to #228 before continuing.

While #228 was being implemented, another worker independently completed and
merged #228.  The duplicate implementation was therefore abandoned rather
than integrated.  This demonstrated that a published-lane worker needs to
refresh repository/issue/PR truth both before beginning a node and immediately
before integration.  Lane ownership/display assignment alone does not prevent
concurrent duplicate work.

Verification of the implementation that actually landed on main found a case
that its tests missed.  Parent recovery worked when the local work branch
existed, and when only the parent local ref had been deleted, but it failed in
a normal fetched clone containing only a remote-tracking work-branch ref.
That contradicted #227's fetched-clone postcondition.  The deficiency became
#246; the repair made work-branch resolution deterministic across local and
remote-tracking refs and added remote-only and conflicting-ref coverage.

The #246 repair passed the PR validation gate and was merged, but the
main-branch release job then failed because VERSION was still 0.1.63 and tag
v0.1.63 already existed.  VERSION was advanced to 0.1.64 and the final main
workflow completed successfully.  A deterministic release invariant that can
be evaluated before merge should be part of the integration gate rather than
being discovered only after main has changed.

These concurrency and pre-merge-gate deficiencies are tracked in #249.

### Workflow observations

The preliminary leaf-to-root precondition/postcondition/invariant check was
valuable and should remain mandatory.  It found both #242 before #228 work
proceeded and the fetched-clone defect after a nominally complete #228 had
landed.

The workflow should distinguish issue completion from verified satisfaction of
the lane node.  When another worker completes a node, the lane worker should
discard/supersede duplicate implementation work but still verify the landed
result against the node's postconditions and invariants before advancing.

Published lanes need an explicit concurrency refresh point immediately before
integration.  The refresh should detect completed issues, changed blockers,
overlapping/superseding PRs, and parent/main advancement.

The integration gate should include all deterministic repository invariants
required for the resulting main commit to pass, including VERSION/tag
uniqueness.  A GREEN test/validation job alone was insufficient in this run.

The lane notation A.227/A.228 worked well as coordination/display identity.
Keeping actual dependency relationships as issue numbers avoided conflating
lane membership with dependency or parent topology.

### Final state

A.227 and A.228 were closed and verified.  #242 and #246 captured and resolved
missing work discovered by the lane exercise.  #249 remains as the explicit
workflow-improvement issue.  Final main validation/release was GREEN at
3dad4982ab7fffa275e8149584a00f3de6dd0b92 with VERSION 0.1.64.
