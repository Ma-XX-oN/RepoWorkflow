from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.dependency_migration_certification import (
  CERTIFICATION_RELATIVE,
  MANIFEST_RELATIVE,
  DependencyMigrationCertificationError,
  certification_value,
  require_dependency_migration_certified,
)
from repo_workflow.git import git_checkout_bytes


class DependencyMigrationCertificationTests(unittest.TestCase):
  def git(self, root: Path, *args: str) -> bytes:
    return subprocess.run(
      ["git", *args], cwd=root, check=True, capture_output=True,
    ).stdout

  def init_repo(self, root: Path) -> None:
    self.git(root, "init", "-q", "-b", "main")
    self.git(root, "config", "user.name", "Fixture")
    self.git(root, "config", "user.email", "fixture@example.invalid")
    self.git(root, "commit", "-qm", "initial", "--allow-empty")

  def write_manifest(self, root: Path, text: str = "{}\n") -> Path:
    path = root / MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

  def commit_manifest(self, root: Path) -> None:
    self.git(root, "add", "--", MANIFEST_RELATIVE.as_posix())
    self.git(root, "commit", "-qm", "commit migration manifest")

  def test_repository_without_manifest_requires_no_certification(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      require_dependency_migration_certified(root)

  def test_manifest_without_certification_fails_closed(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.write_manifest(root)
      self.commit_manifest(root)
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "not certified",
      ):
        require_dependency_migration_certified(root)

  def test_certification_must_match_current_manifest_digest(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.write_manifest(root, '{"a":1}\n')
      self.commit_manifest(root)
      value = certification_value(root, "a" * 64)
      path = root / CERTIFICATION_RELATIVE
      path.write_text(json.dumps(value), encoding="utf-8")
      self.write_manifest(root, '{"a":2}\n')
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "worktree does not match Git checkout",
      ):
        require_dependency_migration_certified(root)

  def test_valid_certification_allows_bootstrap_authority(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.write_manifest(root, '{"reviewed":true}\n')
      self.commit_manifest(root)
      provider_digest = hashlib.sha256(b"provider-readback").hexdigest()
      value = certification_value(root, provider_digest)
      path = root / CERTIFICATION_RELATIVE
      path.write_text(json.dumps(value), encoding="utf-8")
      require_dependency_migration_certified(root)
      committed = self.git(root, "show", "HEAD:" + MANIFEST_RELATIVE.as_posix())
      self.assertEqual(
        value["manifest_sha256"],
        hashlib.sha256(committed).hexdigest(),
      )

  def test_invalid_provider_readback_digest_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.write_manifest(root)
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "lowercase SHA-256",
      ):
        certification_value(root, "not-a-digest")

  def test_deleted_committed_manifest_fails_closed(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      manifest = self.write_manifest(root)
      self.commit_manifest(root)
      value = certification_value(root, "b" * 64)
      (root / CERTIFICATION_RELATIVE).write_text(
        json.dumps(value), encoding="utf-8",
      )
      manifest.unlink()
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError, "worktree does not match",
      ):
        require_dependency_migration_certified(root)

  def test_untracked_manifest_cannot_claim_certification(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.write_manifest(root)
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError, "uncommitted migration manifest",
      ):
        require_dependency_migration_certified(root)

  def test_modified_certificate_digest_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.write_manifest(root)
      self.commit_manifest(root)
      value = certification_value(root, "b" * 64)
      value["manifest_sha256"] = "0" * 64
      (root / CERTIFICATION_RELATIVE).write_text(
        json.dumps(value), encoding="utf-8",
      )
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError, "does not match current manifest",
      ):
        require_dependency_migration_certified(root)

  def test_materialized_crlf_checkout_is_not_a_certificate_mismatch(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.init_repo(root)
      self.git(root, "config", "core.autocrlf", "true")
      manifest = self.write_manifest(root, '{\n  "a": 1,\n  "b": 2\n}\n')
      self.commit_manifest(root)
      raw = self.git(root, "show", "HEAD:" + MANIFEST_RELATIVE.as_posix())
      checkout = git_checkout_bytes(root, MANIFEST_RELATIVE)
      self.assertIsNotNone(checkout)
      manifest.write_bytes(checkout)
      value = certification_value(root, "b" * 64)
      self.assertEqual(value["manifest_sha256"], hashlib.sha256(raw).hexdigest())
      (root / CERTIFICATION_RELATIVE).write_text(
        json.dumps(value), encoding="utf-8",
      )
      require_dependency_migration_certified(root)

  def test_non_git_directory_fails_closed(self):
    with tempfile.TemporaryDirectory() as td:
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "cannot verify Git-committed migration manifest",
      ):
        require_dependency_migration_certified(Path(td))


if __name__ == "__main__":
  unittest.main()
