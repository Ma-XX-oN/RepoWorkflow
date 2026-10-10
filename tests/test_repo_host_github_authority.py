from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
import repo_host_github_authority as authority
from repo_host_github_provider import ProviderError


REQUEST = {
  "schema_version": 1, "operation": "issue.update",
  "repository": "owner/repo", "request_id": "one",
  "parameters": {"number": 3, "title": "Changed"},
}


class Backend:
  def identity(self):
    return {"login": "operator"}


def decision(request=REQUEST, actor="operator", outcome="allow"):
  digest = hashlib.sha256(
    json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
  ).hexdigest()
  return {
    "schema_version": 1, "operation": request["operation"],
    "repository": request["repository"],
    "request_id": request["request_id"],
    "scope_digest": digest,
    "actor_id": actor, "decision": outcome,
    "authority_ref": "verified-grant-1",
    "grant_kind": "standing", "max_uses": None,
  }


class AuthorizationBoundaryTests(unittest.TestCase):

  def test_unconfigured_verifier_never_authorizes(self):
    with patch.dict("os.environ", {}, clear=True):
      with self.assertRaises(ProviderError) as caught:
        authority.authorize(REQUEST, Backend())
    self.assertEqual(caught.exception.code, "unauthorized")

  def test_verifier_needs_absolute_executable(self):
    for config in ['["./verifier"]', '["python"]', '["/../bad"]', "null"]:
      with self.subTest(config=config):
        with patch.dict("os.environ", {
          "RWF_REPO_HOST_AUTH_COMMAND": config,
        }):
          self.assertIsNone(authority.verifier_command())

  def test_windows_absolute_verifier_path_is_supported(self):
    with patch.dict("os.environ", {
      "RWF_REPO_HOST_AUTH_COMMAND":
        json.dumps(["C:\\\\trusted\\\\verify.exe"]),
    }):
      self.assertIsNotNone(authority.verifier_command())

  def test_verified_actor_and_scope_are_accepted(self):
    response = SimpleNamespace(
      returncode=0, stdout=json.dumps(decision()), stderr="",
    )
    with patch.dict("os.environ", {
      "RWF_REPO_HOST_AUTH_COMMAND": '["/opt/trusted/check-auth"]',
    }):
      with patch.object(
        authority.subprocess, "run", return_value=response
      ) as run:
        result = authority.authorize(REQUEST, Backend())
    self.assertEqual(result["actor_id"], "operator")
    self.assertEqual(run.call_args.args[0], ["/opt/trusted/check-auth"])
    self.assertEqual(
      json.loads(run.call_args.kwargs["input"])["request_id"], "one"
    )

  def test_untrusted_verdicts_cannot_authorize(self):
    cases = [
      decision(actor="wrong"),
      decision(outcome="deny"),
      {**decision(), "scope_digest": "wrong"},
      {**decision(), "request_id": "other"},
      {**decision(), "repository": "other/repo"},
      {**decision(), "operation": "issue.comment"},
      {**decision(), "authority_ref": ""},
      {**decision(), "extra": "claim"},
      {**decision(), "grant_kind": "one_time"},
      {**decision(), "max_uses": 1},
    ]
    with patch.dict("os.environ", {
      "RWF_REPO_HOST_AUTH_COMMAND": '["/opt/trusted/check-auth"]',
    }):
      for value in cases:
        with self.subTest(value=value):
          response = SimpleNamespace(
            returncode=0, stdout=json.dumps(value), stderr="",
          )
          with patch.object(
            authority.subprocess, "run", return_value=response
          ):
            with self.assertRaises(ProviderError) as caught:
              authority.authorize(REQUEST, Backend())
            self.assertEqual(caught.exception.code, "unauthorized")

  def test_verifier_failure_never_mutates(self):
    with patch.dict("os.environ", {
      "RWF_REPO_HOST_AUTH_COMMAND": '["/opt/trusted/check-auth"]',
    }):
      for response in [
        SimpleNamespace(returncode=1, stdout="", stderr="token"),
        SimpleNamespace(returncode=0, stdout="{", stderr=""),
      ]:
        with patch.object(
          authority.subprocess, "run", return_value=response
        ):
          with self.assertRaises(ProviderError) as caught:
            authority.authorize(REQUEST, Backend())
          self.assertEqual(caught.exception.code, "unauthorized")


if __name__ == "__main__":
  unittest.main()
