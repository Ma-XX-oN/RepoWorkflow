from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .state_store import (
  JsonRecordStore,
  StateStoreError,
  WriterIdentity,
  _acquire_lock,
  _release_lock,
)


TRANSACTION_SCHEMA_VERSION = 1
TRANSACTION_KEY_PREFIX = "transactions"


class TransactionError(RuntimeError):
  """Raised when a recoverable semantic transaction cannot proceed safely."""


@dataclass(frozen=True)
class StateReference:
  domain: str
  key: str
  revision: int
  identity: str | None = None

  def __post_init__(self) -> None:
    if not isinstance(self.domain, str) or not self.domain.strip():
      raise TransactionError("state-reference domain must be non-empty text")
    if not isinstance(self.key, str) or not self.key.strip():
      raise TransactionError("state-reference key must be non-empty text")
    if isinstance(self.revision, bool) or not isinstance(self.revision, int):
      raise TransactionError("state-reference revision must be an integer")
    if self.revision < 0:
      raise TransactionError("state-reference revision must be non-negative")
    if self.identity is not None and (
      not isinstance(self.identity, str) or not self.identity.strip()
    ):
      raise TransactionError("state-reference identity must be non-empty text")


@dataclass(frozen=True)
class StateWrite:
  domain: str
  key: str
  value: dict

  def __post_init__(self) -> None:
    if not isinstance(self.domain, str) or not self.domain.strip():
      raise TransactionError("state-write domain must be non-empty text")
    if not isinstance(self.key, str) or not self.key.strip():
      raise TransactionError("state-write key must be non-empty text")
    if not isinstance(self.value, dict):
      raise TransactionError("state-write value must be an object")


class SemanticTransactionCoordinator:
  """Durable write-ahead coordinator for multi-domain semantic transitions."""

  def __init__(self, transaction_store: JsonRecordStore):
    self.store = transaction_store

  def prepare(
    self,
    transaction_id: str,
    read_set: Iterable[StateReference],
    write_set: Iterable[StateWrite],
    writer: WriterIdentity,
  ) -> dict:
    key = _transaction_key(transaction_id)
    reads = tuple(read_set)
    writes = tuple(write_set)
    if not reads:
      raise TransactionError("transaction read set must not be empty")
    if not writes:
      raise TransactionError("transaction write set must not be empty")
    _unique_members(reads, "read")
    _unique_members(writes, "write")
    value = {
      "transaction_schema_version": TRANSACTION_SCHEMA_VERSION,
      "transaction_id": transaction_id,
      "status": "prepared",
      "read_set": [_reference_value(item) for item in reads],
      "write_set": [_write_value(item) for item in writes],
    }
    lock = self.store.root / ".transaction-coordinator.lock"
    _acquire_lock(lock)
    try:
      self._ensure_no_prepared_conflict(transaction_id, reads, writes)
      return self.store.create(key, value, writer)
    except StateStoreError as error:
      raise TransactionError(str(error)) from error
    finally:
      _release_lock(lock)

  def read(self, transaction_id: str) -> dict:
    try:
      record = self.store.read(_transaction_key(transaction_id))
    except StateStoreError as error:
      raise TransactionError(str(error)) from error
    _validate_transaction(record["value"], transaction_id)
    return record

  def commit(
    self,
    transaction_id: str,
    writer: WriterIdentity,
    validate: Callable[[tuple[StateReference, ...]], bool],
    materialize: Callable[[tuple[StateWrite, ...]], None],
  ) -> dict:
    record = self.read(transaction_id)
    value = record["value"]
    status = value["status"]
    reads = _references(value["read_set"])
    writes = _writes(value["write_set"])
    if status == "aborted":
      raise TransactionError(f"transaction is aborted: {transaction_id}")
    if status == "committed":
      materialize(writes)
      return record
    if not validate(reads):
      self._abort_record(record, writer, "stale authoritative read set")
      raise TransactionError(
        f"transaction read set is stale; transaction aborted: {transaction_id}"
      )
    committed_value = dict(value)
    committed_value["status"] = "committed"
    try:
      committed = self.store.replace(
        _transaction_key(transaction_id),
        record["revision"],
        committed_value,
        writer,
      )
    except StateStoreError as error:
      raise TransactionError(str(error)) from error
    materialize(writes)
    return committed

  def abort(
    self,
    transaction_id: str,
    writer: WriterIdentity,
    reason: str,
  ) -> dict:
    if not isinstance(reason, str) or not reason.strip():
      raise TransactionError("abort reason must be non-empty text")
    record = self.read(transaction_id)
    if record["value"]["status"] == "committed":
      raise TransactionError(f"committed transaction cannot abort: {transaction_id}")
    if record["value"]["status"] == "aborted":
      return record
    return self._abort_record(record, writer, reason)

  def recover(
    self,
    transaction_id: str,
    writer: WriterIdentity,
    validate: Callable[[tuple[StateReference, ...]], bool],
    materialize: Callable[[tuple[StateWrite, ...]], None],
  ) -> dict:
    record = self.read(transaction_id)
    value = record["value"]
    if value["status"] == "committed":
      materialize(_writes(value["write_set"]))
      return record
    if value["status"] == "aborted":
      return record
    reads = _references(value["read_set"])
    if not validate(reads):
      return self._abort_record(record, writer, "stale authoritative read set")
    return record

  def _ensure_no_prepared_conflict(
    self,
    transaction_id: str,
    reads: tuple[StateReference, ...],
    writes: tuple[StateWrite, ...],
  ) -> None:
    for path in (self.store.root / TRANSACTION_KEY_PREFIX).glob("*.json"):
      key = path.relative_to(self.store.root).with_suffix("").as_posix()
      try:
        record = self.store.read(key)
      except StateStoreError as error:
        raise TransactionError(str(error)) from error
      value = record["value"]
      existing_id = value.get("transaction_id")
      if existing_id == transaction_id:
        continue
      _validate_transaction(value, existing_id)
      if value["status"] != "prepared":
        continue
      existing_reads = _references(value["read_set"])
      existing_writes = _writes(value["write_set"])
      if _sets_conflict(reads, writes, existing_reads, existing_writes):
        raise TransactionError(
          "conflicting prepared transaction requires recovery first: "
          f"{existing_id}"
        )

  def _abort_record(
    self,
    record: dict,
    writer: WriterIdentity,
    reason: str,
  ) -> dict:
    value = dict(record["value"])
    value["status"] = "aborted"
    value["abort_reason"] = reason
    try:
      return self.store.replace(
        record["key"],
        record["revision"],
        value,
        writer,
      )
    except StateStoreError as error:
      raise TransactionError(str(error)) from error


