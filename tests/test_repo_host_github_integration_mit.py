"""Real-shaped provider MIT event ledger tests without protected ref mutation."""
import unittest
from unittest.mock import patch

from adapters.repo_host_github_integration_mit import (
  MitProviderError, read_mit, record_mit,
)

GUID = "11111111-1111-4111-8111-111111111111"
HEAD = "a" * 40
TREE = "b" * 40


class Missing(Exception):
  code = "not_found"


class Backend:
  repository = "Org/Repo"

  def __init__(self):
    self.refs = {}
    self.commits = {HEAD: {"tree": {"sha": TREE}}}
    self.seq = 0
    self.lose_reply = False

  def get(self, path):
    if path == "git/ref/heads/main":
      return {"ref":"refs/heads/main","object":{"sha":HEAD}}
    if path.startswith("git/ref/tags/"):
      ref = "refs/tags/" + path[len("git/ref/tags/"):]
      if ref not in self.refs:
        raise Missing()
      return {"ref":ref,"object":{"sha":self.refs[ref]}}
    if path.startswith("git/matching-refs/tags/"):
      prefix = ("refs/tags/" + path.split("?",1)[0].split(
        "git/matching-refs/tags/",1)[1])
      page = int(path.split("page=")[-1])
      refs = sorted(ref for ref in self.refs if ref.startswith(prefix))
      return [{"ref":ref,"object":{"sha":self.refs[ref]}} for ref in
              refs[(page-1)*100:page*100]]
    if path.startswith("git/commits/"):
      return self.commits[path.removeprefix("git/commits/")]
    raise AssertionError(path)

  def post(self, path, value):
    if path == "git/commits":
      self.seq += 1
      sha = f"{self.seq:040x}"
      self.commits[sha] = dict(value)
      return {"sha":sha}
    if path == "git/refs":
      if value["ref"] in self.refs:
        raise ValueError("duplicate GitHub ref")
      self.refs[value["ref"]] = value["sha"]
      if self.lose_reply:
        raise ValueError("response lost after write")
      return {"ref":value["ref"]}
    raise AssertionError(path)


def deferred(generation=1, **changes):
  value = {
    "repository":"Org/Repo", "guid":GUID, "destination":"main",
    "prelim_sha":"c"*40, "lease_generation":generation,
    "evidence_ref":"defer-" + str(generation), "reason":"timeout",
  }
  value.update(changes)
  return value


def approval(generation=2, **changes):
  value = {
    "repository":"Org/Repo", "guid":GUID, "destination":"main",
    "prelim_sha":"c"*40, "expected_generation":generation,
    "deferred_evidence_ref":"defer-1",
    "evidence_ref":"approve-" + str(generation), "approved":True,
  }
  value.update(changes)
  return value


class MitProviderTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()

  def save(self, kind, record, verifier=lambda record:True):
    return record_mit(self.backend,kind,record,verify_evidence=verifier)

  def test_missing_event_is_not_approval(self):
    self.assertIsNone(read_mit(self.backend,"deferred",GUID,"main"))
    self.assertIsNone(read_mit(self.backend,"resume",GUID,"main"))

  def test_durable_defer_and_resume_are_separate(self):
    status, record = self.save("deferred",deferred())
    self.assertEqual(status,"applied")
    self.assertEqual(record,read_mit(self.backend,"deferred",GUID,"main"))
    self.assertIsNone(read_mit(self.backend,"resume",GUID,"main"))
    self.assertEqual(self.save("resume",approval())[0],"applied")
    self.assertEqual(read_mit(self.backend,"resume",GUID,"main"),
                     approval())
    self.assertEqual(self.save("deferred",deferred())[0],"unchanged")

  def test_append_only_later_generation(self):
    self.save("deferred",deferred())
    self.save("deferred",deferred(3))
    self.assertEqual(read_mit(self.backend,"deferred",GUID,"main"),
                     deferred(3))
    self.assertEqual(len(self.backend.refs),2)

  def test_existing_generation_collision_denied(self):
    self.save("deferred",deferred())
    with self.assertRaisesRegex(MitProviderError,"different"):
      self.save("deferred",deferred(reason="awaiting-manual"))
    self.assertEqual(read_mit(self.backend,"deferred",GUID,"main"),
                     deferred())

  def test_lost_create_reply_reconciles_by_exact_record(self):
    self.backend.lose_reply=True
    self.assertEqual(self.save("deferred",deferred())[0],"unchanged")
    self.assertEqual(read_mit(self.backend,"deferred",GUID,"main"),
                     deferred())

  def test_same_generation_revocation_overrides_prior_approval(self):
    self.save("deferred",deferred())
    self.save("resume",approval())
    self.assertTrue(read_mit(self.backend,"resume",GUID,"main")["approved"])
    revoked=approval(approved=False,evidence_ref="revoke-2")
    self.assertEqual(self.save("resume",revoked)[0],"applied")
    self.assertEqual(read_mit(self.backend,"resume",GUID,"main"),revoked)
    self.assertEqual(len(self.backend.refs),3)
    with self.assertRaisesRegex(MitProviderError,"revoked"):
      self.save("resume",approval())

  def test_later_generation_approval_does_not_reuse_revoked_event(self):
    self.save("deferred",deferred())
    self.save("resume",approval(approved=False,evidence_ref="revoke-2"))
    self.save("deferred",deferred(3))
    fresh=approval(4,deferred_evidence_ref="defer-3")
    self.save("resume",fresh)
    self.assertEqual(read_mit(self.backend,"resume",GUID,"main"),fresh)

  def test_resume_requires_latest_independent_defer(self):
    with self.assertRaisesRegex(MitProviderError,"deferral"):
      self.save("resume",approval())
    self.save("deferred",deferred())
    with self.assertRaisesRegex(MitProviderError,"deferral"):
      self.save("resume",approval(deferred_evidence_ref="forged"))
    with self.assertRaisesRegex(MitProviderError,"deferral"):
      self.save("resume",approval(expected_generation=1))
    with self.assertRaisesRegex(MitProviderError,"deferral"):
      self.save("resume",approval(prelim_sha="d"*40))
    self.assertIsNone(read_mit(self.backend,"resume",GUID,"main"))

  def test_restart_reads_prior_defer_and_revocation(self):
    self.save("deferred",deferred())
    self.save("resume",approval())
    self.save("resume",approval(approved=False,evidence_ref="revoke-2"))
    fresh=Backend()
    fresh.refs=dict(self.backend.refs)
    fresh.commits=dict(self.backend.commits)
    self.assertEqual(read_mit(fresh,"deferred",GUID,"main"),deferred())
    self.assertEqual(
      read_mit(fresh,"resume",GUID,"main")["approved"],False)
    with self.assertRaisesRegex(MitProviderError,"revoked"):
      record_mit(fresh,"resume",approval(),
                 verify_evidence=lambda record:True)

  def test_untrusted_authorization_never_publishes(self):
    with self.assertRaises(MitProviderError):
      self.save("resume",approval(),lambda record:False)
    self.assertFalse(self.backend.refs)

  def test_wrong_repository_and_generation_rejected(self):
    for value in (deferred(repository="Other/Repo"),
                  deferred(lease_generation=True),
                  deferred(reason="failed"),
                  deferred(evidence_ref="")):
      with self.subTest(value=value):
        with self.assertRaises(MitProviderError):
          self.save("deferred",value)

  def test_malformed_provider_read_refuses_silent_success(self):
    self.save("deferred",deferred())
    ref=next(iter(self.backend.refs))
    sha=self.backend.refs[ref]
    self.backend.commits[sha]["message"]="not an MIT record"
    with self.assertRaises(MitProviderError):
      read_mit(self.backend,"deferred",GUID,"main")

  def test_terminal_result_forbids_repeated_mit(self):
    with patch("adapters.repo_host_github_integration_terminal.read_terminal",
               return_value={"status":"integrated"}):
      with self.assertRaisesRegex(MitProviderError,"terminal"):
        self.save("deferred",deferred())


if __name__ == "__main__":
  unittest.main()
