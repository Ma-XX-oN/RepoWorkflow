from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.dependency_migration_certification import (
  CERTIFICATION_RELATIVE,
  MANIFEST_RELATIVE,
  DependencyMigrationCertificationError,
  certification_value,
  require_dependency_migration_certified,
)


class DependencyMigrationCertificationTests(unittest.TestCase):
  def write_manifest(self, root: Path, text: str = "{}\n") -> Path:
    path = root / MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

  def test_repository_without_manifest_requires_no_certification(self):
    with tempfile.TemporaryDirectory() as td:
      require_dependency_migration_certified(Path(td))

  def test_manifest_without_certification_fails_closed(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.write_manifest(root)
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "not certified",
      ):
        require_dependency_migration_certified(root)

  def test_certification_must_match_current_manifest_digest(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.write_manifest(root, '{"a":1}\n')
      value = certification_value(root, "a" * 64)
      path = root / CERTIFICATION_RELATIVE
      path.write_text(json.dumps(value), encoding="utf-8")
      self.write_manifest(root, '{"a":2}\n')
      with self.assertRaisesRegex(
        DependencyMigrationCertificationError,
        "does not match current manifest",
      ):
        require_dependency_migration_certified(root)

  def test_valid_certification_allows_bootstrap_authority(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      manifest = self.write_manifest(root, '{"reviewed":true}\n')
      provider_digest = hashlib.sha256(b"provider-readback").hexdigest()
      value = certification_value(root, provider_digest)
      path = root / CERTIFICATION_RELATIVE
      path.write_text(json.dumps(value), encoding="utf-8")
      require_dependency_migration_certified(root)
      self.assertEqual(
        value["manifest_sha256"],
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
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


if __name__ == "__main__":
  unittest.main()
