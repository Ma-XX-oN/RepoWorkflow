#!/usr/bin/env python3
"""Publish terminal version refs only after canonical hosted result commit."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.hosted_terminal_publication import publish_hosted_terminal
from repo_workflow.hosted_terminal_binding import HostedTerminalError


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("stage")
  parser.add_argument("candidate")
  parser.add_argument("branch")
  parser.add_argument("invocation")
  parser.add_argument("run_id", type=int)
  args = parser.parse_args(argv)
  try:
    tag = publish_hosted_terminal(
      Path.cwd(), branch=args.branch, stage=args.stage,
      candidate=args.candidate, invocation=args.invocation,
      run_id=args.run_id,
    )
  except HostedTerminalError as error:
    print("hosted terminal publication rejected: " + str(error),
          file=sys.stderr)
    return 1
  if tag is None:
    print("INCOMPLETE hosted result: no terminal version tag")
  else:
    print("Immutable hosted terminal tag published: " + tag)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
