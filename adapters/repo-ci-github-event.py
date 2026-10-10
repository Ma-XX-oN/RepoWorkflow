#!/usr/bin/env python3
"""GitHub-owned event, capability and runner mapping for repo-ci contract v1.

The public function map_request accepts and returns only versioned repo-ci
envelopes. GitHub event vocabulary and runner labels stay inside this adapter.
"""
from __future__ import annotations

import json
import sys

EVENT_MODES = {
  "push": "automatic",
  "pull_request": "automatic",
  "workflow_dispatch": "manual",
  "schedule": "scheduled",
}
RUNNERS = {
  "linux": {"label": "ubuntu-latest", "capabilities": ("python", "shell", "linux")},
  "windows": {"label": "windows-latest", "capabilities": ("python", "shell", "windows")},
  "macos": {"label": "macos-latest", "capabilities": ("python", "shell", "macos")},
}
OPERATIONS = {"inspect-context", "resolve-capabilities", "prepare"}
FIELDS = {"contract_version", "operation", "invocation_id", "candidate", "requirements", "inputs"}


class InvalidRequest(ValueError):
  def __init__(self, code: str, detail: str):
    super().__init__(detail)
    self.code = code


def _nonempty(value: object) -> bool:
  return isinstance(value, str) and bool(value.strip())


def _string_array(value: object, label: str) -> list[str]:
  if not isinstance(value, list) or any(not _nonempty(x) for x in value):
    raise InvalidRequest("invalid-request", f"{label} must be a string array")
  if len(set(value)) != len(value):
    raise InvalidRequest("invalid-request", f"{label} contains duplicates")
  return value


def _envelope(request: object) -> dict:
  if not isinstance(request, dict):
    raise InvalidRequest("invalid-request", "request must be an object")
  if set(request) != FIELDS:
    raise InvalidRequest("invalid-request", "request fields are missing or unknown")
  if request["contract_version"] != 1 or isinstance(request["contract_version"], bool):
    raise InvalidRequest("unsupported-version", "unsupported contract version")
  if request["operation"] not in OPERATIONS:
    raise InvalidRequest("unsupported-operation", "unsupported adapter operation")
  if not _nonempty(request["invocation_id"]):
    raise InvalidRequest("invalid-request", "invocation_id is required")
  candidate = request["candidate"]
  if not isinstance(candidate, dict) or set(candidate) != {"repository", "commit", "base"}:
    raise InvalidRequest("invalid-request", "candidate requires repository, commit and base")
  if any(not _nonempty(x) for x in candidate.values()):
    raise InvalidRequest("invalid-request", "candidate identities must be nonempty strings")
  requirements = request["requirements"]
  if not isinstance(requirements, dict) or set(requirements) != {"stages", "capabilities", "artifacts"}:
    raise InvalidRequest("invalid-request", "requirements require stages, capabilities and artifacts")
  for key in ("stages", "capabilities", "artifacts"):
    _string_array(requirements[key], key)
  if not isinstance(request["inputs"], dict):
    raise InvalidRequest("invalid-request", "inputs must be an object")
  return request


def _context(inputs: dict) -> tuple[str, str, str]:
  allowed = {"event", "platform", "mode"}
  if set(inputs) - allowed:
    raise InvalidRequest("invalid-request", "unexpected execution-context input")
  event = inputs.get("event")
  platform = inputs.get("platform")
  if event not in EVENT_MODES:
    raise InvalidRequest("invalid-request", "unsupported event")
  if platform not in RUNNERS:
    raise InvalidRequest("capability-unavailable", "unsupported runner platform")
  mode = EVENT_MODES[event]
  if inputs.get("mode") is not None and inputs["mode"] != mode:
    raise InvalidRequest("invalid-request", "execution mode conflicts with event")
  return mode, platform, RUNNERS[platform]["label"]


def _resolve(inputs: dict, required: list[str]) -> tuple[str, str, list[str]]:
  if set(inputs) - {"platform", "available_capabilities"}:
    raise InvalidRequest("invalid-request", "unexpected capability input")
  platform = inputs.get("platform")
  if platform not in RUNNERS:
    raise InvalidRequest("capability-unavailable", "unsupported runner platform")
  available = set(RUNNERS[platform]["capabilities"])
  if "available_capabilities" in inputs:
    declared = set(_string_array(inputs["available_capabilities"], "available_capabilities"))
    if not declared <= available:
      raise InvalidRequest("invalid-request", "capabilities conflict with runner")
    available = declared
  unmet = sorted(set(required) - available)
  if unmet:
    raise InvalidRequest("capability-unavailable", "required capabilities unavailable: " + ", ".join(unmet))
  return platform, RUNNERS[platform]["label"], sorted(available)


def map_request(request: object) -> dict:
  # Preserve opaque invocation and candidate identities, including on failure.
  response = {
    "contract_version": 1,
    "operation": request.get("operation") if isinstance(request, dict) else None,
    "invocation_id": request.get("invocation_id") if isinstance(request, dict) else None,
    "candidate": request.get("candidate") if isinstance(request, dict) else None,
    "status": "error",
    "observations": {},
    "diagnostics": [],
    "artifacts": [],
  }
  try:
    envelope = _envelope(request)
    inputs = envelope["inputs"]
    required = envelope["requirements"]["capabilities"]
    operation = envelope["operation"]
    if operation == "inspect-context":
      mode, platform, runner = _context(inputs)
      response["observations"] = {
        "mode": mode, "platform": platform, "runner_ref": runner,
      }
    elif operation == "resolve-capabilities":
      platform, runner, available = _resolve(inputs, required)
      response["observations"] = {
        "platform": platform, "runner_ref": runner,
        "available_capabilities": available, "unmet_requirements": [],
      }
    else:
      if set(inputs) != {"event", "platform"}:
        raise InvalidRequest("invalid-request", "prepare requires event and platform")
      mode, platform, runner = _context(inputs)
      _, _, available = _resolve({"platform": platform}, required)
      response["observations"] = {
        "mode": mode, "platform": platform, "runner_ref": runner,
        "available_capabilities": available, "prepared": True,
        "unmet_prerequisites": [],
      }
    response["status"] = "ok"
  except InvalidRequest as exc:
    response["diagnostics"] = [{"code": exc.code, "message": str(exc)}]
  return response


def main() -> int:
  try:
    raw = json.load(sys.stdin)
  except (ValueError, UnicodeError):
    print(json.dumps({"status": "error", "diagnostics": [
      {"code": "invalid-request", "message": "invalid JSON"}]}))
    return 2
  response = map_request(raw)
  print(json.dumps(response, separators=(",", ":"), sort_keys=True))
  return 0 if response["status"] == "ok" else 2


if __name__ == "__main__":
  sys.exit(main())
