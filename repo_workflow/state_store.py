from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable


RECORD_SCHEMA_VERSION = 1
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
IDENTITY_RE = re.compile(r"^[^\s]+$")


class StateStoreError(RuntimeError):
  """Raised when generic RWF state storage is invalid or conflicted."""


@dataclass(frozen=True)
class WriterIdentity:
  writer_id: str
  session_id: str

  def __post_init__(self) -> None:
    for name, value in (
      ("writer_id", self.writer_id),
      ("session_id", self.session_id),
    ):
      if not isinstance(value, str) or not IDENTITY_RE.fullmatch(value):
        raise StateStoreError(f"{name} must be non-empty text without whitespace")


class JsonRecordStore:
  """Versioned atomic JSON records with record-scoped compare-and-swap."""

  def __init__(self, root: Path):
    self.root = Path(root).resolve()

  def read(self, key: str) -> dict:
    path = self._path(key)
    value = _read_json(path)
    _validate_record(value, key)
    return value

  def create(self, key: str, value: dict, writer: WriterIdentity) -> dict:
    key = _key(key)
    _payload(value)
    path = self._path(key)
    lock = _lock_path(path)
    _acquire_lock(lock)
    try:
      if path.exists():
        raise StateStoreError(f"record already exists: {key}")
      record = _record(key, 0, value, writer, None)
      _write_json_atomic(path, record)
      return record
    finally:
      _release_lock(lock)

  def replace(
    self,
    key: str,
    expected_revision: int,
    value: dict,
    writer: WriterIdentity,
  ) -> dict:
    key = _key(key)
    _revision(expected_revision)
    _payload(value)
    path = self._path(key)
    lock = _lock_path(path)
    _acquire_lock(lock)
    try:
      current = self.read(key)
      revision = current["revision"]
      if revision != expected_revision:
        raise StateStoreError(
          f"stale record revision for {key}: "
          f"expected {expected_revision}, current {revision}"
        )
      record = _record(key, revision + 1, value, writer, revision)
      _write_json_atomic(path, record)
      return record
    finally:
      _release_lock(lock)

  def _path(self, key: str) -> Path:
    key = _key(key)
    path = (self.root / f"{key}.json").resolve()
    try:
      path.relative_to(self.root)
    except ValueError as error:
      raise StateStoreError(f"record key escapes store: {key!r}") from error
    return path


def durable_store(repository_root: Path) -> JsonRecordStore:
  return JsonRecordStore(Path(repository_root).resolve() / ".repoworkflow" / "state")


def clone_local_store(repository_root: Path) -> JsonRecordStore:
  from .git import git

  root = Path(repository_root).resolve()
  common = Path(git(root, "rev-parse", "--git-common-dir").stdout.strip())
  if not common.is_absolute():
    common = (root / common).resolve()
  return JsonRecordStore(common / "repoworkflow" / "state")


def _record(
  key: str,
  revision: int,
  value: dict,
  writer: WriterIdentity,
  previous_revision: int | None,
) -> dict:
  return {
    "schema_version": RECORD_SCHEMA_VERSION,
    "key": key,
    "revision": revision,
    "previous_revision": previous_revision,
    "writer_id": writer.writer_id,
    "session_id": writer.session_id,
    "value": value,
  }


def _key(value: str) -> str:
  if not isinstance(value, str) or not KEY_RE.fullmatch(value):
    raise StateStoreError(f"invalid record key: {value!r}")
  if any(part in {"", ".", ".."} for part in value.split("/")):
    raise StateStoreError(f"invalid record key: {value!r}")
  return value


def _revision(value: int) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    raise StateStoreError("expected revision must be non-negative")
  return value


def _payload(value: dict) -> None:
  if not isinstance(value, dict):
    raise StateStoreError("record value must be an object")
  try:
    json.dumps(value, allow_nan=False)
  except (TypeError, ValueError) as error:
    raise StateStoreError("record value must be JSON-serializable") from error


def _validate_record(value: dict, key: str) -> None:
  if set(value) != {
    "schema_version",
    "key",
    "revision",
    "previous_revision",
    "writer_id",
    "session_id",
    "value",
  }:
    raise StateStoreError(f"record has unsupported fields: {key}")
  if value["schema_version"] != RECORD_SCHEMA_VERSION:
    raise StateStoreError(f"unsupported record schema version: {key}")
  if value["key"] != key:
    raise StateStoreError(f"record key mismatch: {key}")
  revision = _revision(value["revision"])
  previous = value["previous_revision"]
  if revision == 0:
    if previous is not None:
      raise StateStoreError(f"revision-zero record has predecessor: {key}")
  elif previous != revision - 1:
    raise StateStoreError(f"record revision chain is invalid: {key}")
  WriterIdentity(value["writer_id"], value["session_id"])
  _payload(value["value"])


def _read_json(path: Path) -> dict:
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as error:
    raise StateStoreError(f"record is missing: {path}") from error
  except json.JSONDecodeError as error:
    raise StateStoreError(f"record is invalid JSON: {path}") from error
  if not isinstance(value, dict):
    raise StateStoreError(f"record must be an object: {path}")
  return value


def _write_json_atomic(
  path: Path,
  value: dict,
  replace: Callable[[Path, Path], None] | None = None,
) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  if replace is None:
    replace = os.replace
  descriptor, temporary = tempfile.mkstemp(
    prefix=f".{path.name}.",
    suffix=".tmp",
    dir=path.parent,
  )
  temporary_path = Path(temporary)
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
      json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
      handle.write("\n")
      handle.flush()
      os.fsync(handle.fileno())
    replace(temporary_path, path)
  finally:
    try:
      temporary_path.unlink()
    except FileNotFoundError:
      pass


def _lock_path(path: Path) -> Path:
  return path.with_name(f".{path.name}.lock")


def _acquire_lock(path: Path, timeout: float = 5.0) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  deadline = time.monotonic() + timeout
  while True:
    try:
      path.mkdir()
      return
    except FileExistsError:
      if time.monotonic() >= deadline:
        raise StateStoreError(f"record lock is busy: {path}")
      time.sleep(0.01)


def _release_lock(path: Path) -> None:
  try:
    path.rmdir()
  except FileNotFoundError:
    pass
