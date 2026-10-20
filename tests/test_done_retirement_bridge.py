"""Independent #681 provider terminal to #103 cleanup proof projections."""
from dataclasses import replace
import unittest

from repo_workflow.done_retirement_bridge import (
  RetirementBridgeError, retirement_bridge_from_v2,
)
from repo_workflow.done_terminal_v2 import IntegratedTerminal


G = "11111111-1111-4111-8111-111111111111"
P = f"refs/heads/PRELIM-issue-123/main-{G}"
I = P.replace("PRELIM-", "INT-ATTEMPT-")
A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
TERMINAL = {
  "repository": "Org/Repo", "guid": G, "status": "integrated",
  "prelim_ref": P, "prelim_sha": A, "int_attempt_ref": I,
  "accepted_sha": C, "destination_ref": "refs/heads/main",
  "expected_destination_sha": B, "observed_destination_sha": D,
  "landed_sha": D, "integration_id": "merge-1",
  "provider_operation_id": "op-1",
  "umbrella": "issue-123", "terminal_evidence_ref": "evidence-1",
}


class Host:
  repository = "Org/Repo"
  def __init__(self):
    self.observed = TERMINAL
    self.calls = []
  def request(self, operation, request_id, params):
    self.calls.append((operation, request_id, params))
    assert operation == "attempt.read"
    return {"guid": G, "record": self.observed}


class RetirementBridgeTests(unittest.TestCase):
  def setUp(self):
    self.host = Host()
    self.terminal = IntegratedTerminal(
      G, "Org/Repo", "main", C, D, "merge-1", "op-1",
      "evidence-1", dict(TERMINAL))

  def test_provider_readback_exact_projection(self):
    bridge = retirement_bridge_from_v2(self.host, self.terminal)
    self.assertEqual(bridge.landed.prelim_ref, P)
    self.assertEqual(bridge.landed.accepted_sha, C)
    expected = {k: v for k, v in TERMINAL.items() if k in (
      "status", "prelim_ref", "prelim_sha", "int_attempt_ref",
      "accepted_sha", "destination_ref", "landed_sha",
      "integration_id", "terminal_evidence_ref")}
    self.assertEqual(bridge.read_terminal("evidence-1"), expected)
    bridge.read_terminal("evidence-1")
    self.assertNotEqual(self.host.calls[0][1], self.host.calls[1][1])

  def test_wrong_reference_never_calls_provider(self):
    bridge = retirement_bridge_from_v2(self.host, self.terminal)
    with self.assertRaisesRegex(RetirementBridgeError, "foreign"):
      bridge.read_terminal("other-evidence")
    self.assertEqual(self.host.calls, [])

  def test_changed_provider_terminal_fails_closed(self):
    bridge = retirement_bridge_from_v2(self.host, self.terminal)
    self.host.observed = {**TERMINAL, "accepted_sha": B}
    with self.assertRaisesRegex(RetirementBridgeError,"differs"):
      bridge.read_terminal("evidence-1")

  def test_cross_attempt_terminal_mismatch_denied(self):
    for terminal in (
      replace(self.terminal, operation_id="foreign-op"),
      replace(self.terminal, accepted_sha=B),
      replace(self.terminal, repository="Other/Repo"),
    ):
      with self.subTest(terminal=terminal):
        with self.assertRaises(RetirementBridgeError):
          retirement_bridge_from_v2(self.host, terminal)


if __name__ == "__main__":
  unittest.main()
