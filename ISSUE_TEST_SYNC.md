# Executable issue-test synchronization and admission

Executable issue tests are issue-contract data, but synchronizing executable
content from a ticket does not grant authority to execute it.

Repository and ticket representations compare by executable meaning: ordered
language/body pairs.  Identical content is idempotent.  Missing ticket structure
does not delete repository tests.  Differing content is a conflict unless a
caller explicitly requests replacement.

Ticket-only or explicitly replaced ticket content always enters repository
state as `ticket-proposed`.  Import and admission are separate operations.
Only an explicit admission transition can change `ticket-proposed` to
`admitted`.

Trust state is never rendered into ticket Markdown.  Therefore repository to
ticket to repository round trips preserve executable meaning without allowing
ticket text to manufacture execution authority.

This contract is separate from #208-#214 native dependency synchronization.
Those commands continue to synchronize dependency facts only.
