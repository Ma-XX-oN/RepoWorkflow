# Worktree-local issue selection

The current-work record under `<git-dir>/repoworkflow/current-work/` selects
the issue being worked on in that worktree. It is local navigation data and
is never committed. Linked worktrees have separate selections.

Its value contains:

```json
{
  "current": {"issue": "64"},
  "resume": null,
  "selected_issue": "64"
}
```

`current` and `resume` are issue references or null. `selected_issue` is an
issue number or null. Start sets `current` and selection; abort may retain
the issue in `resume` while clearing `current`.

Ticket state and dependencies are read from [tickets.csv](TICKET_STATE.md).
Changing the CSV does not invalidate an issue selection. Selecting an issue
does not change its state, complete a prerequisite or prove test results.
Commands validate current CSV state and applicable test evidence when acting.

Local selection updates reject conflicting writes. Missing local data means
no issue is selected; it says nothing about the states of repository tickets.
