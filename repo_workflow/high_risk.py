from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .current_work_store import CurrentWorkError, CurrentWorkStore
from .lifecycle_store import LifecycleStore
from .state_store import WriterIdentity
from .test_catalogue import load_test_catalogue


class HighRiskError(RuntimeError):
  pass


def associate_high_risk(
  root: Path,
  aliases,
  writer: WriterIdentity,
):
  root = Path(root).resolve()
  catalogue = load_test_catalogue(root)

  requested = tuple(aliases)
  if not requested:
    raise HighRiskError("at least one high-risk section is required")

  for name in requested:
    if not isinstance(name, str) or not name:
      raise HighRiskError("high-risk section names must be non-empty strings")

  # Validate all names before mutating any state.
  catalogue.expand_aliases(requested)

  current_store = CurrentWorkStore(root)
  current = current_store.read(validate_durable=True)
  reference = current.value.current
  if reference is None:
    raise HighRiskError("rwf high-risk requires an active current issue")

  lifecycle_store = LifecycleStore(root)
  lifecycle = lifecycle_store.read(reference.issue)
  if lifecycle.revision != reference.lifecycle_revision:
    raise CurrentWorkError(
      f"stale current lifecycle revision for issue {reference.issue}: "
      f"expected {reference.lifecycle_revision}, current {lifecycle.revision!r}"
    )

  merged = tuple(sorted(set(lifecycle.lifecycle.high_risk_aliases) | set(requested)))
  if merged == lifecycle.lifecycle.high_risk_aliases:
    return lifecycle

  updated = lifecycle_store.set_high_risk_aliases(
    reference.issue,
    merged,
    writer,
    lifecycle.revision,
  )

  updated_reference = replace(
    reference,
    lifecycle_revision=updated.revision,
  )
  value = replace(
    current.value,
    current=updated_reference,
    selected_issue=reference.issue,
    cache_lifecycle_revision=updated.revision,
  )
  current_store.replace(current.revision, value, writer)
  return updated
