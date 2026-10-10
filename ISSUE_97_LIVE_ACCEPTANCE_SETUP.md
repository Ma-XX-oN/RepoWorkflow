# Issue #97 — Disposable-000 Live Acceptance Setup

Status: setup implemented; authenticated positive writes still PENDING.
Claim: 6099480122.  Existing draft PR: #616.  Never merge.

## Actual provider-confirmed state (2026-10-10)

Sandbox: https://github.com/Ma-XX-oN/Disposable-000
Visibility: PRIVATE.  Admin rights verified through connected GitHub.
Default branch: main; no #97 adapter writes permitted there.
Issue: #1, open, exact title `RWF #97 SANDBOX live-mutation fixture`.
Branches: `rwf97-sandbox-source`, `rwf97-sandbox-target`, distinct
commits.  Source SHA: `9bf44e1aaac2e49fe26949df3369c4fc10b462fc`.
Draft PR #2: created, updated, then closed UNMERGED as fixture test.

- Read-only private Actions probe completed:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38093124379
  The actual environment list returned `total_count: 0`.
- Actual Python adapter denial verification completed:
  https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38093785174
  It exercised all six operations.  Four were unauthorized and two
  unsupported; remote before/after GitHub state was unchanged.
- GitHub REST Rulesets API returned HTTP 403 with
  "Upgrade to GitHub Pro or make this repository public to enable
  this feature."  Keep the sandbox PRIVATE unless user says otherwise.
- GitHub Free/Pro/Team required deployment reviewers are for PUBLIC
  repositories.  Upgrading only to Pro would NOT provide independent
  required environment reviewers on this private repository.
- DO NOT purchase Enterprise or make the sandbox public solely to run
  this isolated test.  The selected trust boundary is an OFFLINE-signed
  #80 grant plus administrator-controlled GitHub Actions variables.

## Already installed; no dedicated runner or App key

Sandbox's trusted main contains:

- `.github/workflows/issue-97-sandbox-acceptance.yml`;
- `trusted/rwf97/verify-authority`;
- `trusted/rwf97/verify-environment.py` (optional richer plan);
- `.github/workflows/rwf97-capability-audit.yml`;
- `ACCEPTANCE.md` with fixture/provider observations.

PR #616 ships the candidate adapter, live provider acceptance probe,
the offline issuer script and the test-only Ed25519 verifier.
The sandbox workflow uses `ubuntu-latest` and its own short-lived
`GITHUB_TOKEN` with `actions:read`, `contents:write`,
`issues:write`, and `pull-requests:write`; that token is scoped
to Disposable-000 and cannot write RepoWorkflow main.

## Minimum administrator action — no credentials in ChatGPT

The person issuing the #80 grant must independently review BOTH the
sandbox-main trusted workflow/verifier and the exact final PR #616
candidate commit.  A SHA match does not replace substantive review.
Keep the signing private key OFFLINE, not in GitHub or in this chat.

1. On your own trusted computer, obtain/review
   `examples/issue-97-admin-sign-authority.py` from PR #616.
   With Python 3.13 and `cryptography==45.0.7` installed, run:

   ```sh
   python examples/issue-97-admin-sign-authority.py generate-key \
     --private-key rwf97-issuer.pem
   ```

   It creates a private Ed25519 PEM (mode 0600) and a public
   `rwf97-issuer.public.b64`.  Never commit the PEM.

2. After choosing the exact final tested #616 candidate SHA, issue
   a 2-hour SANDBOX-only non-consuming CI grant:

   ```sh
   python examples/issue-97-admin-sign-authority.py issue \
     --private-key rwf97-issuer.pem \
     --issuer-id rwf97-independent-issuer \
     --candidate-sha FULL_FINAL_PR_616_SHA \
     --source-sha 9bf44e1aaac2e49fe26949df3369c4fc10b462fc \
     --issue 1 --hours 2 --output signed-rwf97
   ```

   This produces only signed non-secret documents `grant.json` and
   `revocations.json` plus a grant ID printed by the issuer tool.
   Publish the signed JSON through reviewed commits to the sandbox's
   `trusted/rwf97/` directory on main.  Do not alter signatures.

