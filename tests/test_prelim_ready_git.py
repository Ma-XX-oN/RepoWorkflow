"""Provider-atomic create-only PRELIM publication acceptance.

Git push --force-with-lease on an existing equal-SHA ref can be a no-op
success. This test deliberately uses provider POST /git/refs instead.
"""
import unittest
from repo_workflow.prelim_ready import (
  ReadyPublicationError, create_ready_ref_provider,
)

GUID = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/PRELIM-issue-123/main-{GUID}"
SHA = "a"*40


class Missing(Exception):
  code = "not_found"


class Backend:
  def __init__(self):
    self.refs = {}
    self.posts = []
    self.ambiguous = False

  def get(self, route):
    name = "refs/" + route.removeprefix("git/ref/")
    if name not in self.refs:
      raise Missing()
    return {"ref": name, "object": {"sha": self.refs[name]}}

  def post(self, route, value):
    self.posts.append((route, value))
    if value["ref"] in self.refs:
      raise ValueError("already exists")
    self.refs[value["ref"]] = value["sha"]
    if self.ambiguous:
      raise TimeoutError("lost response")
    return {"ref": value["ref"], "object": {"sha": value["sha"]}}


class PrelimReadyProviderTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()

  def create(self, ref=REF, sha=SHA):
    return create_ready_ref_provider(self.backend, ref, sha, "req-1")

  def test_first_create_and_readback(self):
    self.assertTrue(self.create())
    self.assertEqual(self.backend.refs[REF], SHA)
    self.assertEqual(len(self.backend.posts), 1)

  def test_existing_identical_sha_is_not_new_publication(self):
    self.backend.refs[REF] = SHA
    with self.assertRaisesRegex(ReadyPublicationError, "already"):
      self.create()
    self.assertEqual(self.backend.posts, [])

  def test_existing_different_sha_is_not_mutated(self):
    self.backend.refs[REF] = "b"*40
    with self.assertRaises(ReadyPublicationError):
      self.create()
    self.assertEqual(self.backend.refs[REF], "b"*40)

  def test_lost_reply_is_unknown_not_proof_of_create(self):
    self.backend.ambiguous = True
    with self.assertRaisesRegex(ReadyPublicationError, "UNKNOWN"):
      self.create()
    self.assertEqual(self.backend.refs[REF], SHA)

  def test_non_prelim_or_malformed_ref_rejected(self):
    for name in ("refs/heads/main",
      "refs/heads/PRELIM-issue-0/main-" + GUID,
      "refs/heads/PRELIM-issue-123/../main-" + GUID,
      "refs/heads/PRELIM-issue-123/main-not-a-guid"):
      with self.subTest(name=name):
        with self.assertRaises(ReadyPublicationError):
          self.create(ref=name)
    self.assertEqual(self.backend.posts, [])


if __name__ == "__main__":
  unittest.main()
