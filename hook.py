#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from repo_workflow.config import ConfigError
from repo_workflow.git import GitError
from repo_workflow.local_guards import (
  LocalGuardError,
  check_commit,
  check_push,
  check_rebase,
  install_hooks,
)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="RepoWorkflow local Git guard entry point")
  parser.add_argument("--root", default=".", help="consumer repository root")
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("commit")
  commands.add_parser("push")
  rebase = commands.add_parser("rebase")
  rebase.add_argument("upstream")
  rebase.add_argument("branch", nargs="?")
  install = commands.add_parser("install")
  install.add_argument("--force", action="store_true")
  return parser


def main(argv: list[str] | None = None) -> int:
  args = build_parser().parse_args(argv)
  root = Path(args.root).resolve()
  try:
    if args.command == "commit":
      check_commit(root)
    elif args.command == "push":
      check_push(root, sys.stdin.read())
    elif args.command == "rebase":
      check_rebase(root, args.upstream, args.branch)
    elif args.command == "install":
      for path in install_hooks(root, force=args.force):
        print(path)
    else:
      raise AssertionError("unreachable")
    return 0
  except (ConfigError, GitError, LocalGuardError, ValueError) as exc:
    print(f"RepoWorkflow local guard: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
