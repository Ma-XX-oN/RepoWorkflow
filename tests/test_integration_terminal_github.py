"""Isolated GitHub-shaped terminal ledger acceptance for #681."""
import json
import unittest

from adapters.repo_host_github_integration_terminal import (
  TerminalProviderError, read_terminal, record_terminal,
)


G = "11111111-1111-4111-8111-111111111111"
C = "c"*40
D = "d"*40
P = "a"*40
B = "b"*40
REF = "refs/heads/PRELIM-issue-123/main-" + G
INT = "refs/heads/INT-ATTEMPT-issue-123/main-" + G


def terminal(**updates):
  value = {
    "repository": "Org/Repo", "guid": G,
    "status": "integrated", "prelim_ref": REF, "prelim_sha": P,
    "int_attempt_ref": INT, "accepted_sha": C,
    "destination_ref": "refs/heads/main",
    "expected_destination_sha": B, "landed_sha": D,
    "integration_id": "op-123", "terminal_evidence_ref": "test-log-123",
  }
  value.update(updates)
  return value


class NotFound(Exception):
  code = "not_found"


class FakeBackend:
  repository = "Org/Repo"

  def __init__(self):
    self.refs = {"refs/heads/main": D}
    self.commits = {D: {"tree": {"sha": "e"*40}}}
    self.writes = []
    self.fail_after_create = False

  def get(self, route):
    if route.startswith("git/ref/"):
      ref = "refs/" + route[len("git/ref/"):]
      if ref not in self.refs:
        raise NotFound()
      return {"ref": ref, "object": {"sha": self.refs[ref]}}
    if route.startswith("git/commits/"):
      sha = route[len("git/commits/"):]
      if sha not in self.commits:
        raise NotFound()
      return self.commits[sha]
    raise AssertionError("unexpected route " + route)

  def post(self, route, payload):
    self.writes.append((route, payload))
    if route == "git/commits":
      sha = "f"*40
      self.commits[sha] = {
        "message": payload["message"],
        "tree": {"sha": payload["tree"]},
      }
      return {"sha": sha}
    if route == "git/refs":
      if payload["ref"] in self.refs:
        raise RuntimeError("already exists")
      self.refs[payload["ref"]] = payload["sha"]
      if self.fail_after_create:
        raise RuntimeError("lost response")
      return {"ref": payload["ref"]}
    raise AssertionError("unexpected route " + route)


class TerminalLedgerTests(unittest.TestCase):
  def setUp(self):
    self.backend = FakeBackend()

  def publish(self, value=None, authorized=True, verifier=None):
    return record_terminal(
      self.backend, terminal() if value is None else value,
      authorized=authorized,
      verify_evidence=(lambda record: True) if verifier is None else verifier,
    )

  def test_first_publication_round_trip_preserves_full_record(self):
    state, result = self.publish()
    self.assertEqual(state, "applied")
    self.assertEqual(result["record"], terminal())
    self.assertEqual(read_terminal(self.backend, G), terminal())
    self.assertEqual(self.backend.refs["refs/heads/main"], D)
    self.assertTrue(all(not key.startswith("refs/heads/PRELIM-")
                        for key in self.backend.refs))
    self.assertEqual(len(self.backend.writes), 2)

  def test_immutable_exact_replay_never_writes(self):
    self.publish()
    before = list(self.backend.writes)
    state, result = self.publish()
    self.assertEqual(state, "unchanged")
    self.assertEqual(result["record"], terminal())
    self.assertEqual(self.backend.writes, before)

  def test_conflicting_terminal_and_foreign_repository_are_rejected(self):
    self.publish()
    with self.assertRaisesRegex(TerminalProviderError, "already bound"):
      self.publish(terminal(terminal_evidence_ref="other"))
    with self.assertRaisesRegex(TerminalProviderError, "invalid"):
      self.publish(terminal(repository="Other/Repo"))
    self.assertEqual(read_terminal(self.backend, G), terminal())

  def test_missing_authority_fails_without_writes(self):
    with self.assertRaisesRegex(TerminalProviderError, "unauthorized"):
      self.publish(authorized=False)
    with self.assertRaisesRegex(TerminalProviderError, "evidence"):
      self.publish(verifier=lambda record: False)
    self.assertEqual(self.backend.writes, [])

  def test_lost_ref_reply_recovers_exact_full_record(self):
    self.backend.fail_after_create = True
    state, result = self.publish()
    self.assertEqual(state, "unchanged")
    self.assertEqual(result["record"], terminal())
    self.assertEqual(read_terminal(self.backend, G), terminal())

  def test_lost_ref_reply_wrong_result_does_not_fabricate_pass(self):
    class ConflictingBackend(FakeBackend):
      def post(self, route, payload):
        if route == "git/refs":
          ref = payload["ref"]
          self.refs[ref] = "a"*40
          self.commits["a"*40] = {
            "message": "RWF-INTEGRATION-TERMINAL-V2 " + json.dumps(
              terminal(terminal_evidence_ref="forged"),
              sort_keys=True, separators=(",", ":")),
            "tree": {"sha": "e"*40},
          }
          raise RuntimeError("unknown")
        return super().post(route, payload)
    self.backend = ConflictingBackend()
    with self.assertRaisesRegex(TerminalProviderError, "UNKNOWN"):
      self.publish()
    self.assertNotEqual(read_terminal(self.backend, G), terminal())

  def test_missing_record_is_pending_not_success(self):
    self.assertIsNone(read_terminal(self.backend, G))


if __name__ == "__main__":
  unittest.main()
