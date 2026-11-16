# Ticket state acceptance

The state and dependency contract is [TICKET_STATE.md](TICKET_STATE.md).

| Behavior | Required observation | Tests |
| --- | --- | --- |
| State update | CSV changes immediately; no lifecycle record is created | `test_lifecycle_store` |
| Dependency readiness | Prerequisite CSV state controls readiness | `test_lifecycle_store`, `test_workspace_readiness` |
| Invalid transition | CSV remains unchanged | `test_lifecycle_store` |
| Concurrent edits | Stale write fails without overwriting another edit | `test_ticket_state` |
| Semantic merge | Independent state/dependency edits survive; divergent states conflict | `test_ticket_state`, `test_ticket_merge` |
| Start and resume | Branch/version and active CSV state are committed; unchanged resume is idempotent | `test_issue_start` |
| Completion | Actual tests pass before the completed CSV reaches the parent | `test_done_workflow` |
| Graph presentation | All six glyphs reflect CSV state without copying from another store | `test_six_state_integration` |
| Clone readback | Fresh clone observes the committed CSV state | `test_lifecycle_clone_publish` |
| Test selection | Additional groups are recorded only in the existing test catalogue | `test_high_risk`, `test_self_ci_tiers` |

Existing testing and integration tests continue to verify exact-candidate,
current-parent evidence reuse and reconstruction. These are test-evidence
requirements, not additional fields or histories in ticket state.
