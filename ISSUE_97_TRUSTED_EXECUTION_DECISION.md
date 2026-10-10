# Issue #97 — Minimum Trusted Execution Decision

Decision date: 2026-10-10.  Issue #97 OPEN, PR #616 DRAFT.
Do not merge and do not claim provider write acceptance without evidence.

## What the #80 contract actually requires

`AUTHORIZATION_EVIDENCE_CONTRACT.md` requires a trusted issuer with
authenticated delegation, verified actor, explicit role and capability,
exact scope, trusted time, active policy revision and current revocation
state.  The adapter must refuse unsupported one-time/consuming grants:
a successful one-time grant requires atomic consumption and recovery.
Issue #97's current consumer requests only independently authenticated,
non-consuming standing policy.  This is an intentional limited scope.

#80 does NOT require a dedicated machine, external network service,
specific verifier programming language or GitHub App private key.
The existing Python consumer DOES require an executable verifier path
outside its own checkout; a copied, pinned, independently controlled
artifact meets that path separation without a self-hosted runner.

A GitHub environment reviewer approves execution, NOT the issuer's
grant; an exact SHA does not prove actor, delegation, expiry or
revocation.  A GitHub write token proves provider authentication but
not semantic authorization.

## Architecture comparison

| Option | Privilege and independence | Cost / limitation |
| --- | --- | --- |
| A. GitHub-hosted within RepoWorkflow | Protected environment plus | Native token cannot |
| | separate sandbox-only credential | write another repo |
| B. GitHub-hosted with App token | App installed only in sandbox, | App/key configuration |
| | ephemeral installation token | and extra secret |
| C. Dedicated self-hosted | Independently installed verifier | Extra machine; public |
| | and separately scoped credential | repository runner risk |
| D. GitHub-hosted within sandbox | Native sandbox-only token, | Requires disposable repo, |
| | protected main workflow and grant | trusted policy and reviewer |

**Selected D**: GitHub-hosted Ubuntu runner within the disposable sandbox,
not a dedicated runner.  It uses only the sandbox's job-scoped
`GITHUB_TOKEN`; permissions: Actions read, Contents write, Issues write,
Pull requests write.  This is narrower in repository reach than A or B.
Options A and B are viable fallbacks, not requirements.  C has no
contract-mandated capability advantage and adds persistent runner risk.

## Runtime trust boundaries for selected D

1. Sandbox `main` holds the *trusted* workflow and verifier code behind
   enforced branch rules and independent review.  Neither is fetched
   from the issue #97 pull request.
2. The `rwf97-acceptance` environment enforces independent approval,
   prevent-self-review and exact deployment from `main`.
3. After approval the job checks its trusted commit, separately
   administrator-pinned verifier SHA-256 and independently approved
   exact RepoWorkflow candidate SHA.  The candidate checkout is
   separate and never controls the workflow YAML.
4. The verifier is copied from the protected sandbox checkout to
   `RUNNER_TEMP/rwf97-trusted`, outside the adapter checkout.  It must
   authenticate a current #80 standing grant using an independent
   issuer/delegation proof and trusted authoritative revocation source
   at each mutation.  Unknown or stale authority denies.
5. The GitHub token is minted for the sandbox job only and expires
   automatically.  The Python backend resolves its authenticated actor
   with GitHub; the #80 verifier decision must match that actor.
6. The sandbox default branch and `rwf-host-request-*` ref ruleset
   prevent the test token from altering main or existing reservations.
   The candidate still receives a sandbox write token: independently
   reviewing its exact SHA and trusted workflow is essential.
7. No one-time grant consumption is attempted; the verifier denies
   `max_uses != null`.  Standing policy is not a shortcut for a
   one-time grant or remote finalizer privileges.
8. The Python adapter never merges PRs or publishes success checks.
   Source and target are dedicated non-main sandbox branches and the
   issue is explicitly marked disposable.

## Missing authority is still real, but smaller than a runner

#80 completed documentation and an acceptance matrix.  We have not
found a deployed verifier or an independently issued, authenticated,
currently revocable standing policy.  A separate network service is
NOT required if the verifier on sandbox protected `main` can read and
validate current independently issued immutable grants and revocation
facts itself, with trusted issuer authentication.

Neither a new mock `allow` script nor GitHub deployment approval may
manufacture that grant.  Provisioning this scoped #80 authority and
validating its denial cases is the remaining genuine authorization
work, besides creating the disposable sandbox and protected environment.
No new DAG ticket was created.

## Implementation and acceptance links

`examples/issue-97-sandbox-hosted.workflow.yml` is the sandbox-owned
workflow template.  Its protected-environment guard is
`examples/issue-97-sandbox-verify-environment.py`.
`ISSUE_97_LIVE_ACCEPTANCE_SETUP.md` gives precise GitHub UI steps.
`scripts/probe-repo-host-github.py` executes the shipped adapter and
independently validates issue/PR/comment and Git reservation evidence.

A completed sandbox run must prove real write authority, exact-provider
persistence, retries after process restart, racing operations, cleanup,
permission and authorization negatives, including expiry and revocation.
Until then #97 remains OPEN and PR #616 remains DRAFT.
