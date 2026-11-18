# Workflow in a Nutshell

## Files

RWF uses the following repository files and worktree-local files.

```text
<repository>/
└── .rwf/
    ├── tickets.csv
    ├── repo/
    │   ├── version
    │   ├── info
    │   ├── ci
    │   ├── host
    │   └── contact
    └── ci/
        ├── tests-permanent.json
        ├── tests-temporary.json
        ├── tests-temporary/
        ├── testers.txt
        ├── MIT-timeout.txt
        ├── rwf
        ├── cmd-results.txt
        └── test-results/
            └── <id-range>/<issue>.jsonl

<worktree-git-dir>/
└── rwf/
    └── last-paused.txt
```

`<worktree-git-dir>` is the directory returned by Git for this checkout's
administrative files: normally `.git`, or the associated worktree Git directory
for a linked worktree. These local files are not committed or shared between
worktrees. A worker operating directly through the Git host does not require them.

| File | Purpose |
| --- | --- |
| `.rwf/tickets.csv` | Ticket number, title, state, dependencies and one claimant identity field: `<user>[;<agent-name>;<chat-id>[;<session-id>]]`. The user is the person under whom the AI is working. |
| `.rwf/ci/tests-permanent.json` | Catalogue of retained tests, including regression, automatic integration and manual integration tests. RED/GREEN selection uses the catalogue; it does not require a second permanent catalogue. |
| `.rwf/ci/tests-temporary.json` | Catalogue of temporary development tests. |
| `.rwf/ci/tests-temporary/` | Temporary test files. `done` removes the completing ticket's files and catalogue entries after successful testing. |
| `.rwf/ci/testers.txt` | Accepted tester identities. Everyone is currently trusted; the list is not enforced. |
| `.rwf/ci/MIT-timeout.txt` | Merge-slot wait in `[[h:]m:]s` format. Absent or empty means zero. Zero releases the CI slot immediately while MIT remains outstanding; local execution returns to the MIT prompt. Timeout is not test failure. |
| `.rwf/ci/rwf` | Arguments for the RWF command submitted to CI on a CMD branch. |
| `.rwf/ci/cmd-results.txt` | Output/result of that CI command on its CMD branch. |
| `.rwf/ci/test-results/<id-range>/<issue>.jsonl` | Append-only test results, one file per ticket, in ranges of 1,000 issue numbers. |
| `<worktree-git-dir>/rwf/last-paused.txt` | Line stack of arguments for `rwf resume <ticket-id> [addendum]`. Pause appends an entry after successfully checkpointing work. Argumentless resume uses the last entry and removes it only after successful resume. Explicit resume removes its matching entry while preserving the others. |

Each test-result record includes `"source": "<ticket-id>[-addendum]"`, tester
identity and the information needed to determine which test, source and
environment it applies to. Copying results preserves their source. Integration
preserves existing records and appends new records from both sides through
RWF's append-aware reconciliation, rather than ordinary text merging.

The current ticket is derived from the current RWF branch name. There is no
`current-ticket.txt` or separate persisted current-ticket selection.

### Ticket claims

```text
rwf start <ticket-id> [addendum] [--user <user>] [--agent <agent-name> <chat-id> [<session-id>]]
```

Start records the invoking user and any supplied AI identity in one CSV field
on the ticket's row. The field has the form
`<user>[;<agent-name>;<chat-id>[;<session-id>]]`; the preceding comma separates
this field from the other CSV fields. Agent name and chat ID are supplied
together; session ID is optional. Without AI arguments, the identity is the
user alone. Use normal CSV quoting when required by the field contents.

This complete field is the claimant identity. It identifies both the user and
the AI acting for that user; agent/chat/session values are not separate claim
columns.

Use `--user <user>` when supplied; otherwise resolve the user with
`git config --get user.name` in the target repository. If no nonblank user is
available, `start` errors before creating the branch or changing the claim.
Host-only callers supply `--user` and any `--agent` arguments through `start`;
RWF writes the claimant identity into `.rwf/tickets.csv`. The identity is that
of the implementing user and agent, rather than the CI runner executing the
request.

