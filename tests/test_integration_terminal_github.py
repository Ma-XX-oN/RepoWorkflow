"""Isolated GitHub-shaped terminal ledger acceptance for #681."""
import json
import unittest

from adapters.repo_host_github_integration_terminal import (
  TerminalProviderError, read_terminal, record_terminal,
  retirement_terminal_reader,
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
    "expected_destination_sha": B,
    "observed_destination_sha": D, "landed_sha": D,
    "provider_operation_id": "merge-op-123", "umbrella": "issue-123",
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
    if route.startswith("compare/"):
      base, head = route[len("compare/"):].split("...", 1)
      if (base, head) not in ((C, D), (D, D)):
        raise RuntimeError("unknown ancestry")
      return {"merge_base_commit": {"sha": base}}
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

  def test_recorded_destination_tip_requires_exact_provider_readback(self):
    with self.assertRaises(TerminalProviderError):
      self.publish(terminal(observed_destination_sha="f"*40))
    self.assertFalse(self.backend.writes)

  def test_landed_record_must_have_real_provider_ancestry(self):
    def reject_ancestry(route):
      if route.startswith("compare/"):
        return {"merge_base_commit": {"sha": "a"*40}}
      return FakeBackend.get(self.backend, route)
    self.backend.get = reject_ancestry
    with self.assertRaisesRegex(TerminalProviderError, "ancestry"):
      self.publish()
    self.assertFalse(self.backend.writes)

  def test_provider_terminal_projects_exact_103_callback_fields(self):
    from types import SimpleNamespace
    self.publish()
    source = terminal()
    landed = SimpleNamespace(**source)
    reader = retirement_terminal_reader(self.backend, landed)
    expected = {key: source[key] for key in (
      "status", "prelim_ref", "prelim_sha", "int_attempt_ref",
      "accepted_sha", "destination_ref", "landed_sha",
      "integration_id", "terminal_evidence_ref")}
    self.assertEqual(reader(source["terminal_evidence_ref"]), expected)
    with self.assertRaisesRegex(TerminalProviderError, "differs"):
      reader("another-evidence")

  def test_retirement_projection_rejects_different_landed_claim(self):
    from types import SimpleNamespace
    self.publish()
    source = terminal()
    claim = SimpleNamespace(**terminal(landed_sha="e"*40))
    with self.assertRaisesRegex(TerminalProviderError, "differs"):
      retirement_terminal_reader(self.backend, claim)(
        source["terminal_evidence_ref"])

  def test_deferred_mit_does_not_become_irreversible_terminal(self):
    with self.assertRaisesRegex(TerminalProviderError, "resumable"):
      self.publish(terminal(status="deferred-mit", landed_sha=None))
    self.assertEqual(self.backend.writes, [])
    self.assertIsNone(read_terminal(self.backend, G))

  def test_missing_record_is_pending_not_success(self):
    self.assertIsNone(read_terminal(self.backend, G))


if __name__ == "__main__":
  unittest.main()
