# Workflow in a Nutshell

## Initialisation

```
<user> <system> <repo-dir> (<git-branch>)
$ repoworkflow/rwf init  # initialises RWF files.  Will state how to init for current shell.
To initialise the rwf command for bash, execute this command:

  source <(rwf init bash)

<user> <system> <repo-dir> (<git-branch>)
$ source <(rwf init bash)  # initialises auto selection of rwf command and tab completion

<user> <system> <repo-dir> RWF (<git-branch>)
$ 
```

`(<git-branch>)` is from git's prompt setup.  RWF doesn't have to do anything for that.

The first part initiates the state of the repo in terms of RWF.  That sets up the skeleton set of files for the repo.

The second part allows calling the rwf command anywhere in the main repo.  
So if I call it in `<repo-dir>/some/path`, it'll still call
`<repo-dir>/repoworkflow/rwf`.

The `RWF` in the prompt shows that the bash hooks are active.

## General Workflow

```
<user> <system> <repo-dir> RWF (<git-branch>)
$ rwf start <ticket-id> [addendum]

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # branch made from <git-branch>

<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ # agent creates the RED tests (optional) and adds 
  # `issue-<ticket>-<regression-test-name>`and/or
  # `issue-<ticket>-[manual--]<integration-test-name>` to test catalogue and/or
  # `issue-<ticket>-[-temp-]<integration-test-name>` to temp test catalogue.

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

`rwf done` should create the PRELIM branch
`PRELIM-issue-<ticket-id>.0.0-<title>[-<addendum>]`. If moving to tip of parent
fails, agent is signalled by email.  So that they can pull the repo, fix the
merge on the latest `PRELIM-issue-<ticket-id>.Q.R-<title>[-addendum]`,
optionally test it, push it and then run `rwf done --remote` to have remaining
tests to be executed.

Be aware that there should be a space where if the agent isn't part of a group
which is trusted with tests, that those tests will not be used as part of
validation.

If remaining tests done on server show failure, the agent will be contacted by
email, or the agent can look at the test results using `rwf test results
issue-<ticket-id> [--remote [--poll [<seconds> ...]]]`.  Without `--remote` it
reports the local test results.  On test failure, just like merge failure, agent
will edit the latest `PRELIM-issue-<ticket-id>.Q.R-<title>[-addendum]` and push
it.

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

For both local and remote completion, prepare and test candidate C against
parent tip A. Update the parent only if it still points to A. Locally, Git
provides this atomic check and update through `git update-ref
refs/heads/<parent> <C> <A>`; remote completion requires the equivalent
conditional destination update. If another integration advances the parent,
reconstruct against its new tip and rerun the invalidated tests before retrying.
Never merge first and roll back afterward. Local completion must also respect
any worktree using the parent: a ref update alone does not update that
worktree's index or files.

`.repoworkflow/tickets.csv` is updated before merging to parent.

## Remote Commands

All commands can take `--remote [--poll <seconds> ...]` which updates the
`.ci/rwf` file, which triggers a CI action.  The `.ci/rwf` file contains the
parameters to `rwf` and adds a `n` item to the `--remote` switch.  E.g. `rwf
<some-command> --remote [--poll <seconds> ...]` will result in `.ci/rwf` to
contain `<some-command> --remote n [--poll <seconds> ...]`, where `n` is the
retry number starting at `0`.

All remote commands are put in a CMD branch off of the branch to execute from.
The command is executed from the parent branch.  The CMD branch must be
branching off the tip of the parent.  Any results are stored in
`.ci/cmd-results.txt` in that CMD branch.  The execution of a CMD may result in
mutation of that branch, which is why the CMD branch MUST be rooted to the tip
of the parent branch.  The CMD branch is named
`CMD-<cmd-number>-issue-<ticket-id>.Q.R-<title>[-addendum]`.

## Integration Tests

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
$ rwf test integration --AITs
```

Counting the tests can be done by:

```
<user> <system> <repo-dir> RWF (issue-<ticket-id>-<title>[-<addendum>])
$ rwf test integration [--manual|--automatic|particular-test-ids...] --count
```

When doing a remote done, if there are MITs, then an email will have to be sent
to the manual tester and the PRELIM merge process is suspended until the tester
uploads test results.  If the tester doesn't do so within some duration (maybe
put that in a file `.ci/MIT-timeout.txt`), then the test is kept in the queue,
but is not waited on.

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

There will be a `.repoworkflow\last-paused.txt` file to store the last paused
parameters used to restore the last paused.  E.g. `[<ticket-id> [<addendum>]]`.


I think an explicit `resume` is better than overloading `start`.  `start` should
fail if the branch already exists. `resume` should fail if no branch to resume.

## Tests and Versioning

Tests can run individually or as a group.  If a test is executed and no previous
tests have been executed on the code head (e.g. test logs can be written to
without invalidating the code head), then the version is incremented prior to
running the tests.

The test results are committed in the repo under
`.ci/test-results/<id-range>/<test-name>.jsonl`.  The `<id-range>` is to prevent
overfilling a directory with files causing performance issues and/or failures.
Not sure what the size of a range should be.

A version tag is added to the repo after the tests, which is either the
`v<version>` on test success or the `v<version>-CI-FAIL` if any of the tests
fail.
