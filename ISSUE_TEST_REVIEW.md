# Executable-test ticket review workflow

For the current issue established by `rwf start`:

```text
rwf tests sync
rwf tests view
rwf tests view new
rwf tests view old
rwf tests diff [git diff options...]
rwf tests <git-cmd> [args...]
rwf tests accept
```

`rwf tests sync` is the explicit provider operation. Repository-only tests are published into an absent structured ticket section. Identical sets are idempotent. Ticket-only or differing tests create a frozen before/after review and print a warning ending with the explicit acceptance command.

`rwf tests view` is exactly equivalent to `rwf tests view new`. `old` displays the complete trusted set that preceded the proposal.

Other `rwf tests` subcommands are passed as an argv vector to `git` followed by `--no-index -- <before-file> <after-file>`. This supports compatible Git diff commands/options and user Git aliases without shell evaluation by RWF. RWF verifies the frozen review files remain unchanged afterward.

`rwf tests accept` admits exactly the frozen proposal. It first re-reads the ticket and rejects acceptance if the ticket body digest has changed since synchronization. There is no implicit/default acceptance.
