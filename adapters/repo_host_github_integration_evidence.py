"""Independent external evidence authority for integration-host v2 writes.

The verifier executable must live outside the untrusted RepoWorkflow checkout.
This is a consumer of independent evidence, never an issuer of approval.
Absent, stale, revoked, mismatched or unreadable authority is a hard refusal.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


class IntegrationEvidenceError(RuntimeError):
  """Independent provider evidence authority is absent or unverified."""


_COMMAND_ENV = "RWF_REPO_HOST_INTEGRATION_EVIDENCE_COMMAND"
_RESPONSE_FIELDS = {
  "schema_version", "request_digest", "record_digest",
  "actor_id", "repository", "operation", "request_id",
  "decision", "authority_ref", "revocation_revision", "evaluated_at",
}
_KEY_BY_OP = {
  "attempt.record": "record",
  "destination.accept": "record",
  "retirement.record": "record",
  "mit.deferred.record": "event",
  "mit.resume.record": "authorization",
}


def _digest(value):
  return hashlib.sha256(json.dumps(
    value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _configured_command():
  raw = os.environ.get(_COMMAND_ENV)
  if not raw:
    return None
  try:
    command = json.loads(raw)
  except (TypeError, ValueError):
    return None
  if type(command) is not list or len(command) not in (1, 2):
    return None
  workspace = Path(__file__).resolve().parents[1]
  project_checkout = Path.cwd().resolve()
  for element in command:
    if (type(element) is not str or not element
        or not os.path.isabs(element)
        or ".." in element.replace("\\", "/").split("/")):
      return None
    lexical = Path(element)
    target = lexical.resolve()
    if any(root == candidate or root in candidate.parents
           for root in (workspace, project_checkout)
           for candidate in (lexical, target)):
      return None
  return command


def make_evidence_verifier(request, backend):
  """Return a bound verifier or None, never a fabricated PASS callback."""
  command = _configured_command()
  if command is None:
    return None
  operation = request["operation"]
  key = _KEY_BY_OP.get(operation)
  if key is None:
    return None
  try:
    actor = backend.identity()["login"]
  except Exception as error:
    raise IntegrationEvidenceError("provider actor identity UNKNOWN") from error
  if type(actor) is not str or not actor:
    raise IntegrationEvidenceError("authenticated provider actor invalid")
  expected_record = request["parameters"][key]
  expected_request_digest = _digest(request)
  expected_record_digest = _digest(expected_record)

  def verify(record):
    if record != expected_record:
      return False
    payload = {"schema_version": 1, "request": request,
               "provider_actor": actor}
    try:
      result = subprocess.run(
        command, input=json.dumps(payload), capture_output=True,
        text=True, encoding="utf-8", errors="strict",
        check=False, timeout=30,
      )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
      return False
    if result.returncode or not result.stdout or len(result.stdout) > 4096:
      return False
    try:
      answer = json.loads(result.stdout)
    except (TypeError, ValueError):
      return False
    if type(answer) is not dict or set(answer) != _RESPONSE_FIELDS:
      return False
    expected = {
      "schema_version": 1, "request_digest": expected_request_digest,
      "record_digest": expected_record_digest,
      "actor_id": actor, "repository": request["repository"],
      "operation": operation, "request_id": request["request_id"],
      "decision": "allow",
    }
    if any(type(answer[k]) is not type(v) or answer[k] != v
           for k, v in expected.items()):
      return False
    if (type(answer["authority_ref"]) is not str
        or not answer["authority_ref"].strip()
        or type(answer["revocation_revision"]) is not int
        or answer["revocation_revision"] < 0
        or type(answer["evaluated_at"]) is not str):
      return False
    try:
      stamp = datetime.strptime(
        answer["evaluated_at"], "%Y-%m-%dT%H:%M:%SZ",
      ).replace(tzinfo=timezone.utc)
    except ValueError:
      return False
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    return 0 <= age <= 60

  return verify
