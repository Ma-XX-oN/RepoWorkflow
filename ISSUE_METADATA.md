# Issue Metadata

Status: authoritative boundary between synchronized ticket state and optional
provider display metadata.

## Canonical ticket metadata

The canonical durable ticket record is defined by
[TICKET_STATE.md](TICKET_STATE.md) and stored in:

```text
.repoworkflow/tickets.csv
```

It contains exactly:

- ticket number;
- exact provider title;
- direct dependencies.

Titles are not duplicated in a second authoritative metadata store.

## Display metadata

Provider state/link values used only for presentation such as `lanes list
--links` may be cached separately under the generic durable state store.

Those values are not dependency, title, lifecycle, readiness, or branch-parent
authority.

A plain offline lane list needs only the canonical ticket file. A request that
needs provider link/state information must have complete display metadata or
refresh it explicitly.

## Refresh

A metadata refresh:

1. reads the canonical ticket scope;
2. obtains provider issue information;
3. validates all requested results;
4. applies provider-authoritative title updates to canonical ticket state;
5. publishes validated display state/link data.

Failure does not publish partial title changes. Provider failure never becomes
an empty title or empty display value.

## Invariants

- ticket number identity is exact;
- provider title is always authoritative;
- display metadata cannot introduce a ticket absent from canonical state;
- display metadata never replaces dependency or lifecycle authority;
- offline title reads never contact the provider;
- malformed/missing provider values fail closed.

TEST_ADEQUACY.md applies.
