#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repo_workflow.orchestrate import run_series


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--command", action="append", required=True)
  parser.add_argument("--continue-on-failure", action="store_true")
  args = parser.parse_args()
  commands = [json.loads(value) for value in args.command]
  results = run_series(commands, continue_on_failure=args.continue_on_failure)
  for result in results:
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
  return 0 if all(result.returncode == 0 for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
