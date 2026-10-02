# RepoWorkflow Test Strategy

Status: test specification for issue #14 and the guarded task-to-release
lifecycle.  This document defines the tests required to establish that
RepoWorkflow implements the contracts in `WORKFLOW_LIFECYCLE.md` without
requiring the user to act as a routine test stage.

The lifecycle specification is authoritative for behaviour.  Tests must be
added with the implementation stage that introduces the behaviour; a stage is
not complete merely because its implementation exists.

## 1. Test principles

RepoWorkflow must test policy at several levels:

1. unit tests for pure state, parsing, naming, and policy decisions;
2. CLI/contract tests for user-visible commands, exit codes, JSON, and
   diagnostics;
3. Git integration tests using disposable repositories and bare remotes;
4. concurrency tests using independent clones/workers against one remote;
5. hosted tests for GitHub/server behaviour that cannot be faithfully reduced
   to a local bare remote;
6. end-to-end lifecycle tests that cross subsystem boundaries.

Every safety invariant needs both a positive test proving the legal operation
works and a negative test proving the corresponding illegal operation is
blocked.

Tests must verify observable repository state, not only return codes.  Where
applicable this includes HEAD, branches, remote refs, tags, versions, audit
records, working-tree cleanliness, and exact candidate SHAs.

A GREEN result for one physical candidate must never be silently reused for a
different SHA.

Tests must not depend on the user's machine or manual acceptance.  Temporary
repositories, remotes, GitHub test branches/PRs where required, and automated
shell interaction are the test harness.

## 2. Cross-cutting tests

These tests apply across implementation stages.

### 2.1 State and command consistency

- every legal state-machine transition is reachable through its documented
  command;
- every illegal transition is rejected without partial mutation;
- `what-next`, `what-next --json`, CLI command acceptance, local guards, and
  completion agree on the same legal transitions;
- blocked operations include an actionable reason;
- failed commands leave repository/workflow state unchanged unless the
  transition explicitly records failure evidence;
- `repo-workflow` and `rwf` behave equivalently.

### 2.2 Exact-candidate identity

- evidence records the exact tested SHA;
- evidence for SHA A is accepted for A;
- evidence for A is rejected for changed SHA B;
- version-only, branch-only, or tag-name-only equality cannot substitute for
  SHA identity;
- mutations made by validators are detected, rolled back where specified, and
  cannot produce PASS evidence.

### 2.3 Validation environment evidence

- every authoritative validation record includes structured `platform`
  evidence with OS and architecture;
- validators that declare a relevant runtime/toolchain record its identity in
  `platform`;
- platform evidence is sufficient to distinguish materially different
  validation environments without relying on hostname or another machine ID;
- hardware-insensitive validators record `hardware: null` and do not inventory
  the host;
- hardware-sensitive validators record only their declared relevant
  capabilities/specifications;
- hardware evidence may include a required CPU feature, GPU model/API, or
  accelerator capability when the test contract requires it;
- hardware evidence never includes serial numbers, hostnames, MAC/network
  addresses, device IDs, account identifiers, or unrelated inventory;
- local and hosted validation both produce the same environment-evidence
  schema;
- evidence reuse enforces any platform/hardware constraints declared by the
  suite rather than assuming that evidence is portable merely because its SHA
  matches.

### 2.4 Git ref immutability and reachability

- task, PRELIM, and stable tags cannot be reused or moved;
- deleting an ephemeral branch does not make a tagged candidate unreachable;
- squashing the final integration does not destroy PRELIM reachability;
- malformed or unauthorized refs are rejected.

### 2.5 Concurrency and worker isolation

Use at least two independent clones against one disposable remote.

- simultaneous issue work does not corrupt shared state;
- simultaneous preliminary integrations receive different GUIDs;
- both `prelim-main-<GUID>` refs can coexist remotely;
- one worker cannot adopt, modify, or clean up another integration attempt;
- concurrent audit updates do not silently lose records;
- stale observations are rejected before destructive cleanup or integration.

### 2.6 Failure atomicity

Inject failures at mutation boundaries such as version update, commit, tag,
push, audit append, and cleanup.

- no operation reports success after a partial failure;
- rollback restores state where the contract requires rollback;
- immutable evidence already published is never rewritten during recovery;
- rerunning after an interrupted operation is deterministic or gives an
  actionable recovery state.

