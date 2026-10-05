from __future__ import annotations

import hashlib
import json
from pathlib import Path


MANIFEST_RELATIVE = (
  Path(".repoworkflow")
  / "migrations"
  / "native-dependencies-v1.json"
)
CERTIFICATION_RELATIVE = (
  Path(".repoworkflow")
  / "migrations"
  / "native-dependencies-v1.certified.json"
)


class DependencyMigrationCertificationError(RuntimeError):
  pass


def manifest_digest(path: Path) -> str:
  return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_dependency_migration_certified(root: Path) -> None:
  root = Path(root).resolve()
  manifest_path = root / MANIFEST_RELATIVE
  if not manifest_path.is_file():
    return

  certification_path = root / CERTIFICATION_RELATIVE
  if not certification_path.is_file():
    raise DependencyMigrationCertificationError(
      "native ticket dependency migration is not certified for this "
      "repository; run/reconcile migration before bootstrapping canonical "
      "relationships"
    )

  try:
    value = json.loads(certification_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise DependencyMigrationCertificationError(
      f"cannot read dependency migration certification: {error}"
    ) from error

  required = {
    "schema_version",
    "migration_id",
    "repository",
    "manifest_sha256",
    "provider_readback_sha256",
  }
  if not isinstance(value, dict) or set(value) != required:
    raise DependencyMigrationCertificationError(
      "dependency migration certification has missing/unsupported fields"
    )
  if value["schema_version"] != 1:
    raise DependencyMigrationCertificationError(
      "unsupported dependency migration certification schema"
    )
  if value["migration_id"] != "repoworkflow-native-dependencies-v1":
    raise DependencyMigrationCertificationError(
      "dependency migration certification identifies the wrong migration"
    )
  if value["repository"] != "Ma-XX-oN/RepoWorkflow":
    raise DependencyMigrationCertificationError(
      "dependency migration certification identifies the wrong repository"
    )
  if value["manifest_sha256"] != manifest_digest(manifest_path):
    raise DependencyMigrationCertificationError(
      "dependency migration certification does not match current manifest"
    )
  readback = value["provider_readback_sha256"]
  if (
    not isinstance(readback, str)
    or len(readback) != 64
    or any(char not in "0123456789abcdef" for char in readback)
  ):
    raise DependencyMigrationCertificationError(
      "dependency migration certification has invalid provider readback digest"
    )


def certification_value(
  root: Path,
  provider_readback_sha256: str,
) -> dict:
  if (
    len(provider_readback_sha256) != 64
    or any(char not in "0123456789abcdef" for char in provider_readback_sha256)
  ):
    raise DependencyMigrationCertificationError(
      "provider readback digest must be lowercase SHA-256"
    )
  root = Path(root).resolve()
  return {
    "schema_version": 1,
    "migration_id": "repoworkflow-native-dependencies-v1",
    "repository": "Ma-XX-oN/RepoWorkflow",
    "manifest_sha256": manifest_digest(root / MANIFEST_RELATIVE),
    "provider_readback_sha256": provider_readback_sha256,
  }
