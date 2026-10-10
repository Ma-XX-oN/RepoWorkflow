#!/usr/bin/env python3
"""Safe authenticated negative provider-boundary probe for issue #97.

Execute the shipped CLI with GitHub's read-only token.  Refuse authority
before contacting any write endpoint.  No persistent fixture is created.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "repo-host-github.py"


def main() -> int:
  request = {
    "schema_version": 1, "operation": "issue.comment",
    "repository": "Ma-XX-oN/RepoWorkflow",
    "request_id": "issue97-negative-hosted-probe",
    "parameters": {
      "number": 2147483647, "body": "MUST NEVER BE PUBLISHED",
    },
  }
  result = subprocess.run(
    [sys.executable, str(ADAPTER)], input=json.dumps(request),
    capture_output=True, text=True, timeout=45, check=False,
  )
  if result.returncode == 0 or result.stdout:
    raise RuntimeError("unauthorized mutation appeared to succeed")
  response = json.loads(result.stderr)
  if response["error"] != "unauthorized":
    raise RuntimeError("authorization did not fail first")
  if response["request_id"] != request["request_id"]:
    raise RuntimeError("negative probe request identity changed")
  print(json.dumps({
    "result": "PASS", "operation": request["operation"],
    "expected": "unauthorized", "mutations": 0,
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
