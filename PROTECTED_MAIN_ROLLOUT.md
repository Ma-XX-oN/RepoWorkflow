# Protected-main rollout and verification

Status: draft operator acceptance checklist for #85 and #542.  This document
does not configure GitHub or authorize a merge.

## Current observed blockade (2026-10-09)

- `main` at `f2c5378af11cb6de966b65bad135fe2e1ff5515d`.
- GitHub branch snapshot: `protected=false`; repository rulesets: none.
- Connected GitHub App gets HTTP 403 reading main protection.
- No check run with context `repo-workflow/exact-candidate` was returned
  for the inspected main and #603 PR commits.
- Existing GitHub PR merge guard in draft #546 requires that exact check,
  strict status checks, admin enforcement, PR review and no force/delete.
- Draft #603 rechecks the destination after validation, but a client-side
  reread cannot make an unprotected merge atomic.

These observations must be refreshed immediately before rollout.  They are
not a claim about future configuration or a different repository.

## Order of operations

1. Finish and review #81/#119 host adapter and #69/#104 exact-candidate
   evidence gates.  A caller-supplied success boolean is not proof.
2. Establish a trusted CI/service identity that actually publishes the
   `repo-workflow/exact-candidate` check against the precise candidate
   SHA.  Refuse incomplete/forged/outdated evidence and a changed target.
3. Demonstrate that the check appears on GitHub as a real check run for
   a test PR, with success and failure observations bound to run identity.
   Do not add it as required until the publisher exists and is audited.
4. Using an authorized repository administrator or properly permissioned
   GitHub App, configure a protected-main branch rule/ruleset requiring
   PR review, strict current-base checks and that trusted required check.
   Apply enforcement to administrators; reject force pushes and deletions.
5. Read back the authoritative server policy with an independently
   authorized identity.  Do not treat a UI click or local config file as
   evidence that GitHub enforces the rule.
6. Test direct push, forced update, deletion, PR without passing check,
   stale target after another actor's merge, changed PR head, and
   unauthorized bypass.  All must be refused by GitHub itself.
7. Verify a fully eligible exact-source PR can be accepted through the
   controlled path, and that the terminal server merge commit and
   post-merge validation are traceable to the approved candidate.
8. Recheck branch protection and required checks on the exact destination
   immediately before production workflow cutover.

## Failure and evidence requirements

If an administrative API responds 403, required check is absent, status is
ambiguous, provider evidence cannot be authenticated, or a bypass succeeds,
mark this gate BLOCKED.  Do not claim a GREEN local merge-guard unit test
proves protected-main enforcement.

Retain immutable experiment records with Problem, Hypothesis, Action and
Learning.  Include repository/branch/candidate SHA, expected/current base,
provider run/check identifiers, policy snapshot, refusal/success outcome,
actor permission level and exact test revision.

## Ownership

#104 decides provider-neutral candidate eligibility.  #69 supplies durable
evidence; #548 authenticates hosted evidence.  #542 checks live destination
freshness.  #85 owns actual GitHub enforcement, and #543 closes the final
replacement CLI and integration certification.  Deferred actor-role work
under #548 must not be silently declared complete.