The normal prescribed issue branch is the claim boundary. A worker checks the
claim, records this identity in that branch's `tickets.csv`,
and publishes the branch using atomic create-if-absent semantics. Competing
creation of the same branch must not overwrite the winner. Updates to an
existing claim use its expected previous branch tip. An existing claim by
another worker requires explicit instruction to reclaim it.

An addendum is an explicitly justified replacement implementation, not an
ordinary parallel claim or an automatic workaround for an existing claim.
The superseded implementation must stop progressing and must not reach `done`.
The optional addendum precedes the options; AI identity arguments follow
`--agent`.

Lane selection, lane settings/diagnostics and workspace registry/claim files
are excluded from this simplified workflow. There is no separate workflow
`state.json`, PRELIM checkpoint store or engine-version file. Additional
persistent information requires a specific workflow purpose and must not
duplicate information available from Git or the existing files.

## Initialisation

### Repository adapter scripts

RWF calls repository-owned scripts in `.rwf/repo/` for
repository/provider-specific work:

| Script | Responsibility |
| --- | --- |
| `.rwf/repo/version` | Read and change the repository version through its defined API. Own the version storage details. See [REPO_VERSION_ADAPTER.md](REPO_VERSION_ADAPTER.md). |
| `.rwf/repo/info` | Read repository and ticket information. See [REPO_INFO_CONTRACT.md](REPO_INFO_CONTRACT.md). |
| `.rwf/repo/ci` | CI execution, runner/environment setup and result/artifact transport. See [PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md#repo-ci). |
| `.rwf/repo/host` | Repository-host mutations, including conditional ref updates and ticket operations. See [REPOSITORY_HOST_MUTATION_CONTRACT.md](REPOSITORY_HOST_MUTATION_CONTRACT.md). |
| `.rwf/repo/contact` | Deliver notifications to the implementing user or assigned manual tester using email or another contact mechanism. Recipient resolution and delivery belong here. Its exact invocation contract remains to be defined. |

RWF supplies the notification's recipient context and message to
`.rwf/repo/contact`. References to email below mean notification through this
adapter. Repository initialization follows:

```
<user> <system> <repo-dir> (<git-branch>)
$ repoworkflow/rwf init  # initialises RWF files.  Will state how to init for current shell.
To initialise the rwf command for bash, execute this command:

  source <(repoworkflow/rwf init bash)

<user> <system> <repo-dir> (<git-branch>)
$ source <(repoworkflow/rwf init bash)  # initialises auto selection of rwf command and tab completion

<user> <system> <repo-dir> RWF (<git-branch>)
$ 
```

`<user> <system> <repo-dir>` is the regular bash prompt. `(<git-branch>)` is
from git's prompt setup.  RWF doesn't have to do anything with those.

The first part initiates the state of the repo in terms of RWF.  That sets up
the skeleton set of files for the repo.

The second part allows calling the rwf command anywhere in the main repo.
So if `rwf` is called from within `<repo-dir>/some/path`, it'll still call
`<repo-dir>/repoworkflow/rwf`.

The `RWF` in the prompt shows that the bash hooks are active.

## Typical Workflow

```
<user> <system> <repo-dir> RWF (<git-branch>)
$ rwf start <ticket-id> [addendum] [--user <user>] [--agent <agent-name> <chat-id> [<session-id>]]

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # branch made from <git-branch>

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # agent creates the RED tests (optional) and adds 
  # `issue-<ticket>-<regression-test-name>`and/or
  # `issue-<ticket>-[manual--]<integration-test-name>` to test catalogue and/or
  # `issue-<ticket>-[temp--]<integration-test-name>` to temp test catalogue.

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test RED issue-<ticket-id>-<regression-test-name> # must fail

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # agent implements task

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test GREEN # must succeed, if not go back to "agent implements task"

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test regression [particular-test-ids...] # optional.  If not done, will be done on DONE.

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test integration [particular-test-ids...] # optional.  If not done, will be done on DONE.

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ git push

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf done --remote

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf parent

<user> <system> <repo-dir> RWF (<git-branch>)
$ # back at starting branch
```

## Done

Run all required automatic tests before bringing manual testers into the loop.

Completion runs the ticket's temporary tests as well as the other required
tests, reusing applicable results where available. After successful testing,
`done` removes that ticket's temporary test files from
`.rwf/ci/tests-temporary/` and their entries from
`.rwf/ci/tests-temporary.json`, and records the cleanup in Git before merging
into the parent. Preserve the JSONL test results. Do not remove another ticket's
temporary tests. Failed or unfinished testing leaves the tests available for
repair and retry; when testing is deferred to the server, cleanup is deferred
with it. Cleanup must not silently reuse evidence invalidated by changes to
the remaining test inputs.

`rwf done` should create the PRELIM branch
`PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>]`, retaining the version already
prepared through testing. Before the ticket's first test, initialize `Q=0, R=0`,
including when `done` initiates that first test. Subsequent preparation follows
the source-change and parent-reintegration increment rules rather than
reinitializing the counters. If moving to tip of parent
fails, agent is signalled by email.  So that they can pull the repo, fix the
merge on the latest `PRELIM-issue-<ticket-id>.Q.R-<title>[-addendum]`,
optionally test it, push it and then run `rwf done --remote` to have remaining
tests to be executed.

Be aware that there should be a space where if the agent isn't part of a group
which is trusted with tests, then those test results will not be used as part of
validation.  For now, we are assuming everyone is trusted.

If remaining tests done on server show failure, the agent will be contacted by
email, or the agent can look at the test results using `rwf test results
issue-<ticket-id> [--remote [--poll [<seconds> ...]]]`.  Without `--remote` it
reports the local test results.  On test failure, just like merge failure, agent
will edit the latest `PRELIM-issue-<ticket-id>.Q.R-<title>[-addendum]`, push it
and then submit `rwf done --remote`.

I'm thinking that it might be a good idea to have a `rwf fix <ticket-id>
[addendum]` so that it's easier to come back to the branch. E.g.

```
<user> <system> <repo-dir> RWF (<git-branch>)
$ git pull

<user> <system> <repo-dir> RWF (<git-branch>)
$ rwf fix <ticket-id> [addendum]

<user> <system> <repo-dir> RWF (PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>])
$ # P.Q are the latest ones.