### 2.6 Platform coverage

- run the portable unit/integration suite on Linux and Windows;
- exercise Git invocation, path handling, process invocation, quoting, line
  endings, hooks, and launcher/alias behaviour on both platforms;
- platform-specific consumer validation remains INCOMPLETE rather than falsely
  PASS when the required platform/capability is unavailable.

## 3. Stage 1 - repository version adapter

This stage covers the repository-owned `repo-version` contract and RWF
forwarding.

Required tests:

- query current version in text and JSON forms;
- initialize `task issue <number>` through the adapter;
- patch and minor integration intents derive the expected literal version from
  the authoritative parent;
- major release increments major and resets minor/patch as specified;
- RWF does not directly edit repository-specific version storage;
- malformed adapter output is rejected;
- missing adapter/capability gives an actionable failure;
- adapter failure does not leave a partial version mutation;
- manually changing a version into a state inconsistent with the requested
  transition is detected;
- task counters are changed only by their owning workflow transitions;
- equivalent adapter behaviour works through `repo-workflow version` and
  `rwf version`.

## 4. Stage 2 - state machine, guidance, CLI, alias, and completion

Required state-machine tests:

- initial task-development state;
- regression-required state;
- ART PASS, FAIL, and INCOMPLETE transitions with no user result entry;
- local ART starts only on explicit full validation invocation; no heuristic such as
  code changes, idleness, or implementation completion starts it automatically;
- `validate regression --fast` runs the repository-defined minimal fast ART
  set and cannot satisfy/advance the complete ART gate;
- `validate regression --group NAME` runs only that ART group and cannot by
  itself satisfy/advance the complete ART gate;
- accumulated partial ART evidence does not satisfy the full gate unless the
  repository's declared complete required set for the exact candidate is
  authoritatively covered;
- AIT-required state and automatic AIT result recording;
- local integration validation starts only on explicit `validate integration`;
- bare `validate integration` orchestrates all required AIT and required MIT;
- `validate integration --automatic` selects AIT only and cannot skip a
  required MIT gate;
- `validate integration --manual` selects MIT only and cannot skip required
  AIT;
- `validate integration --group NAME` runs only the named integration subset
  and cannot by itself satisfy the complete integration gate;
- a full integration run executes AIT automatically but stops/presents required
  MIT for a human result rather than pretending MIT was automated;
- server examination automatically runs missing ART/AIT only; it never creates
  MIT evidence;
- AIT PASS, FAIL, and INCOMPLETE transitions, including automatic result
  recording and that AIT FAIL advances `Q` and resets `R`;
- MIT-required state only when manual integration testing is declared;
- MIT succeeded and failed human-result transitions, including that MIT FAIL
  advances `Q` and resets `R`;
- AIT PASS -> MIT-required when MIT is declared, versus AIT PASS -> accepted
  integration requirement when no MIT is declared;
- acceptance with AIT but no MIT, proving no unnecessary user test gate is
  introduced;
- accepted-but-not-yet-integrated state;
- preliminary-integration states;
- stale preliminary candidate state;
- landed-but-not-finalized state;
- finalized stable state;
- invalid transitions from every state are blocked.

Required `what-next` tests:

- text output identifies legal next actions;
- JSON exposes the same actions and blocked reasons;
- output is deterministic for the same repository state;
- no GREEN result, ready PR, or completed task is mistaken for a transition
  that the repository's policy does not permit.

Required completion tests must exercise an actual supported shell completion
environment rather than merely inspect generated text:

- completion is generated from the same state-machine result as `what-next`;
- `rwf validate integration <TAB>` offers only legal outcomes when a result
  transition is pending, and the state identifies whether it is AIT or MIT;
- illegal commands disappear as state changes;
- options such as `--json` remain options rather than workflow states;
- filenames or unrelated shell candidates do not leak into controlled
  transition positions;
- quoting and spaces do not corrupt completion;
- completion works after command aliases and partial tokens;
- completion failure cannot execute a workflow mutation.

## 5. Stage 3 - validation audit and local/hosted equivalence

Required audit tests:

- append one valid regression record;
- append one valid integration record;
- all required fields are present and correct;
- records preserve branch identity after branch deletion;
- records preserve exact `testSHA` and candidate tag identity;
- records are append-only through normal RWF operations;
- malformed/truncated records are detected rather than silently trusted;
- same-issue concurrent writes do not lose valid records;
- correctness does not depend on a locally configured custom merge driver.

