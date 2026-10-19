"""Provider-backed immutable per-ref retirement audits for #681/#103."""
import unittest

from adapters.repo_host_github_integration_retirement import (
  RetirementAuditError, read_retirement, record_retirement,
)
from adapters.repo_host_github_integration_terminal import record_terminal
from tests.test_integration_terminal_github import (
  FakeBackend, G, C, D, P, REF, INT, terminal,
)


class AuditBackend(FakeBackend):
  def post(self, route, payload):
    if (route == "git/commits" and
        payload["message"].startswith("RWF-INTEGRATION-RETIREMENT-V2 ")):
      self.retirement_commit_count = getattr(
        self, "retirement_commit_count", 0) + 1
      sha = format(1000 + self.retirement_commit_count, "040x")
      self.commits[sha] = {
        "message": payload["message"], "tree": {"sha": payload["tree"]}}
      self.writes.append((route, payload))
      return {"sha": sha}
    return super().post(route, payload)


def audit(kind="PRELIM", **changes):
  value = {
    "repository": "Org/Repo", "guid": G, "ref_kind": kind,
    "retired_ref": REF if kind == "PRELIM" else INT,
    "expected_sha": P if kind == "PRELIM" else C,
    "operation_id": "retirement-123-" + kind.lower(),
    "terminal_evidence_ref": "test-log-123",
    "destination_ref": "refs/heads/main", "landed_sha": D,
    "outcome": "retired",
  }
  value.update(changes)
  return value


class RetirementAuditTests(unittest.TestCase):
  def setUp(self):
    self.backend = AuditBackend()
    record_terminal(self.backend, terminal(), authorized=True,
                    verify_evidence=lambda _: True)

  def publish(self, record=None, verifier=None):
    return record_retirement(self.backend, record or audit(),
      verify_deletion=(lambda _: True) if verifier is None else verifier)

  def test_publication_is_immutable_and_replay_readback_is_exact(self):
    self.assertIsNone(read_retirement(self.backend, G, "PRELIM"))
    status, result = self.publish()
    self.assertEqual(status, "applied")
    self.assertEqual(result, audit())
    self.assertEqual(read_retirement(self.backend, G, "PRELIM"), result)
    count = len(self.backend.writes)
    status, result = self.publish()
    self.assertEqual(status, "unchanged")
    self.assertEqual(len(self.backend.writes), count)

  def test_retirement_for_each_ref_keeps_independent_history(self):
    self.publish()
    status, int_audit = self.publish(audit("INT-ATTEMPT"))
    self.assertEqual(status, "applied")
    self.assertEqual(int_audit["retired_ref"], INT)
    self.assertEqual(read_retirement(self.backend, G, "PRELIM"), audit())
    self.assertEqual(read_retirement(self.backend, G, "INT-ATTEMPT"),
                     audit("INT-ATTEMPT"))

  def test_untrusted_deletion_cannot_publish(self):
    before = len(self.backend.writes)
    with self.assertRaisesRegex(RetirementAuditError, "trusted deletion"):
      self.publish(verifier=lambda _: False)
    self.assertEqual(len(self.backend.writes), before)

  def test_ref_still_exists_denies_retirement(self):
    self.backend.refs[REF] = P
    with self.assertRaisesRegex(RetirementAuditError, "still exists"):
      self.publish()

  def test_wrong_terminal_scope_and_sha_denied(self):
    for changes in (
      {"repository": "Other/Repo"},
      {"retired_ref": INT},
      {"expected_sha": C},
      {"destination_ref": "refs/heads/other"},
      {"landed_sha": "a"*40},
      {"terminal_evidence_ref": "made-up"},
      {"guid": "22222222-2222-4222-8222-222222222222"},
      {"ref_kind": "bad"},
      {"operation_id": ""},
      {"outcome": "unknown"},
    ):
      with self.subTest(changes=changes):
        with self.assertRaises(RetirementAuditError):
          self.publish(audit(**changes))

  def test_conflicting_provenance_cannot_reuse_retirement_key(self):
    self.publish()
    with self.assertRaisesRegex(RetirementAuditError, "conflicting"):
      self.publish(audit(operation_id="another-request"))

  def test_lost_publication_reply_reconciles_exact_record(self):
    self.backend.fail_after_create = True
    status, result = self.publish()
    self.assertEqual(status, "unchanged")
    self.assertEqual(result, audit())

  def test_unknown_provider_ref_read_is_not_absence(self):
    original = self.backend.get
    def read(route):
      if route == "git/ref/heads/" + REF.removeprefix("refs/heads/"):
        raise RuntimeError("provider transport down")
      return original(route)
    self.backend.get = read
    with self.assertRaisesRegex(RetirementAuditError, "readback UNKNOWN"):
      self.publish()

  def test_missing_terminal_is_not_deletion_authority(self):
    terminal_ref = "refs/tags/rwf-integration-terminal-v2-" + G
    self.backend.refs.pop(terminal_ref)
    with self.assertRaisesRegex(RetirementAuditError, "terminal landing"):
      self.publish()

  def test_corrupted_audit_tag_does_not_read_as_verified(self):
    self.publish()
    audit_ref = "refs/tags/rwf-integration-ref-retired-v2-" + G + "-prelim"
    sha = self.backend.refs[audit_ref]
    self.backend.commits[sha]["message"] = "forged"
    with self.assertRaisesRegex(RetirementAuditError, "identity invalid"):
      read_retirement(self.backend, G, "PRELIM")


if __name__ == "__main__":
  unittest.main()
