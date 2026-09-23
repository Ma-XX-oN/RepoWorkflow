# Consumer Adoption Checklist

A repository adopts RepoWorkflow only after its existing validation and
publication responsibilities have been inventoried. Migration must preserve
behaviour before duplicate machinery is removed.

1. Establish an issue-versioned migration branch.
2. Inventory every existing CI, policy, integration, artifact, and tagging
   responsibility.
3. Add `https://github.com/Ma-XX-oN/RepoWorkflow.git` as a Git submodule at
   exactly `RepoWorkflow/` and pin the reviewed commit.  RepoWorkflow enforces
   that canonical URL so a consumer cannot silently substitute another engine.
4. Add `.ci/repoworkflow.json`, `.ci/github.json`, and
   `.ci/branch-policy.json`.
5. Provide one repository-owned version command.
6. Provide one authoritative validation command per genuinely distinct required
   environment/capability set.
7. Move test-level serial/parallel fan-out behind those repository validation
   commands; do not encode individual tests in RepoWorkflow JSON.
8. For each committed generated artifact, provide a generator, independent
   verifier, and exact output allow-list.
9. Install `RepoWorkflow/templates/github/ci.yml` byte-for-byte as
   `.github/workflows/ci.yml`.
10. Establish `.ci/run-ci-request` using the exact development version.
11. Run RepoWorkflow locally and compare its coverage/results with the existing
    repository workflow.
12. Run the hosted path where permitted and compare environment, artifact, and
    terminal-tag behaviour.
13. Remove old CI engines or standalone policy/integration workflows only after
    causal-equivalence verification proves their responsibilities are present
    in the new path.
14. Re-run local and hosted validation after cleanup.

The submodule pin, configuration, and repository scripts are part of the
consumer candidate. RepoWorkflow never silently self-updates.