Required validation-reuse tests:

- complete authoritative local evidence for exact SHA is reused;
- hosted validation runs missing required work;
- evidence from another SHA is rejected;
- changed validation-relevant candidate requires fresh evidence;
- INCOMPLETE evidence is not treated as PASS or FAIL;
- genuine FAIL creates only the appropriate immutable failure evidence;
- a pushed candidate always receives server-side examination even when hosted
  execution is skipped because exact local evidence is complete;
- local and hosted paths invoke the same validation contract and produce
  semantically equivalent results.

## 6. Stage 4 - GUID preliminary integration, reintegration, and PRELIM tags

Required creation tests:

- no prelim branch is created during ordinary issue development;
- beginning an authorized integration creates
  `prelim-main-<GUID>` from the current authoritative remote `main`;
- the GUID is newly generated per integration attempt;
- the integration record stores/identifies the correct GUID-bearing branch;
- a fixed shared `prelim-main` is never used.

Required concurrency tests:

- two workers starting simultaneously create distinct GUID branches;
- both branches push without collision;
- each worker continues to identify only its own integration record/branch;
- one worker cannot delete or mutate the other's prelim branch.

Required integration tests:

- accepted task/umbrella content is integrated onto the prelim branch;
- patch/minor intent produces the adapter-derived stable candidate version;
- integration-specific conflict resolution remains on the prelim candidate and
  does not rewrite the accepted issue branch;
- PRELIM tag names use the documented version/issue/generation/iteration
  identity;
- PRELIM tags are immutable and keep exact candidates reachable.

Required stale-main/reintegration scenario:

1. create server main A;
2. create and validate prelim candidate B' from A;
3. advance server main independently to B;
4. prove B' is now stale and cannot integrate using its old GREEN evidence;
5. combine B with B' to produce C while preserving integration-specific work;
6. derive the candidate version again from the new authoritative parent;
7. give C a new PRELIM identity;
8. require fresh exact-SHA validation/audit evidence for C;
9. prove B' evidence cannot satisfy C.

Required cleanup tests:

- push alone does not permit prelim cleanup;
- GREEN validation alone does not permit cleanup;
- ready/open integration PR alone does not permit cleanup;
- after RWF observes that the corresponding integration reached authoritative
  server `main`, local main is resynchronized and only that attempt's local
  and remote prelim refs are deleted;
- PRELIM tags/audit evidence survive cleanup;
- a later integration creates a fresh GUID from then-current server main.

## 7. Stage 5 - local Git guard layer

Each guard needs positive and negative tests.

Required tests:

- legitimate issue commit is permitted;
- manual/direct version edit outside the adapter is blocked;
- integration commit on tracking local `main` is blocked;
- equivalent integration work on the correct `prelim-main-<GUID>` is
  permitted;
- direct push to `main` is blocked locally;
- force-push and deletion hazards are blocked where policy requires;
- malformed task tags are blocked;
- malformed PRELIM tags are blocked;
- unauthorized stable tags are blocked;
- attempts to move immutable tags are blocked;
- stale prelim candidate operations are blocked;
- invalid branch/version combinations are blocked;
- transitions that `what-next` marks blocked are also rejected by guards;
- absence/bypass of local hooks cannot be mistaken for server authorization;
- guard failure is a STOP and leaves no repair-forward mutation.

## 8. Stage 6 - protected server integration and stable finalization

Use hosted integration tests where server behaviour itself is the contract.

Required server tests:

- direct push to protected `main` is rejected;
- direct issue/task integration into `main` is rejected;
- controlled GUID prelim integration path is accepted when all gates pass;
- force push and deletion of protected main are rejected;
- stale candidate is rejected after server main advances;
- exact-current-base candidate can proceed;
- required exact-candidate validation cannot be substituted with evidence for
  another SHA;
- ordinary development actors cannot arbitrarily create, update, or delete
  protected stable tags;
- server examines pushed candidates and runs only missing automated validation.

Required stable-finalization tests:

- finalization before candidate lands on authoritative server main is rejected;
- finalization against a non-current/local-only commit is rejected;
- landed exact candidate with complete gates can be finalized;
- canonical stable version is obtained through the repository adapter;
- existing stable tag causes STOP;
- final stable tag points to the intended landed server-main commit;
- stable tag cannot subsequently move or be recycled;
- PRELIM tag remains distinct from the stable tag even when both represent the
  same logical release candidate.

