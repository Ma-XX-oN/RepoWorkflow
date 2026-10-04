from __future__ import annotations

from collections.abc import Mapping
import os

from .state_store import StateStoreError, WriterIdentity


WRITER_ID_ENV = "RWF_WRITER_ID"
SESSION_ID_ENV = "RWF_SESSION_ID"


class RuntimeIdentityError(RuntimeError):
  """Raised when required runtime mutation provenance is unavailable."""


def runtime_writer_identity(
  environment: Mapping[str, str] | None = None,
) -> WriterIdentity:
  """Return the explicit writer/session identity for a mutating transition."""
  if environment is None:
    environment = os.environ

  missing = [
    name
    for name in (WRITER_ID_ENV, SESSION_ID_ENV)
    if name not in environment
  ]
  if missing:
    raise RuntimeIdentityError(
      "missing required runtime identity input: " + ", ".join(missing)
    )

  try:
    return WriterIdentity(
      writer_id=environment[WRITER_ID_ENV],
      session_id=environment[SESSION_ID_ENV],
    )
  except StateStoreError as error:
    raise RuntimeIdentityError(f"malformed runtime identity: {error}") from error