<user> <system> <repo-dir> RWF (PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>])
$ rwf test results  # optionally look at the test results locally.

<user> <system> <repo-dir> RWF (PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>])
$ # do fixes.

<user> <system> <repo-dir> RWF (PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>])
$ git push

<user> <system> <repo-dir> RWF (PRELIM-issue-<ticket-id>.Q.R-<title>[-<addendum>])
$ rwf done --remote
```

Note that `<repo-dir>` can be any directory within the repo's directory.

An agent authorised to merge into the local parent can use `rwf done` offline
instead of `git push` followed by `rwf done --remote`.

For both local and remote completion, `done` checks the ticket's state in
`.rwf/tickets.csv` at destination parent tip A. If the ticket is already
completed, report an error and stop. Otherwise continue normally, preparing
and testing candidate C against A.
Update the parent only if it still points to A. Locally, Git
provides this atomic check and update through `git update-ref
refs/heads/<parent> <C> <A>`; remote completion requires the equivalent
conditional destination update. If another integration advances the parent,
recheck the destination ticket state, reconstruct against its new tip and rerun
the invalidated tests before retrying.
Never merge first and roll back afterward. Local completion must also respect
any worktree using the parent: a ref update alone does not update that
worktree's index or files.

After required testing passes, record the ticket as completed in
`.rwf/tickets.csv` and commit that update before merging to parent. This
completion-record update preserves the applicable test results. After the
conditional parent update succeeds, create the success version tag on the
integrated commit containing the completed-ticket record and test evidence.
The order is: test, commit completion, merge, then tag.

After successful integration, synchronize completion with the ticket system
and retire the processed PRELIM branch.
Retain test evidence in repository history. Offline execution reports local
integration completed and ticket-system synchronization outstanding; synchronize
when connectivity returns. Report any unfinished tag creation or PRELIM
retirement explicitly. Retrying these finishing steps must not merge the ticket
again.

## Remote Commands

Remote-capable commands can take `--remote [--poll <seconds> ...]` which updates the
`.rwf/ci/rwf` file, which triggers a CI action.  The `.rwf/ci/rwf` file contains the
parameters to `rwf` and adds a `n` item to the `--remote` switch.  E.g. `rwf
<some-command> --remote [--poll <seconds> ...]` will result in `.rwf/ci/rwf` to
contain `<some-command> --remote n [--poll <seconds> ...]`, where `n` is the
retry number starting at `0`.

`--poll` checks immediately and then waits between status checks. Supplied
seconds are successive delays: `--poll 5 15 60` waits 5 seconds, then 15,
then repeats 60-second delays until completion. With no numbers, `--poll`
uses 15-second delays. Without `--poll`, submission returns without waiting.
These delays are separate from the manual-test merge-slot timeout.

`parent`, `resume`, `fix`, `pause`, and shell activation are local-only.
They reject `--remote` with an explanation that the operation acts on the
caller's local checkout or shell. Their help and tab completion do not offer
`--remote` or its dependent polling options. The commands remain available locally.

All remote commands are put in a CMD branch off of the branch to execute from.
The command is executed from the parent branch.  The CMD branch must be
branching off the tip of the parent.  Any results are stored in
`.rwf/ci/cmd-results.txt` in that CMD branch.  The execution of a CMD may result in
mutation of that branch, which is why the CMD branch MUST be rooted to the tip
of the parent branch.  The CMD branch is named
`CMD-<cmd-number>-issue-<ticket-id>.Q.R-<title>[-addendum]`.

## Testing

Tests are declared in `.rwf/ci/tests-permanent.json` or
`.rwf/ci/tests-temporary.json`. The catalogues determine which tests exist and
which regression, automatic integration or manual integration selection they
belong to. RED/GREEN is a development use of regression tests, not a separate
test category or catalogue.

Tests may run individually or in groups, locally or through supported remote
commands. Applicable results already recorded for the same source, test inputs
and environment can be reused. Required tests without applicable passing
results remain outstanding and are run during completion, including on the
server when deferred. An applicable failure prevents merge.

Results are appended to `.rwf/ci/test-results/<id-range>/<issue>.jsonl`, with
the originating `source`, tester identity, tested source and relevant test and
environment information. Remaining tests and outcomes are determined from the
catalogues and these logs, without a separate pending-results file. AIs are
trusted for now. `.rwf/ci/testers.txt` describes accepted testers when that
policy is applied; ticket ownership and test-result attribution remain distinct.

### Temporary Tests

Temporary tests support development or diagnosis and are registered in
`.rwf/ci/tests-temporary.json`. Their files live in
`.rwf/ci/tests-temporary/`. Run them with `rwf test temporary`.
`done` owns their removal after successful testing, as described under
[Done](#done). Permanent regression tests belong in their permanent location
and catalogue from creation; they must not be placed in the temporary directory.
Cleanup deletes the temporary tests but preserves their JSONL evidence. Their
source remains reviewable in the ticket branch's Git history before cleanup.

### Regression Tests

Regression tests check required behavior and protect it against later changes.
Register retained tests in `.rwf/ci/tests-permanent.json`.

Each ticket should define one focused RED/GREEN regression test. Needing
multiple independent tests is a reason to revisit ticket decomposition;
combining independent tests inside one test to disguise that need is not
acceptable. Existing required regression and integration coverage still runs.

The optional RED/GREEN development sequence is:

1. Write and register the regression test for the intended behavior.
2. Run `rwf test RED issue-<ticket-id>-<regression-test-name>` before the
   implementation. Confirm the expected failure, rather than a runner error.
3. Implement the change.
4. Run `rwf test GREEN` to rerun the remembered selection without retyping its
   name. Fix the implementation until the selected tests pass.

Skipping RED/GREEN does not exempt any required test from final validation.
The same retained tests participate in regression testing afterward.
`rwf test regression [particular-test-ids...]` runs the selected regression
tests, or the full regression selection when IDs are omitted. Partial passing
runs can collectively satisfy coverage when their evidence remains applicable.

### Integration Tests

If doing integration testing and there are manual tests, then it should look like this:

```
<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test integration [--manual|particular-test-ids...]

