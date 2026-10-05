from __future__ import annotations

from collections.abc import MutableMapping
import os
from pathlib import Path
import uuid

from .git import git
from .runtime_identity import (
  RuntimeIdentityError,
  SESSION_ID_ENV,
  WRITER_ID_ENV,
  runtime_writer_identity,
)


def ensure_public_runtime_identity(
  root: Path,
  environment: MutableMapping[str, str] | None = None,
):
  """Provision ordinary public-CLI provenance without weakening core semantics."""
  if environment is None:
    environment = os.environ

  present = {
    name: name in environment
    for name in (WRITER_ID_ENV, SESSION_ID_ENV)
  }
  if all(present.values()):
    return runtime_writer_identity(environment)
  if any(present.values()):
    missing = [name for name, value in present.items() if not value]
    raise RuntimeIdentityError(
      "missing required runtime identity input: " + ", ".join(missing)
    )

  writer = _local_writer_id(Path(root).resolve())
  session = "session-" + uuid.uuid4().hex
  environment[WRITER_ID_ENV] = writer
  environment[SESSION_ID_ENV] = session
  return runtime_writer_identity(environment)


def _local_writer_id(root: Path) -> str:
  common = git(root, "rev-parse", "--git-common-dir").stdout.strip()
  common_dir = Path(common)
  if not common_dir.is_absolute():
    common_dir = (root / common_dir).resolve()
  path = common_dir / "repoworkflow" / "runtime-writer-id"
  path.parent.mkdir(parents=True, exist_ok=True)

  try:
    value = path.read_text(encoding="utf-8").strip()
  except FileNotFoundError:
    value = "local-" + uuid.uuid4().hex
    try:
      with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value + "\n")
    except FileExistsError:
      value = path.read_text(encoding="utf-8").strip()

  if not value or any(char.isspace() for char in value):
    raise RuntimeIdentityError(
      f"malformed clone-local runtime writer identity: {path}"
    )
  return value
