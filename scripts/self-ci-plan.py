#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.self_ci import plan_self_ci


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--event", required=True)
  parser.add_argument("--ref", default="")
  parser.add_argument("--head-ref", default="")
  parser.add_argument("--classification", required=True)
  parser.add_argument("--requested-tier", default="")
  args = parser.parse_args()
  plan = plan_self_ci(
    ROOT,
    event=args.event,
    ref=args.ref,
    head_ref=args.head_ref,
    classification=args.classification,
    requested_tier=args.requested_tier,
  )
  print(json.dumps(plan.to_json_value(), separators=(",", ":")))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
