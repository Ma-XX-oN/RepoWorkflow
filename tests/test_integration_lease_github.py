"""Repository-scoped lease CAS tests: one destination, one writer at a time."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adapters.repo_host_github_integration_lease import (
  LeaseProviderError, _ref, cas_lease, read_lease,
)


G = "11111111-1111-4111-8111-111111111111"
H = "22222222-2222-4222-8222-222222222222"
PARENT = "a" * 40
TREE = "b" * 40


class NotFound(Exception):
  code = "not_found"


class Backend:
  def __init__(self, repository="Org/Repo"):
    self.repository = repository
    self.refs = {}
    self.commits = {}

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
    raise AssertionError("unexpected backend read: " + route)


def request(operation, *, expected_generation=0, expected_holder=None,
            expected_guid=None, holder="worker-a", guid=G, name="claim-1",
            destination="main"):
  return {
    "schema_version": 2, "repository": "Org/Repo",
    "operation": operation, "request_id": name,
    "parameters": {
      "destination": destination, "expected_generation": expected_generation,
      "expected_holder": expected_holder, "expected_guid": expected_guid,
      "holder": holder, "guid": guid,
    },
  }


class GitCAS:
  """Model atomic advertised refs, a checkout and one exact leased Git push."""
  def __init__(self, backend):
    self.backend = backend
    self.fetch_sha = PARENT
    self.pending = None
    self.counter = 0
    self.reject_push = False
    self.lost_reply = False
    self.commands = []

  def __call__(self, argv, **kwargs):
    self.commands.append(argv)
    args = argv[3:]
    def result(code=0, out=""):
      return SimpleNamespace(returncode=code, stdout=out, stderr="")
    if args[:2] == ["remote", "get-url"]:
      return result(out="https://github.com/Org/Repo.git\n")
    if args[:2] == ["fetch", "--no-tags"]:
      target = args[3]
      self.fetch_sha = self.backend.refs.get(target, PARENT)
      return result()
    if args[:2] == ["rev-parse", "--verify"]:
      return result(out=(TREE if args[2] == "FETCH_HEAD^{tree}"
                         else self.fetch_sha) + "\n")
    if "commit-tree" in args:
      self.counter += 1
      sha = format(self.counter + 10, "040x")
      self.pending = (sha, args[args.index("-m") + 1])
      return result(out=sha + "\n")
    if args[0] == "push":
      lease = next(x for x in args if x.startswith("--force-with-lease="))
      _, conditional = lease.split("=", 1)
      ref, expected = conditional.rsplit(":", 1)
      sha, _ = self.pending
      if self.reject_push or self.backend.refs.get(ref, "") != expected:
        return result(code=1)
      self.backend.refs[ref] = sha
      self.backend.commits[sha] = {"message": self.pending[1]}
      if self.lost_reply:
        return result(code=1)
      return result()
    raise AssertionError("unexpected git operation: " + repr(args))


class LeaseAcceptance(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()
    self.git = GitCAS(self.backend)

  def write(self, **updates):
    p = request("lease.cas", **updates)
    with patch("adapters.repo_host_github_integration_lease.subprocess.run",
               side_effect=self.git):
      return cas_lease(self.backend, p, Path("/isolated"), "origin")

  def test_absent_lease_is_unowned_generation_zero(self):
    self.assertEqual(read_lease(self.backend, "main"), {
      "destination": "main", "generation": 0, "holder": None, "guid": None})

  def test_claim_release_restart_readback(self):
    status, result = self.write()
    self.assertEqual((status, result["generation"]), ("applied", 1))
    self.assertEqual(result["guid"], G)
    # A second process reads the same repository-scoped provider record.
    self.assertEqual(read_lease(self.backend, "main"), result)
    status, result = self.write(expected_generation=1,
      expected_holder="worker-a", expected_guid=G, holder=None, guid=None,
      name="release-1")
    self.assertEqual((status, result["generation"]), ("applied", 2))
    self.assertIsNone(result["holder"])
    status, result = self.write(expected_generation=2, holder="worker-b",
                                guid=H, name="claim-2")
    self.assertEqual((status, result["generation"]), ("applied", 3))
    self.assertEqual(result["holder"], "worker-b")

  def test_stale_competing_writer_cannot_take_lease(self):
    self.write()
    before = dict(self.backend.refs)
    with self.assertRaisesRegex(LeaseProviderError, "stale"):
      self.write(holder="worker-b", guid=H, name="competing-claim")
    self.assertEqual(self.backend.refs, before)

  def test_replayed_exact_request_is_idempotent(self):
    self.write()
    before = dict(self.backend.refs)
    status, result = self.write()
    self.assertEqual((status, result["generation"]), ("unchanged", 1))
    self.assertEqual(before, self.backend.refs)

  def test_ambiguous_reply_reconciles_only_exact_record(self):
    self.git.lost_reply = True
    status, result = self.write()
    self.assertEqual((status, result["generation"]), ("unchanged", 1))
    self.assertEqual(len(self.backend.refs), 1)

  def test_rejected_push_is_not_success(self):
    self.git.reject_push = True
    with self.assertRaisesRegex(LeaseProviderError, "rejected"):
      self.write()
    self.assertEqual(self.backend.refs, {})

  def test_different_destination_and_repository_have_separate_refs(self):
    self.assertNotEqual(_ref("Org/Repo", "main"),
                        _ref("Org/Repo", "issue-23"))
    self.assertNotEqual(_ref("Org/Repo", "main"),
                        _ref("Org/Other", "main"))

  def test_forged_record_and_changed_repository_refused(self):
    self.write()
    ref = _ref("Org/Repo", "main")
    commit = self.backend.commits[self.backend.refs[ref]]
    record = json.loads(commit["message"].split(" ", 1)[1])
    record["repository"] = "Org/Evil"
    commit["message"] = ("RWF-INTEGRATION-LEASE-V2 " +
                         json.dumps(record, sort_keys=True,
                                    separators=(",", ":")))
    with self.assertRaisesRegex(LeaseProviderError, "record"):
      read_lease(self.backend, "main")

  def test_remote_scope_denied_before_writes(self):
    with patch("adapters.repo_host_github_integration_lease.subprocess.run",
               return_value=SimpleNamespace(returncode=0, stdout=
                 "https://github.com/Org/Other.git\n", stderr="")):
      with self.assertRaisesRegex(LeaseProviderError, "repository differs"):
        cas_lease(self.backend, request("lease.cas"),
                  Path("/isolated"), "origin")


if __name__ == "__main__":
  unittest.main()
