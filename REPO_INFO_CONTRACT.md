# Portable Repository Information Contract

Status: authoritative provider-neutral read contract for core RWF.

This contract defines the repository/ticket-manager information that core RWF
may request without embedding GitHub-specific API, issue-body, label, or project
logic.

## 1. Boundary

Core RWF consumes semantic repository information through a configured
`repo-info` adapter.

The adapter owns provider-specific access and normalization.  Core callers own
workflow decisions made from the normalized result.

All operations in this contract are read-only.

## 2. Invocation

The portable executable interface is:

```text
repo-info repository
repo-info issue get ISSUE
repo-info issue list-open
```

Successful operations write exactly one JSON value to stdout and exit `0`.

Failures write a human-readable diagnostic to stderr, write no successful JSON
value to stdout, and exit non-zero.

Core RWF must not interpret provider-specific exit codes.

## 3. Repository result

`repo-info repository` returns:

```json
{
  "schema_version": 1,
  "repository": "owner/name",
  "provider": "github"
}
```

`repository` is the adapter's stable repository identity.  `provider` is
informational identity for diagnostics/configuration and must not be branched on
by core workflow semantics.

## 4. Issue result

`repo-info issue get ISSUE` returns:

```json
{
  "schema_version": 1,
  "number": 64,
  "title": "Implement rwf issue start transition",
  "state": "open",
  "link": "https://example.invalid/issues/64"
}
```

Required fields are exactly:

- `schema_version`: integer `1`;
- `number`: positive integer;
- `title`: non-empty text;
- `state`: `open` or `closed`;
- `link`: non-empty canonical `http://` or `https://` browser URL for the issue.

The requested issue number must equal the returned `number`.

A missing issue is an explicit failure, not a successful null/empty result.

## 5. Open-issue list result

`repo-info issue list-open` returns:

```json
{
  "schema_version": 1,
  "issues": [
    {"number": 64, "title": "Implement rwf issue start transition"}
  ]
}
```

The list contains only open issues and is sorted by ascending issue number.
Duplicate issue numbers are invalid.

An empty repository legitimately returns `"issues": []`.  Provider failure
must never be normalized to that value.

## 6. Consumer guarantees

The contract deliberately exposes only provider facts required by current core
consumers.

For #64 issue-start, `issue get` is sufficient to prove that the requested
issue exists and that its provider state is currently open.  The normalized
`link` is provider-neutral presentation data for consumers such as issue/lane
list rendering; core RWF must not construct provider-specific issue URLs.

Canonical RWF dependency relationships, lifecycle state, readiness, current
work, validation evidence, and version state do not come from this adapter.
Those facts are owned by their RWF stores/contracts.

#120 owns invocation/dispatch of this contract and must forward semantic
requests without changing their meaning.

## 7. Validation

The dispatcher/adapter implementation must prove at least:

1. valid repository, issue-get, and open-list results normalize exactly;
2. issue numbers are positive and requested/returned identity matches;
3. unsupported schema versions fail explicitly;
4. malformed JSON and missing/extra required fields fail explicitly;
5. provider failure remains failure;
6. missing issue remains failure;
7. an empty successful open list remains distinguishable from provider failure;
8. open-list output is deterministic and duplicate-free;
9. issue links are canonical browser URLs and malformed/missing links fail;
10. core callers require no GitHub-specific fields.

## 8. Evolution

Additional provider facts may be added only when a core consumer demonstrates a
semantic requirement for them.

Do not expose raw provider payload as an escape hatch.  Extend the normalized
contract explicitly instead.
