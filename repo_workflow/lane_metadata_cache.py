from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .issue_metadata import (
  IssueMetadataError,
  IssueMetadataStore,
  refresh_issue_metadata,
)
from .repo_info_adapter import resolve_info_config
from .state_store import WriterIdentity


@dataclass(frozen=True)
class MetadataAcquisition:
  issues: tuple[int, ...]
  provider_reads: tuple[int, ...]


def ensure_lane_metadata(
  root: Path,
  issues: tuple[str | int, ...],
  writer: WriterIdentity,
  *,
  refresh: bool = False,
) -> MetadataAcquisition:
  normalized = tuple(sorted({int(value) for value in issues}))
  try:
    snapshot = IssueMetadataStore(root).read()
    current = snapshot.issues
  except IssueMetadataError as error:
    if "record is missing:" not in str(error):
      raise
    current = {}

  if refresh:
    scope = normalized
  else:
    scope = tuple(
      number
      for number in normalized
      if number not in current or not current[number].display_complete
    )

  if scope:
    refresh_issue_metadata(
      root,
      resolve_info_config(root),
      writer,
      scope,
    )

  return MetadataAcquisition(
    issues=normalized,
    provider_reads=scope,
  )
