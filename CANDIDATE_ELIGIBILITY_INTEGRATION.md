# Exact-candidate eligibility gate (#104)

## Ownership

This ticket owns the provider-neutral per-candidate allow/block decision.
It does **not** authorise a merge or perform acceptance-time remote locking.
Issue #542 must recheck the live destination and candidate at final acceptance;
#85 owns remote enforcement and #543 owns assembled CI/CLI certification.

## Decision inputs

- `repo_workflow.candidate_eligibility.decide` is the pure deterministic
  candidate decision. The candidate, tested SHA and current source HEAD must
  match. The recorded and current destination-base SHAs must match.
- `repo_workflow.candidate_evidence.read_evidence_gate` uses #69's
  `ValidationEvidenceStore.read` and #95's coverage evaluator. Callers supply
  a complete, trusted requirements manifest and exact observation IDs.
  Absent, stale, failed, malformed and mismatched records cannot grant PASS.
  Coverage of zero declared required units never grants PASS.
- `repo_workflow.github_host_facts.read_host_facts` fetches current source
  and destination branch tips and a provider comparison of the actual base
  to the candidate. The source SHA, destination SHA and ancestry result are
  **read from GitHub**, not accepted as caller-supplied positive flags.
- `decide_with_verified_sources` combines those two boundaries and passes
  derived facts to the pure `decide` function; neither a successful
  intermediate decision nor a branch name grants merge authorisation.

## Trust and applicability

The current #548 contract explicitly assumes trusted test-result publishers;
its advanced publisher-role authentication is deferred. A successful #69
store read checks payload integrity, not independent adversarial publisher
identity. When #548's advanced role enforcement is activated, this boundary
must consume that enforced publisher authority before allowing integration.

The requirements manifest must come from an authoritative complete
configuration, not an arbitrary incomplete selection. The coverage evaluator
must be the #95 implementation; the durability store must be the #69 store.
An importer or ordinary caller must not substitute a fake PASS or declare
the requirements manifest complete without independent authority.

Each decision is transient. Changes to the candidate, testing inputs, source
HEAD, destination SHA, requirements or evidence require a new evaluation.
A final acceptance-time check is mandatory even after a prior ALLOW.

## Verification

The issue-tier test groups are `issue-104-candidate-eligibility`,
`issue-104-github-host-facts` and `issue-104-durable-evidence`.
Their black-box matrices cover SHA-1/SHA-256 identities, stale bases,
moved heads, ancestry failures, malformed/failed provider responses,
invalid store records, stale/failed/incomplete required-unit coverage,
empty manifests and repeated reassessment.

Provider-neutral semantic code is separated from GitHub-specific read-only
fact acquisition. No protected-branch configuration, remote check
publication, merge or production cutover is performed by these modules.
