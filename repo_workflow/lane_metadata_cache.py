from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lane_diagnostics import LaneDiagnostics
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
  diagnostics: LaneDiagnostics | None = None,
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

  if diagnostics is not None:
    diagnostics.hit("metadata", len(normalized) - len(scope))
    diagnostics.miss("metadata", len(scope))

  if scope:
    config = resolve_info_config(root)
    if diagnostics is None:
      refresh_issue_metadata(root, config, writer, scope)
    else:
      for index, number in enumerate(scope, start=1):
        diagnostics.provider(
          "metadata",
          number,
          lambda number=number: refresh_issue_metadata(
            root,
            config,
            writer,
            (number,),
          ),
          index=index,
          total=len(scope),
        )

  return MetadataAcquisition(
    issues=normalized,
    provider_reads=scope,
  )