# Runs integration tests.  On running a manual test, will wait for completion.
# A is the current number of manual tests already reported succeeded or failed.
# B is the total number of manual tests to be done.

<user> <system> <repo-dir> RWF MIT A/B (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test [succeeded|failed]
```

Also tests default to stop on first failure.  Can specify flag `rwf test
--cont-on-fail (regression|integration)
[particular-test-ids]` to run them all, regardless of successfulness.

Manual integration tests are named `issue-<ticket-id>-manual--<description>`.

To only run the automated integration tests, do the following:

```
<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test integration --automatic
```

Counting the tests can be done by:

```
<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test integration [--manual|--automatic|particular-test-ids...] --count
```

Remote `done` completes all required automatic tests before emailing the manual
tester. The merge slot waits for manual results for the duration configured in
`.rwf/ci/MIT-timeout.txt`, using `[[h:]m:]s`: `45` is 45 seconds, `2:30` is
2 minutes 30 seconds, and `1:02:30` is 1 hour 2 minutes 30 seconds. On expiry,
release the slot so other submissions progress. Keep this submission queued
and unmerged until its required manual results pass; timeout is not test failure.

An absent or empty timeout file defaults to `0`. In CI, zero releases the merge
slot without waiting while preserving the outstanding manual-test obligation.
For local execution outside CI, return to the `[MIT A/B]` shell prompt so the
tester can perform and report the manual tests.

## Pausing a Ticket

This is similar to git stash.

```
<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf pause [--save-untracked [specific-files...]] # save all untracked if no specific-files specified.

<user> <system> <repo-dir> RWF (parent-branch)
$ # do what needs to be done

<user> <system> <repo-dir> RWF (parent-branch)
$ rwf resume [<ticket-id> [<addendum>]] # if ticket id isn't specified, resume last paused.

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # back to where you were.
```

There will be a `<worktree-git-dir>/rwf/last-paused.txt` file to store the last paused
parameters used to restore the last paused.  E.g. `[<ticket-id> [<addendum>]]`.


I think an explicit `resume` is better than overloading `start`.  `start` should
fail if the branch already exists. `resume` should fail if no branch to resume.

## Tests and Versioning

Tests can run individually or as a group. Initialize `Q=0, R=0` before the
ticket's first test. Before testing a changed implementation, increment Q once
and reset R to zero. Reintegrating unchanged implementation against a newer
parent increments R. If both change, increment Q and reset R to zero.
Additional tests, unchanged retries and test-log-only commits reuse the
prepared version without incrementing either counter.

The test results are committed in the repo under
`.rwf/ci/test-results/<id-range>/<issue>.jsonl`.  The `<id-range>` is to prevent
overfilling a directory with files causing performance issues and/or failures.
Each range spans 1,000 issue numbers: `0-999`, `1000-1999`, and so on.
For example, issue 109 uses `0-999/109.jsonl`.

Each JSONL test-result record contains `"source": "<ticket-id>[-addendum]"`,
identifying the originating ticket and optional addendum. This remains the
same when its results are copied or integrated into another branch.

On test failure, record the failure tag `v<version>-CI-FAIL`.
Create the success tag `v<version>` after successful integration, following
the test, completion commit, merge and tag order under [Done](#done).
Version preparation changes version data through `.rwf/repo/version`; it must
not change implementation code. Recording completion and creating the tag do
not require repeating tests for the unchanged implementation.
