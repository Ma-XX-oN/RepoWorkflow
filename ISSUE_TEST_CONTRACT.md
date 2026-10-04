# Executable issue-test contract

Executable requirement tests are structured evidence attached to an issue
contract.  They supplement preconditions, postconditions, and invariants; they
do not replace those semantic requirements.

RWF workflow facts such as dependency edges, dependency completion, issue
readiness, and lane ownership remain intrinsic RWF checks and must not be
duplicated as executable issue tests.

## Ticket representation

Only fences inside the explicit structured section are executable-test data:

~~~markdown
<!-- rwf:issue-tests:v1 -->
```bash
test -f PARENT_BRANCH_WORKFLOW.md
```
<!-- /rwf:issue-tests -->
~~~

Ordinary Markdown fences elsewhere in a ticket are prose/examples and are
ignored.  The fence language selects the evaluator.  Version 1 recognizes
`bash` and `python`; unknown languages fail validation.

Ticket parsing assigns `ticket-proposed` trust.  Trust authority is never
serialized into ticket Markdown, so editing a ticket cannot grant execution
authority.  Repository state may use `repository`, `ticket-proposed`, or
`admitted` trust.

The exact test body, language, and order are preserved across structured
render/parse operations.  Tests may intentionally be RED before implementation.
A GREEN test is evidence only for the requirement represented by that test.