3. Open sandbox Settings -> Secrets and variables -> Actions ->
   Variables:
   https://github.com/Ma-XX-oN/Disposable-000/settings/variables/actions

   Create/update these repository variables, controlled by GitHub
   administration rather than by the job's native GITHUB_TOKEN:

   | Variable | Exact required source |
   | --- | --- |
   | RWF97_ENABLE | `true` ONLY for approved execution |
   | RWF97_APPROVED_SHA | Exact tested final PR #616 head SHA |
   | RWF97_TRUSTED_MAIN_SHA | Sandbox main HEAD AFTER signed files |
   | RWF97_VERIFIER_SHA256 | SHA-256 of trusted verifier file bytes |
   | RWF97_ISSUER_AUTHORITY | `rwf97-independent-issuer` |
   | RWF97_ISSUER_PUBLIC_KEY | Public .b64 file, single line |
   | RWF97_APPROVED_GRANT_ID | Exact issuer-printed grant ID |
   | RWF97_SIGNED_REVOCATIONS | Full signed JSON, one line |
   | RWF97_SANDBOX_ISSUE | `1` |
   | RWF97_SANDBOX_SOURCE_REF | `refs/heads/rwf97-sandbox-source` |
   | RWF97_SANDBOX_TARGET_REF | `refs/heads/rwf97-sandbox-target` |

   The trusted verifier SHA-256 is printed by the read-only
   sandbox capability audit job after checkout.  Re-run that safe
   audit on main if the verifier file changes.  Ensure final
   `RWF97_TRUSTED_MAIN_SHA` matches the reviewed workflow commit.

4. Open sandbox -> Actions, select
   `Issue 97 sandbox-hosted Python adapter acceptance`, choose
   `Run workflow` on `main`.  The job must reject a changed trusted
   main SHA, candidate SHA, unsigned policy, missing issuer key,
   changed grant ID or mismatched revocation mirror before any write.

5. Confirm the actual GitHub issue/comment/PR state and immutable
   reservation tags/commit messages after provider execution.
   Prove replay, fresh-process restart, concurrent request collision,
   changed same-ID content, stale-head denial, unsupported merge/check,
   and adapter-mediated PR closure/issue restoration.

6. To test authenticated REVOKED policy, use the offline issuer:

   ```sh
   python examples/issue-97-admin-sign-authority.py revoke \
     --private-key rwf97-issuer.pem \
     --issuer-id rwf97-independent-issuer \
     --grant-id EXACT_GRANT_ID --revision 1 \
     --output revoked-rwf97.json
   ```

   Publish the signed file as `trusted/rwf97/revocations.json` on
   main and set RWF97_SIGNED_REVOCATIONS to its exact JSON.
   An old grant must then be rejected by the shipped adapter.
   Re-pinning the trusted main SHA requires independent review.

7. Turn `RWF97_ENABLE=false` after acceptance and retain evidence.
   Never paste keys, GitHub tokens or issuer secrets into a chat.

## Security boundary and optional stronger protection

The signed issuer public key, approved grant ID, current signed
revocation state and exact SHA variables are controlled via GitHub
administration, separate from GITHUB_TOKEN's repository permissions.
The verifier obtains current signed revocation facts each time and
cross-checks the main-branch audit mirror.  A stale or forged signed
record denies.  One-time grant consumption is unsupported and denies.

No normal RepoWorkflow workflow is granted write access.  No main or
release tags in RepoWorkflow are touched.

GitHub Free private repositories lack the requested server rulesets
and required environment reviewers.  These features cannot simply
be assumed.  GitHub Pro enables private rulesets, while private
required environment reviewers need a higher eligible plan.  They
remain optional defense-in-depth for THIS disposable positive test,
not substitutes for #80 cryptographic authorization.  Without rules,
this harness is NOT safe for executing arbitrary malicious candidate
code with the sandbox write token; use only independently reviewed
exact candidate SHA.  Production enforcement would require stronger
provider-side isolation.

Issue #97 is NOT DONE until the positive live Python write path and
all authoritative security/negative gates have been evidenced.
