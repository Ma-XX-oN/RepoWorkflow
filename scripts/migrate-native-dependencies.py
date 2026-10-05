#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from repo_workflow.dependency_migration import (  # noqa: E402
  DependencyMigrationError,
  apply_manifest_to_provider,
  compare_manifest_to_provider,
  load_manifest_for_root,
  report_value,
  write_report,
)
from repo_workflow.dependency_migration_manifest import (  # noqa: E402
  DependencyMigrationManifestError,
)


def parser() -> argparse.ArgumentParser:
  result = argparse.ArgumentParser(
    description="Compare/apply reviewed native ticket dependency migration.",
  )
  result.add_argument(
    "--root",
    type=Path,
    default=Path.cwd(),
    help="Repository root (default: current directory).",
  )
  result.add_argument(
    "--manifest",
    type=Path,
    help="Migration manifest path.",
  )
  mode = result.add_mutually_exclusive_group()
  mode.add_argument(
    "--apply",
    action="store_true",
    help="Apply only empty-destination/matching migration state.",
  )
  mode.add_argument(
    "--reconcile",
    action="store_true",
    help="Explicitly replace conflicting provider dependency sets.",
  )
  result.add_argument(
    "--report",
    type=Path,
    help="Write deterministic JSON report to this path.",
  )
  return result


def main(arguments: list[str]) -> int:
  args = parser().parse_args(arguments)
  root = args.root.resolve()
  try:
    manifest = load_manifest_for_root(root, args.manifest)
    if manifest.repository != "Ma-XX-oN/RepoWorkflow":
      raise DependencyMigrationError(
        "migration manifest is not for Ma-XX-oN/RepoWorkflow"
      )

    if args.apply or args.reconcile:
      diffs = apply_manifest_to_provider(
        root,
        manifest,
        reconcile=args.reconcile,
      )
      mode = "reconcile" if args.reconcile else "apply"
    else:
      diffs = compare_manifest_to_provider(root, manifest)
      mode = "dry-run"

    report = report_value(manifest, diffs, mode=mode)
    if args.report is not None:
      write_report(args.report, report)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0
  except (DependencyMigrationError, DependencyMigrationManifestError) as error:
    print(f"RepoWorkflow dependency migration error: {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