def _transaction_key(transaction_id: str) -> str:
  if not isinstance(transaction_id, str) or not transaction_id:
    raise TransactionError("transaction id must be non-empty text")
  allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
  if transaction_id[0] not in set("abcdefghijklmnopqrstuvwxyz0123456789"):
    raise TransactionError("transaction id must start with lowercase alphanumeric")
  if any(character not in allowed for character in transaction_id):
    raise TransactionError(
      "transaction id must use lowercase alphanumeric, dot, underscore, or hyphen"
    )
  return f"{TRANSACTION_KEY_PREFIX}/{transaction_id}"


def _sets_conflict(
  reads: tuple[StateReference, ...],
  writes: tuple[StateWrite, ...],
  existing_reads: tuple[StateReference, ...],
  existing_writes: tuple[StateWrite, ...],
) -> bool:
  read_members = {(item.domain, item.key) for item in reads}
  write_members = {(item.domain, item.key) for item in writes}
  existing_read_members = {
    (item.domain, item.key) for item in existing_reads
  }
  existing_write_members = {
    (item.domain, item.key) for item in existing_writes
  }
  return bool(
    write_members & (existing_read_members | existing_write_members)
    or existing_write_members & read_members
  )


def _unique_members(items, kind: str) -> None:
  members = [(item.domain, item.key) for item in items]
  if len(members) != len(set(members)):
    raise TransactionError(f"transaction {kind} set contains duplicate members")


def _reference_value(item: StateReference) -> dict:
  return {
    "domain": item.domain,
    "key": item.key,
    "revision": item.revision,
    "identity": item.identity,
  }


def _write_value(item: StateWrite) -> dict:
  return {
    "domain": item.domain,
    "key": item.key,
    "value": item.value,
  }


def _references(values: list[dict]) -> tuple[StateReference, ...]:
  return tuple(
    StateReference(
      item["domain"],
      item["key"],
      item["revision"],
      item.get("identity"),
    )
    for item in values
  )


def _writes(values: list[dict]) -> tuple[StateWrite, ...]:
  return tuple(
    StateWrite(item["domain"], item["key"], item["value"])
    for item in values
  )


def _validate_transaction(value: dict, transaction_id: str) -> None:
  if not isinstance(value, dict):
    raise TransactionError(f"transaction value is invalid: {transaction_id}")
  allowed = {
    "transaction_schema_version",
    "transaction_id",
    "status",
    "read_set",
    "write_set",
    "abort_reason",
  }
  if not set(value).issubset(allowed):
    raise TransactionError(f"transaction has unsupported fields: {transaction_id}")
  required = allowed - {"abort_reason"}
  if not required.issubset(value):
    raise TransactionError(f"transaction is incomplete: {transaction_id}")
  if value["transaction_schema_version"] != TRANSACTION_SCHEMA_VERSION:
    raise TransactionError(f"unsupported transaction schema: {transaction_id}")
  if value["transaction_id"] != transaction_id:
    raise TransactionError(f"transaction identity mismatch: {transaction_id}")
  if value["status"] not in {"prepared", "committed", "aborted"}:
    raise TransactionError(f"transaction status is invalid: {transaction_id}")
  if not isinstance(value["read_set"], list) or not value["read_set"]:
    raise TransactionError(f"transaction read set is invalid: {transaction_id}")
  if not isinstance(value["write_set"], list) or not value["write_set"]:
    raise TransactionError(f"transaction write set is invalid: {transaction_id}")
  reads = _references(value["read_set"])
  writes = _writes(value["write_set"])
  _unique_members(reads, "read")
  _unique_members(writes, "write")
  if value["status"] == "aborted":
    reason = value.get("abort_reason")
    if not isinstance(reason, str) or not reason.strip():
      raise TransactionError(f"aborted transaction lacks reason: {transaction_id}")
  elif "abort_reason" in value:
    raise TransactionError(
      f"non-aborted transaction has abort reason: {transaction_id}"
    )
