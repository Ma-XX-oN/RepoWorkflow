# Consumer Adoption Checklist

A repository adopts RepoWorkflow only after its existing validation and
publication responsibilities have been inventoried. Migration must preserve
behaviour before duplicate machinery is removed.

1. Establish an issue-versioned migration branch.
2. Inventory every existing CI, policy, integration, artifact, and tagging
   responsibility.
3. Add `https://github.com/Ma-XX-oN/RepoWorkflow.git` as a Git submodule at
   exactly `RepoWorkflow/` and pin the reviewed commit. RepoWorkflow enforces
   that canonical URL so a consumer cannot silently substitute another engine.
4. Add `.ci/repoworkflow.json`, `.ci/github.json`, and
   `.ci/branch-policy.json`.
5. Provide one repository-owned version command and, when automatic iteration
   advancement is required, a repository-owned version setter.
6. Provide one authoritative validation command per genuinely distinct required
   environment/capability set.
7. Move test-level serial/parallel fan-out behind those repository validation
   commands; do not encode individual tests in RepoWorkflow JSON.
8. For each committed generated artifact, provide a generator, independent
   verifier, and exact output allow-list.
9. Install `RepoWorkflow/templates/github/ci.yml` byte-for-byte as the tiny
   `.github/workflows/ci.yml` bootstrap. The bootstrap delegates hosted work to
   RepoWorkflow's stable reusable workflow instead of duplicating the full CI
   implementation in the consumer.
10. Install `RepoWorkflow/templates/local/repoworkflow.py` as
    `scripts/repoworkflow.py`. This launcher executes before submodule engine
    code, compares the consumer gitlink with the checked-out RepoWorkflow HEAD,
    skips submodule repair when they match, and repairs a missing/mismatched
    checkout before delegation.
11. If hosted causal-equivalence testing requires a pre-existing GitHub workflow
    to remain executable during migration, list only that exact direct workflow
    filename in `.ci/github.json` `migrationWorkflows`. Undeclared additional
    workflows remain policy violations. Remove every migration entry and its
    legacy workflow immediately after equivalence is established.
12. Establish `.ci/run-ci-request` using the exact development version.
13. Run the authoritative local path:

    ```text
    python scripts/repoworkflow.py verify --push
    ```

    When the local submodule already matches the gitlink, this performs no
    submodule update. A missing or stale checkout is repaired automatically.
    Force repair explicitly when diagnosing the checkout itself:

    ```text
    python scripts/repoworkflow.py --force-repair verify --push
    ```

14. Run the hosted path where permitted and compare environment, artifact, and
    terminal-tag behaviour.
15. Remove old CI engines or standalone policy/integration workflows only after
    causal-equivalence verification proves their responsibilities are present
    in the new path.
16. Re-run local and hosted validation after cleanup.

The submodule gitlink, configuration, launchers, and repository scripts are part
of the consumer candidate. The gitlink is authoritative: the local launcher
establishes that exact engine before delegation and avoids network/submodule work
when the checked-out pin is already correct.
