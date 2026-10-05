from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .dependency_migration_manifest import (
  DependencyMigrationManifest,
  load_dependency_migration_manifest,
)
from .ticket_dependency_adapter import (
  TicketDependencyError,
  read_ticket_dependencies,
  replace_ticket_dependencies,
  resolve_dependency_config,
)


class DependencyMigrationError(RuntimeError):
  pass


@dataclass(frozen=True)
class DependencyMigrationDiff:
  issue: int
  desired: tuple[int, ...]
  provider: tuple[int, ...]
  status: str

  def to_json_value(self) -> dict:
    return {
      "issue": self.issue,
      "desired": list(self.desired),
      "provider": list(self.provider),
      "status": self.status,
    }


def compare_manifest_to_provider(
  root: Path,
  manifest: DependencyMigrationManifest,
) -> tuple[DependencyMigrationDiff, ...]:
  config = resolve_dependency_config(root)
  result: list[DependencyMigrationDiff] = []
  for issue in sorted(manifest.issues):
    desired = manifest.issues[issue].blocked_by
    try:
      provider = tuple(
        read_ticket_dependencies(root, config, issue)
      )
    except TicketDependencyError as error:
      raise DependencyMigrationError(
        f"cannot read native dependencies for #{issue}: {error}"
      ) from error
    if provider == desired:
      status = "MATCH"
    elif not provider:
      status = "DESTINATION_EMPTY"
    else:
      status = "CONFLICT"
    result.append(
      DependencyMigrationDiff(issue, desired, provider, status)
    )
  return tuple(result)


def apply_manifest_to_provider(
  root: Path,
  manifest: DependencyMigrationManifest,
  *,
  reconcile: bool = False,
) -> tuple[DependencyMigrationDiff, ...]:
  before = compare_manifest_to_provider(root, manifest)
  conflicts = tuple(item for item in before if item.status == "CONFLICT")
  if conflicts and not reconcile:
    rendered = ", ".join(f"#{item.issue}" for item in conflicts)
    raise DependencyMigrationError(
      "native dependency migration has conflicts; "
      f"rerun with explicit reconciliation after review: {rendered}"
    )

  config = resolve_dependency_config(root)
  for item in before:
    if item.status == "MATCH":
      continue
    try:
      confirmed = tuple(
        replace_ticket_dependencies(
          root,
          config,
          item.issue,
          item.desired,
        )
      )
    except TicketDependencyError as error:
      raise DependencyMigrationError(
        f"native dependency mutation failed for #{item.issue}: {error}"
      ) from error
    if confirmed != item.desired:
      raise DependencyMigrationError(
        f"native dependency mutation for #{item.issue} returned "
        "an unexpected confirmed set"
      )

  after = compare_manifest_to_provider(root, manifest)
  mismatches = tuple(item for item in after if item.status != "MATCH")
  if mismatches:
    rendered = ", ".join(f"#{item.issue}" for item in mismatches)
    raise DependencyMigrationError(
      "post-migration provider readback does not match manifest: "
      f"{rendered}"
    )
  return after


def report_value(
  manifest: DependencyMigrationManifest,
  diffs: tuple[DependencyMigrationDiff, ...],
  *,
  mode: str,
) -> dict:
  counts = {
    "MATCH": 0,
    "DESTINATION_EMPTY": 0,
    "CONFLICT": 0,
  }
  for item in diffs:
    counts[item.status] += 1
  return {
    "schema_version": 1,
    "migration_id": manifest.migration_id,
    "repository": manifest.repository,
    "mode": mode,
    "counts": counts,
    "issues": [item.to_json_value() for item in diffs],
  }


def write_report(path: Path, value: dict) -> None:
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
    json.dumps(value, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
  )


def load_manifest_for_root(
  root: Path,
  manifest_path: Path | None = None,
) -> DependencyMigrationManifest:
  path = (
    Path(manifest_path)
    if manifest_path is not None
    else root
    / ".repoworkflow"
    / "migrations"
    / "native-dependencies-v1.json"
  )
  manifest = load_dependency_migration_manifest(path)
  return manifest
