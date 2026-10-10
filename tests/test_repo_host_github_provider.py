from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
import repo_host_github_provider as provider


SHA = "a" * 40
TREE = "b" * 40
RECORD = "c" * 40
REQUEST = {
  "schema_version": 1, "operation": "issue.comment",
  "repository": "owner/repo", "request_id": "once",
  "parameters": {"number": 2, "body": "comment"},
}


def response(value, code=0):
  return SimpleNamespace(
    returncode=code, stdout=json.dumps(value),
    stderr="provider output",
  )


class GitHubProviderTests(unittest.TestCase):

  def test_get_is_read_only_and_sends_no_payload(self):
    with patch.object(
      provider.subprocess, "run", return_value=response({"login": "actor"})
    ) as run:
      identity = provider.GitHubBackend("owner/repo").identity()
    self.assertEqual(identity["login"], "actor")
    self.assertEqual(run.call_args.args[0], [
      "gh", "api", "--method", "GET", "user",
    ])
    self.assertIsNone(run.call_args.kwargs["input"])

  def test_patch_uses_json_stdin_not_process_arguments(self):
    with patch.object(
      provider.subprocess, "run", return_value=response({"ok": True})
    ) as run:
      backend = provider.GitHubBackend("owner/repo")
      backend.patch("issues/2", {"title": "secret-sensitive-title"})
    args = run.call_args.args[0]
    self.assertEqual(args[:4], ["gh", "api", "--method", "PATCH"])
    self.assertEqual(args[-2:], ["--input", "-"])
    self.assertNotIn("secret-sensitive-title", " ".join(args))
    self.assertEqual(
      json.loads(run.call_args.kwargs["input"])["title"],
      "secret-sensitive-title",
    )

  def test_unknown_write_outcome_never_becomes_success(self):
    with patch.object(
      provider.subprocess, "run",
      side_effect=provider.subprocess.TimeoutExpired(["gh"], 30),
    ):
      with self.assertRaises(provider.ProviderError) as caught:
        provider.GitHubBackend("owner/repo").post(
          "issues/2/comments", {"body": "comment"}
        )
    self.assertEqual(caught.exception.code, "unknown_outcome")

  def test_persisted_reservation_is_checked_before_replay(self):
    backend = provider.GitHubBackend("owner/repo")
    ref = provider.reservation_ref(REQUEST)
    digest = provider.reservation_digest(REQUEST)
    records = {
      "": {"default_branch": "main"},
      "git/ref/heads/main": {
        "object": {"sha": SHA},
      },
      "git/commits/" + SHA: {"tree": {"sha": TREE}},
      "git/ref/tags/" + ref.split("/")[-1]: {
        "ref": ref, "object": {"sha": RECORD},
      },
      "git/commits/" + RECORD: {
        "message": "RWF-HOST-RESERVATION-V1 " + digest,
      },
    }
    with patch.object(backend, "get", side_effect=lambda path: records[path]):
      with patch.object(
        backend, "post",
        side_effect=[
          {"sha": RECORD},
          provider.ProviderError("provider_failure", "already exists"),
        ],
      ):
        self.assertFalse(backend.reserve(REQUEST))
      changed = {**REQUEST, "parameters": {
        "number": 2, "body": "other",
      }}
      with self.assertRaises(provider.ProviderError) as caught:
        backend.check_reservation(changed)
      self.assertEqual(caught.exception.code, "conflict")

  def test_new_reservation_is_atomic_ref_creation(self):
    backend = provider.GitHubBackend("owner/repo")
    values = {
      "": {"default_branch": "main"},
      "git/ref/heads/main": {"object": {"sha": SHA}},
      "git/commits/" + SHA: {"tree": {"sha": TREE}},
    }
    with patch.object(
      backend, "get", side_effect=lambda path: values[path]
    ):
      with patch.object(
        backend, "post", side_effect=[
          {"sha": RECORD}, {"ref": provider.reservation_ref(REQUEST)},
        ],
      ) as post:
        self.assertTrue(backend.reserve(REQUEST))
    self.assertEqual(post.call_args.args[0], "git/refs")
    self.assertEqual(
      post.call_args.args[1]["ref"],
      provider.reservation_ref(REQUEST),
    )


if __name__ == "__main__":
  unittest.main()
