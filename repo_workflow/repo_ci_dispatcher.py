"""Provider-neutral repo-ci dispatcher (issue #91).

The configured executable is the only provider-specific boundary.  The
dispatcher validates the v1 envelope and forwards its original bytes.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any


OPERATIONS = frozenset({
  "inspect-context", "resolve-capabilities", "prepare", "execute",
  "publish", "fetch", "check-policy",
})
ERRORS = frozenset({
  "invalid-request", "unsupported-version", "unsupported-operation",
  "capability-unavailable", "prerequisite-unavailable",
  "execution-unavailable", "transport-failed", "identity-mismatch",
  "integrity-failed", "internal-error",
})
FIELDS = frozenset({
  "contract_version", "operation", "invocation_id", "candidate",
  "requirements", "inputs",
})
RESULT_FIELDS = frozenset({
  "contract_version", "operation", "invocation_id", "candidate",
  "status", "observations", "diagnostics", "artifacts",
})


class RepoCiError(RuntimeError):
  def __init__(self, code: str, message: str):
    assert code in ERRORS
    self.code = code
    super().__init__(message)


def _object(value: Any, name: str) -> dict:
  if not isinstance(value, dict):
    raise RepoCiError("invalid-request", f"{name} must be an object")
  return value


def _nonempty(value: Any, name: str) -> None:
  if not isinstance(value, str) or not value:
    raise RepoCiError("invalid-request", f"{name} is required")


def validate_request(value: Any, operation: str) -> dict:
  request = _object(value, "request")
  if set(request) != FIELDS:
    raise RepoCiError("invalid-request", "incorrect request envelope fields")
  version = request["contract_version"]
  if type(version) is not int or version != 1:
    raise RepoCiError("unsupported-version", "unsupported contract version")
  if request["operation"] != operation or operation not in OPERATIONS:
    raise RepoCiError("unsupported-operation", "invalid operation")
  _nonempty(request["invocation_id"], "invocation_id")
  candidate = _object(request["candidate"], "candidate")
  if not candidate:
    raise RepoCiError("invalid-request", "candidate is required")
  if not all(isinstance(k, str) and k for k in candidate):
    raise RepoCiError("invalid-request", "invalid candidate identity")
  requirements = _object(request["requirements"], "requirements")
  if not all(isinstance(k, str) for k in requirements):
    raise RepoCiError("invalid-request", "invalid requirements")
  _object(request["inputs"], "inputs")
  return request



def _pairs(items: list[tuple[str, Any]]) -> dict:
  result = {}
  for key, value in items:
    if key in result:
      raise ValueError("duplicate JSON key")
    result[key] = value
  return result


def _reject_constant(value: str) -> None:
  raise ValueError("non-standard JSON constant")


def _parse_json(value: bytes) -> Any:
  return json.loads(
    value, object_pairs_hook=_pairs, parse_constant=_reject_constant,
  )

def _config(root: Path) -> list[str]:
  path = root / ".ci" / "repo-ci.json"
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, ValueError) as exc:
    raise RepoCiError(
      "prerequisite-unavailable", "repo-ci adapter configuration unavailable"
    ) from exc
  if not isinstance(value, dict) or set(value) != {"schema", "command"}:
    raise RepoCiError("invalid-request", "invalid adapter configuration")
  if type(value["schema"]) is not int or value["schema"] != 1:
    raise RepoCiError("unsupported-version", "invalid adapter config schema")
  command = value["command"]
  if not isinstance(command, list) or not command or not all(
    isinstance(x, str) and x and "\x00" not in x for x in command
  ):
    raise RepoCiError("invalid-request", "invalid adapter command")
  return command


def _result(value: Any, request: dict) -> dict:
  response = _object(value, "response")
  if set(response) != RESULT_FIELDS:
    raise RepoCiError("internal-error", "invalid adapter response fields")
  for name in ("contract_version", "operation", "invocation_id", "candidate"):
    if response[name] != request[name]:
      raise RepoCiError("identity-mismatch", f"mismatched {name}")
  if type(response["contract_version"]) is not int:
    raise RepoCiError("identity-mismatch", "invalid result version")
  if not isinstance(response["status"], str) or (
    response["status"] not in {"ok", "error"}
  ):
    raise RepoCiError("internal-error", "invalid adapter status")
  if not isinstance(response["observations"], dict):
    raise RepoCiError("internal-error", "invalid observations")
  if not isinstance(response["diagnostics"], list):
    raise RepoCiError("internal-error", "invalid diagnostics")
  if not isinstance(response["artifacts"], list):
    raise RepoCiError("internal-error", "invalid artifacts")
  if response["status"] == "error":
    if not any(
      isinstance(item, dict)
      and isinstance(item.get("code"), str)
      and item["code"] in ERRORS
      for item in response["diagnostics"]
    ):
      raise RepoCiError("internal-error", "missing semantic error code")
  return response


def dispatch(root: Path, operation: str, raw: bytes) -> dict:
  if operation not in OPERATIONS:
    raise RepoCiError("unsupported-operation", "unknown operation")
  try:
    request = validate_request(_parse_json(raw), operation)
  except (UnicodeDecodeError, ValueError) as exc:
    raise RepoCiError("invalid-request", "malformed JSON request") from exc
  engine_root = Path(__file__).resolve().parents[1]
  config_root = root
  if (
    not (root / ".ci" / "repo-ci.json").exists()
    and (root / "RepoWorkflow").resolve() == engine_root
  ):
    config_root = engine_root
  command = _config(config_root)
  try:
    result = subprocess.run(
      [*command, operation],
      input=raw,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      cwd=config_root,
      timeout=120,
      check=False,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    raise RepoCiError("transport-failed", "adapter invocation failed") from exc
  if result.returncode != 0:
    try:
      error = _parse_json(result.stderr)
      if (
        isinstance(error, dict)
        and isinstance(error.get("code"), str)
        and error["code"] in ERRORS
      ):
        raise RepoCiError(error["code"], "adapter rejected request")
    except (ValueError, UnicodeDecodeError):
      pass
    raise RepoCiError("transport-failed", "adapter returned failure")
  try:
    response = _parse_json(result.stdout)
  except (UnicodeDecodeError, ValueError) as exc:
    raise RepoCiError("internal-error", "invalid adapter JSON") from exc
  return _result(response, request)



def error_envelope(
  raw: bytes, operation: str, error: RepoCiError,
) -> dict | None:
  try:
    request = validate_request(_parse_json(raw), operation)
  except (RepoCiError, ValueError, UnicodeDecodeError):
    return None
  return {
    "contract_version": 1,
    "operation": request["operation"],
    "invocation_id": request["invocation_id"],
    "candidate": request["candidate"],
    "status": "error",
    "observations": {},
    "diagnostics": [{"code": error.code, "message": str(error)}],
    "artifacts": [],
  }

def main(argv: list[str] | None = None) -> int:
  words = list(sys.argv[1:] if argv is None else argv)
  if len(words) != 1:
    print(json.dumps({
      "code": "invalid-request", "message": "expected one operation"
    }), file=sys.stderr)
    return 2
  raw = sys.stdin.buffer.read()
  try:
    value = dispatch(Path.cwd(), words[0], raw)
  except RepoCiError as exc:
    error = error_envelope(raw, words[0], exc)
    if error is not None:
      print(json.dumps(error, separators=(",", ":")))
    else:
      print(json.dumps({
        "code": exc.code, "message": str(exc)
      }, separators=(",", ":")), file=sys.stderr)
    return 2
  print(json.dumps(value, separators=(",", ":")))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
