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


def _committed_manifest(root: Path) -> tuple[bytes, bytes] | None:
  """Return Git's raw committed blob and separate checkout-materialized bytes."""
  from .git import GitError, git_bytes, git_checkout_bytes
  relative = MANIFEST_RELATIVE.as_posix()
  try:
    record = git_bytes(root, "ls-tree", "-z", "HEAD", "--", relative).stdout
    if not record:
      return None
    if not record.endswith(b"\0") or record.count(b"\0") != 1:
      raise DependencyMigrationCertificationError("ambiguous committed migration manifest")
    header, separator, name = record[:-1].partition(b"\t")
    fields = header.split(b" ")
    if (separator != b"\t" or name != relative.encode("utf-8")
        or len(fields) != 3 or fields[0] not in (b"100644", b"100755")
        or fields[1] != b"blob"):
      raise DependencyMigrationCertificationError("committed migration manifest is not a regular Git file")
    raw = git_bytes(root, "show", "HEAD:" + relative).stdout
    checkout = git_checkout_bytes(root, relative)
    if checkout is None:
      raise DependencyMigrationCertificationError("committed migration manifest cannot be checked out")
    return raw, checkout
  except (GitError, OSError, UnicodeError) as error:
    raise DependencyMigrationCertificationError(
      "cannot verify Git-committed migration manifest"
    ) from error


def require_dependency_migration_certified(root: Path) -> None:
  root = Path(root).resolve()
  manifest_path = root / MANIFEST_RELATIVE
  committed = _committed_manifest(root)
  if committed is None:
    if manifest_path.exists() or manifest_path.is_symlink():
      raise DependencyMigrationCertificationError(
        "uncommitted migration manifest is not certified"
      )
    return
  raw, checkout = committed
  try:
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.read_bytes() != checkout:
      raise DependencyMigrationCertificationError(
        "committed migration manifest worktree does not match Git checkout"
      )
  except OSError as error:
    raise DependencyMigrationCertificationError("cannot read committed migration manifest worktree") from error

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
  if value["manifest_sha256"] != hashlib.sha256(raw).hexdigest():
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
  committed = _committed_manifest(root)
  if committed is None:
    raise DependencyMigrationCertificationError("no Git-committed migration manifest to certify")
  raw, checkout = committed
  path = root / MANIFEST_RELATIVE
  if path.is_symlink() or not path.is_file() or path.read_bytes() != checkout:
    raise DependencyMigrationCertificationError("committed migration manifest worktree does not match Git checkout")
  return {
    "schema_version": 1,
    "migration_id": "repoworkflow-native-dependencies-v1",
    "repository": "Ma-XX-oN/RepoWorkflow",
    "manifest_sha256": hashlib.sha256(raw).hexdigest(),
    "provider_readback_sha256": provider_readback_sha256,
  }
