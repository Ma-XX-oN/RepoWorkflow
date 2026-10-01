# Server Enforcement

RepoWorkflow's local guards are early mistake-prevention.  The remote server is
the hard integration and stable-release boundary.

## Current RepoWorkflow repository state

As checked during issue #18 implementation on 2026-10-01, the repository had no
GitHub repository rulesets configured.  The connected GitHub App could list
rulesets but received `403 Resource not accessible by integration` when reading
the `main` branch-protection endpoint.  Administrative protection must therefore
be configured and verified by an account or app with repository-administration
permission; ordinary RepoWorkflow execution must not assume that it can create
or bypass those controls.

## Required `main` rules

The authoritative integration branch must enforce all of the following:

- require a pull request / controlled integration path;
- block direct pushes;
- block force pushes;
- block branch deletion;
- require the RepoWorkflow integration-admission status check;
- require the candidate to be current with authoritative `main` at integration
  time (merge queue where available, otherwise strict/current-base required
  checks);
- do not grant ordinary development users or automation an unrestricted bypass.

The integration-admission check is RepoWorkflow policy, not YAML policy.  It
must reject unless all of these facts are true for the exact proposed candidate:

1. source branch is `prelim-main`;
2. target branch is the configured integration branch;
3. candidate SHA exists;
4. current authoritative `main` is an ancestor of that candidate;
5. required validation evidence applies to that exact candidate SHA;
6. required validation passed;
7. explicit integration authorization exists.

The representation/storage of explicit integration authorization is deliberately
not defined yet by the lifecycle design.  Until that representation is agreed,
the admission layer must fail closed rather than infer authorization from a
GREEN result, completed issue, ready PR, or accepted integration test.

Likewise, durable exact-SHA local-validation publication is still blocked on the
issue #16 evidence-ownership question.  The admission check accepts an exact-SHA
validation fact, but this document does not invent where that fact is persisted.

## Required stable-tag rules

Stable release tags matching `vX.Y.Z` must be protected so ordinary development
actors cannot create, update, or delete them.  Only the controlled finalizer may
create a new stable tag, and only after RepoWorkflow verifies that:

- the checked-out commit is exactly the authoritative server `main` head;
- the repository-owned version adapter reports a plain stable semantic version;
- the corresponding stable tag does not already exist.

Existing stable tags are immutable and must never be moved or reused.

Task and PRELIM tags are also immutable workflow evidence.  Their creation path
is different from stable finalization, but update/delete operations must not be
permitted as ordinary integration behaviour.

## Stale candidate behaviour

A preliminary candidate based on server `main` at `A` is invalid for integration
once server `main` advances to `B` unless the candidate is reintegrated so `B`
is an ancestor of the new candidate.  Old GREEN evidence applies only to its
old SHA and cannot satisfy validation for the new candidate.

Guard failure is a STOP condition.  Server enforcement must reject the invalid
operation; it must not repair forward by changing versions, rewriting tags, or
merging first and diagnosing afterward.

## Required administrative verification

For each consumer repository, an administrator should verify the live GitHub
configuration after applying rules.  RepoWorkflow can test its policy engine and
inspect rulesets when permitted, but a successful test suite is not evidence
that GitHub protections are actually enabled on a particular repository.