Where GitHub plan/repository permissions make a protection mechanism
unavailable, the test must record that as an external capability dependency;
RWF must not silently claim that boundary is enforced.

## 9. Stage 7 - consumer pilot and full lifecycle certification

The pilot must be automated and disposable enough that the user is not the
test harness.

At minimum, exercise these complete scenarios:

### 9.1 Happy path

Exercise both required forms:

- issue branch -> task version -> ART PASS -> AIT PASS -> no MIT required ->
  accepted -> GUID prelim -> patch/minor version intent -> PRELIM validation ->
  controlled server integration -> observe server main -> prelim cleanup ->
  stable finalization;
- issue branch -> task version -> ART PASS -> AIT PASS -> MIT PASS -> accepted
  -> the same integration/finalization path.

AIT result recording must occur automatically.  MIT result recording must be
an explicit human-result transition.

Verify every intermediate branch, version, SHA, tag, audit record, legal next
action, and cleanup result.

### 9.2 ART failure and recovery

ART FAIL -> immutable failure evidence -> automatic `R` increment ->
development fix -> new candidate -> PASS.  Prove failed evidence remains
reachable and cannot validate the replacement candidate.

### 9.3 AIT failure and recovery

AIT FAIL -> immutable integration-rejection evidence -> automatic `Q`
increment and `R` reset -> return to development -> new ART/AIT validation ->
AIT succeeds.  Prove no user result entry is required and that AIT failure is
not misclassified as an ART/CI iteration.

### 9.4 MIT failure and recovery

MIT FAIL -> manual rejection evidence -> automatic `Q` increment and `R` reset
-> return to development -> fresh automated validation -> required MIT -> MIT
succeeds.

### 9.5 INCOMPLETE and retry

Missing capability/environment -> INCOMPLETE -> no terminal tag -> unchanged
candidate may retry -> changed candidate cannot inherit the incomplete run as
terminal evidence.

### 9.6 Exact integrated-candidate validation

Construct a prelim candidate by combining an already accepted task with the
current parent.  Prove the resulting SHA cannot inherit task-candidate ART,
AIT, or MIT evidence merely because the task was accepted.  Run required ART
and AIT against the integrated SHA and require MIT again when the declared
acceptance contract applies to the integrated result.  Verify complete local
evidence is reusable for the exact prelim SHA and that the server runs missing
automated ART/AIT rather than asking the user to run them.

### 9.7 Main advances during integration

Run the A/B/B'/C reintegration scenario from Stage 4 end to end, including
server rejection of stale B' and successful fresh validation of C.

### 9.8 Concurrent workers

Two accepted tasks begin separate integration attempts against the same remote.
Verify unique GUID branches, no ref collision, no cross-worker cleanup, and
correct stale handling when one lands first.

### 9.9 Squash integration and evidence retention

Land an integration using squash semantics, clean up the prelim branch, and
prove the PRELIM tag still reaches the exact tested pre-squash candidate while
the stable tag identifies the final server-main release commit.

### 9.10 Guard/bypass defence in depth

Demonstrate that an operation blocked locally is also rejected at the server
boundary when local hooks are absent or bypassed, for every remotely enforceable
critical invariant.

## 10. Stage completion gates

An implementation stage is complete only when:

- its documented positive and negative tests exist;
- all tests for that stage pass;
- previously completed stage tests still pass;
- failure paths leave repository state consistent;
- the test suite leaves its own repositories/worktrees clean;
- required Linux/Windows coverage is GREEN where applicable;
- required hosted/server checks are GREEN or an explicit external capability
  dependency is documented;
- no behaviour that requires user manual acceptance remains unless the
  lifecycle specification explicitly identifies it as a user decision rather
  than a test.

The final RWF lifecycle is certifiable only when the complete Stage 7 system
suite passes in addition to all lower-level tests.

## 11. Regression rule for future changes

Every defect found in RepoWorkflow must receive a regression test that fails
for the defect before or alongside the fix and passes afterward.

Every new lifecycle invariant must identify its test level and stage.  Changes
to `WORKFLOW_LIFECYCLE.md` that introduce testable behaviour must update this
test strategy in the same work so implementation requirements and test
requirements cannot drift apart.
