# Issue 627 — provider protection capability survey

## Provenance
- Repository: Ma-XX-oN/RepoWorkflow
- Authenticated connector profile: ID 10625935, nickname Ma-XX-oN.
- Connector methods inspected: get_profile, search_branches, fetch_file,
  fetch_issue, fetch_issue_comments.
- Provider observations: main exists; repository test catalogue is readable.
- The available connector methods do not expose branch-protection settings,
  repository rulesets, effective actor permissions, token scopes or tag rules.
  Therefore no protection enforcement is certified by these observations.

## Independent provider acceptance matrix

| Scenario | Non-mutating evidence needed | Current verdict |
| --- | --- | --- |
| Direct push to main | Effective branch rule and actor bypass list | INCOMPLETE |
| Force push to main | Effective force-push restrictions and actor bypass | INCOMPLETE |
| Delete main | Effective deletion rule and actor bypass | INCOMPLETE |
| Stale-base push | Required up-to-date checks and merge queue configuration | INCOMPLETE |
| Unauthorized actor | Ruleset actor matching and effective bypass identities | INCOMPLETE |
| Required checks | Required check names, sources and exact SHA | INCOMPLETE |
| Protected release tag | Tag ruleset patterns and bypass actors | INCOMPLETE |

A successful read of a branch is **not** evidence that writes are restricted.
Do not perform any production mutation as a probe.

## Reproduction / follow-up

Read-only GitHub REST probes, when an authorized client is available:

- GET /repos/Ma-XX-oN/RepoWorkflow
- GET /repos/Ma-XX-oN/RepoWorkflow/branches/main/protection
- GET /repos/Ma-XX-oN/RepoWorkflow/rulesets
- GET /repos/Ma-XX-oN/RepoWorkflow/rules/branches/main
- GET /repos/Ma-XX-oN/RepoWorkflow/rulesets?includes_parents=true
- GET /user and inspect authenticated token permissions from response headers
  where provided by the authentication mechanism.

Record response status, UTC timestamp, repository ID, actor, effective rule
IDs, bypass subjects, and sanitized response bodies. A 403 or 404 on policy
endpoints is INCOMPLETE, not evidence of absent protection.

The seven rows are independent black-box contract cases. Actual rejection
testing requires an authorized isolated test repository with representative
rules and distinct actor identities. Production main and release tags must
not be used for destructive probes.

## Handoff to #85

This is a preparatory read-only capability survey. It does not establish
protected-main enforcement. #85 must obtain the missing policy observations
and verify the effective bypass and enforcement matrix before certification.
