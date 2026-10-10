#!/usr/bin/env python3
"""Real signed-authority negative against private sandbox; no mock provider."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
adapter = ROOT / "adapters/repo-host-github.py"
helper = ROOT / "scripts/probe-repo-host-github-private-sandbox-deny.py"
spec = importlib.util.spec_from_file_location("rwf97_snapshot", helper)
snapshot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot_module)


def main() -> int:
  before = snapshot_module.snapshot()
  request = {
    "schema_version": 1, "operation": "issue.comment",
    "repository": "Ma-XX-oN/Disposable-000",
    "request_id": "rwf97-signed-authority-refusal",
    "parameters": {
      "number": 1,
      "body": "MUST NOT POST UNDER REVOKED OR EXPIRED POLICY",
    },
  }
  result = subprocess.run(
    [sys.executable, str(adapter)],
    input=json.dumps(request), text=True, capture_output=True,
    timeout=90, check=False,
  )
  if result.returncode == 0 or result.stdout:
    raise RuntimeError("invalid standing grant unexpectedly authorized")
  response = json.loads(result.stderr)
  if response.get("error") != "unauthorized" or response.get(
    "request_id"
  ) != request["request_id"]:
    raise RuntimeError("expected scoped signed authority denial")
  if snapshot_module.snapshot() != before:
    raise RuntimeError("signed denial changed remote provider state")
  print(json.dumps({
    "result": "PASS", "reason": "invalid_current_signed_authority",
    "provider_state_unchanged": True, "adapter": "shipped Python",
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
