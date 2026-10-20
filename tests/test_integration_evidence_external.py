"""Independent integration evidence verifier gate, positive and RED tests."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from adapters.repo_host_github_integration_evidence import (
  IntegrationEvidenceError, make_evidence_verifier,
)


class Backend:
  def identity(self):
    return {"login": "github-actions[bot]"}


SCRIPT = r'''#!PYTHON
import datetime
import hashlib
import json
import os
import sys
payload = json.load(sys.stdin)
request = payload["request"]
key = {"mit.deferred.record": "event",
       "mit.resume.record": "authorization",
       "attempt.record": "record",
       "retirement.record": "record"}[request["operation"]]
record = request["parameters"][key]
def digest(value):
  return hashlib.sha256(json.dumps(value,sort_keys=True,
    separators=(",",":")).encode()).hexdigest()
now = datetime.datetime.now(datetime.timezone.utc)
if os.environ.get("TEST_EVIDENCE_MODE") == "stale":
  now -= datetime.timedelta(minutes=4)
result = {
  "schema_version":1, "request_digest":digest(request),
  "record_digest":digest(record),
  "actor_id":payload["provider_actor"],
  "repository":request["repository"],"operation":request["operation"],
  "request_id":request["request_id"],"decision":"allow",
  "authority_ref":"external-verified-provider-fixture",
  "revocation_revision":2,
  "evaluated_at":now.strftime("%Y-%m-%dT%H:%M:%SZ"),
}
mode = os.environ.get("TEST_EVIDENCE_MODE")
if mode == "forged": result["record_digest"] = "0"*64
if mode == "foreign": result["actor_id"] = "attacker"
if mode == "revoked": result["decision"] = "deny"
if mode == "bad-revision": result["revocation_revision"] = "2"
print(json.dumps(result))
'''


class ExternalEvidenceTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.script = Path(self.tmp.name) / "external-verifier"
    self.script.write_text(
      SCRIPT.replace("#!PYTHON", "#!" + sys.executable),
      encoding="utf-8")
    self.script.chmod(self.script.stat().st_mode | stat.S_IXUSR)
    self.request = {
      "schema_version":2, "repository":"Example/Sandbox",
      "operation":"mit.deferred.record", "request_id":"grant-1",
      "parameters":{"guid":"guid-1", "destination":"main",
                    "event":{"proof":"test-only"}},
    }
    self.env = {"RWF_REPO_HOST_INTEGRATION_EVIDENCE_COMMAND":
                json.dumps([str(self.script)])}

  def check(self, mode=""):
    with patch.dict(os.environ, {**self.env,
                                 "TEST_EVIDENCE_MODE":mode}, clear=True):
      verifier = make_evidence_verifier(self.request, Backend())
      self.assertIsNotNone(verifier)
      return verifier(self.request["parameters"]["event"])

  def test_correct_external_fresh_evidence_passes(self):
    self.assertTrue(self.check())

  def test_forged_expired_revoked_or_wrong_actor_fail_closed(self):
    for mode in ("forged", "stale", "revoked", "foreign", "bad-revision"):
      with self.subTest(mode=mode):
        self.assertFalse(self.check(mode))

  def test_changed_record_is_not_granted(self):
    with patch.dict(os.environ, self.env, clear=True):
      verifier = make_evidence_verifier(self.request, Backend())
      self.assertFalse(verifier({"proof":"substituted"}))

  def test_no_configuration_has_no_authority(self):
    with patch.dict(os.environ, {}, clear=True):
      self.assertIsNone(make_evidence_verifier(self.request, Backend()))

  def test_relative_or_repo_local_command_cannot_issue_grant(self):
    for command in ("verifier", str(Path(__file__).resolve())):
      with self.subTest(command=command):
        with patch.dict(os.environ, {
            "RWF_REPO_HOST_INTEGRATION_EVIDENCE_COMMAND":
              json.dumps([command])}, clear=True):
          self.assertIsNone(make_evidence_verifier(self.request, Backend()))

  def test_identity_unknown_cannot_authorize(self):
    class Unknown:
      def identity(self):
        raise ValueError("no authenticated actor")
    with patch.dict(os.environ, self.env, clear=True):
      with self.assertRaises(IntegrationEvidenceError):
        make_evidence_verifier(self.request, Unknown())


if __name__ == "__main__":
  unittest.main()
