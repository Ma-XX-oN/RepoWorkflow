# Preliminary executable-test start gate

Executable tests are part of the start contract, not a detached admission workflow.

## States

- `start`: work is selected/preparing and preliminary requirements have not yet cleared.
- `start-preliminary`: ticket executable tests differ from the trusted canonical set; implementation is blocked pending an explicit choice.
- `start-failed`: the RED gate found a GREEN preliminary test or could not safely execute the gate.
- `implement`: every accepted preliminary executable test is RED and implementation may proceed.

These states are deliberately separate from the durable issue lifecycle (`active`, `accepted`, `completed`). They describe the start gate, not completion/acceptance of work.

## Changed tests

A changed structured executable-test section freezes exact OLD and NEW sets and enters `start-preliminary`. Review with:

```text
rwf tests view
rwf tests view new
rwf tests view old
rwf tests diff
```

`rwf tests view` is exactly `view new`.

Continue with exactly one explicit choice:

```text
rwf tests accept new
rwf tests accept old
```

`new` replaces the canonical executable-test set with the reviewed proposal. `old` rejects/discards the proposal and retains the prior canonical set. Bare `rwf tests accept` is invalid.

Proposal staleness is determined by the exact structured executable-test bytes, not unrelated ticket prose. If the ticket test section changes after review, neither old nor new may be selected from that stale review.

## RED gate

After an unchanged contract or an explicit old/new choice, RWF executes the canonical trusted preliminary tests. Every test must be RED. Any GREEN test means the assumed starting condition is already satisfied and start fails closed as RED non-compliance. Runner errors also fail closed. Only an all-RED result enters `implement`.

The final #230 `rwf start <id>` implementation owns branch preparation and automatic comparison. Bare `rwf start` for selected current work reruns this RED gate.
