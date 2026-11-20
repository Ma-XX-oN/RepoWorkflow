# GitHub tracker adapter: limits and batching

Status: implementation notes for the GitHub implementation of
`.rwf/repo/tracker`. The limits below were measured on 2026-11-19 against
`Ma-XX-oN/Disposable-001` using a personal `gh` login. GitHub can change them
without notice, so the adapter must still handle rejections at runtime.

## Use GraphQL and batch requests

Use GitHub's GraphQL API rather than one REST call per ticket. One GraphQL
request can carry many operations, each under its own alias, so a batch costs
one connection and one round trip instead of one per ticket. This removes most
of the per-call overhead.

| Operation | One request per ticket | One batched GraphQL request |
| --- | --- | --- |
| Read 20 ticket descriptions | 8.92 s (0.45 s each) | 0.64 s |

Writes are batched the same way, for example several aliased `createIssue`,
`addBlockedBy` or `addComment` mutations in one request:

```graphql
mutation {
  a: createIssue(input: {repositoryId: "...", title: "...", body: "..."}) { issue { number } }
  b: createIssue(input: {repositoryId: "...", title: "...", body: "..."}) { issue { number } }
}
```

The response maps each alias to its result. For ticket creation this gives the
placeholder-to-ticket-ID mapping directly. `repositoryId` is GitHub's internal
repository ID, not `owner/name`; look it up once and cache it.

GitHub processes the mutations in a request one after another, at roughly
0.2–0.3 s each, so batching writes saves connection overhead but not GitHub's
own processing time.

## Limits

| Limit | Value | Evidence |
| --- | --- | --- |
| Per-request time | About 10 s; GitHub stops the request after that | A 90-issue `createIssue` request was cut off after 39 issues (~8.3 s): "Resource limits for this query exceeded". 30 `addComment` mutations took 8.8–9.0 s. |
| Created content per minute | 80 items, counted per item, not per request | Three back-to-back requests of 30 `addComment` mutations: exactly 80 succeeded within ~24 s, then the rest failed with "was submitted too quickly". |
| Hourly points | 5,000 per hour for a personal login | Each request above cost 1 point, regardless of how many mutations it held. |

GitHub's documented limits also apply: at most 100 items per page of a list,
at most 500,000 nodes per request, at most 100 concurrent requests, and at most
2,000 points per minute (a read request costs 1, a request containing
mutations costs 5).

## Adapter rules

- Send at most about 20 writes per request, to stay well clear of the
  per-request time limit. A timed-out request also costs extra points for the
  next hour.
- Create at most about 70 items per rolling minute across all requests
  (issues, comments and any other created content), below the hard limit of
  80. That is roughly three batches of 20, then a wait.
- Wait at least 1 second between write requests, as GitHub recommends for bulk
  writes.
- Read up to 100 tickets per request. Reads need no pacing.
- Read every alias's result. Partial success and rate-limit rejections are
  returned as per-item errors inside an HTTP 200 response, not as 403/429
  status codes, and `gh` may exit non-zero while still returning the items
  that succeeded.
- Treat a "was submitted too quickly" item as not yet done, not as a failure:
  record what succeeded, wait until the minute has passed, then resubmit only
  the rejected items.

## Who is charged

Limits are charged to the credential making the request:

| Credential | Charged to | Hourly points |
| --- | --- | --- |
| Personal login or token | That user account, across all repositories | 5,000 |
| GitHub App installation | That installation | 5,000, up to 12,500 for larger organizations |
| Actions `GITHUB_TOKEN` (CI) | The repository | 1,000 |

The created-content limit also counts actions the same user takes in the
GitHub web interface. A large local sync can therefore briefly block the
user's own GitHub activity; in CI, content is attributed to the
`github-actions` bot instead.

## Not yet measured

- Whether `addBlockedBy`, body edits or closing and reopening issues count
  toward the 80-per-minute created-content limit.
- How the limits behave for the Actions `GITHUB_TOKEN`.

## Sources

- [Rate limits and query limits for the GraphQL API](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [Best practices for using the REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- [Issues mutations](https://docs.github.com/en/graphql/reference/issues)
