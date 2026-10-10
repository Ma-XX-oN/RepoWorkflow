# Durable validation evidence storage (#69)

One immutable observation occupies a #101 versioned JSON record under
.repoworkflow/validation/records. Writer/session identity, schema version,
atomic fsync publication, and record-scoped conflict checks come from #101.
The domain API only supports create, read, and list; no replace operation.

Each observation contains its stable record ID, exact candidate SHA,
version, branch, unit, #68 fingerprint, verdict, mode, runner, platform,
and provider-run identity. A digest of canonical schema-versioned payload
bytes is verified on every read. Invalid IDs, malformed evidence,
unexpected fields, changed verdicts and broken state envelopes fail closed.
Successful reads can project into the #95 pure coverage evaluator.

**Repository history boundary:** local atomic creation does not alone
preserve evidence after clone deletion. The caller must commit the durable
record and push the commit to a retained authoritative Git ref. Once
retained by shared history, execution branch/worktree cleanup does not
erase the observation. Distinct record IDs merge independently; conflicting
same-ID records are not overwritten. Locks on one clone are not
distributed locks across clones. A digest provides integrity detection
against accidental change, not authentication against deliberate rewrite.

Producer authentication, real runner-capability evidence, exact candidate
authorization, audit commit retention, and local-hosted applicability must
be enforced before reusable evidence is admitted downstream. Those are
integration responsibilities for #70 and later stages.

Tests: tests/test_validation_store.py and the issue-69-durable-evidence
Self CI group.
