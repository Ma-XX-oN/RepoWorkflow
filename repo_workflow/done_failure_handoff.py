"""Durable issue/PR handoff after a failed #109 integration.

A failed item may leave runnable READY processing only after independently
verified, persistent owner notification. Unavailable workers are handed off,
never falsely represented as restarted or asynchronously executing.
"""
from dataclasses import dataclass
import re


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_GUID=re.compile(
  r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}-[0-9a-f]{12}\Z")


class HandoffError(RuntimeError):
  """Failure handoff or owner notification not durably verified."""


@dataclass(frozen=True)
class FailureHandoff:
  guid: str
  issue: int
  destination: str
  prelim_sha: str
  expected_parent_sha: str
  tested_int_sha: str
  failure_kind: str
  evidence_ref: str
  owner_issue_ids: tuple[int,...]
  reproduction_ref: str
  conflict_paths: tuple[str,...]
  attribution: str
  operation_id: str


@dataclass(frozen=True)
class PersistedFailureHandoff:
  handoff: FailureHandoff
  per_issue_refs: tuple[tuple[int,str], ...]


def publish_failure_handoff(handoff, *, publish_comment, read_comment):
  """Publish once per owner and verify exact immutable event readback.

  The provider adapter must implement idempotent append/read operations.
  A lost response is reconciled by readback, never blind duplicate POST.
  """
  if (not isinstance(handoff,FailureHandoff)
      or _GUID.fullmatch(handoff.guid) is None
      or type(handoff.issue) is not int or handoff.issue < 1
      or type(handoff.destination) is not str or not handoff.destination
      or any(type(sha) is not str or _SHA.fullmatch(sha) is None
             for sha in (
               handoff.prelim_sha,handoff.expected_parent_sha,
               handoff.tested_int_sha))
      or handoff.failure_kind not in {
        "ART_FAIL","AIT_FAIL","MIT_FAIL","CONFLICT","STALE_PARENT"}
      or any(type(t) is not str or not t.strip()
             for t in (
               handoff.evidence_ref,handoff.reproduction_ref,
               handoff.attribution,handoff.operation_id))
      or type(handoff.owner_issue_ids) is not tuple
      or not handoff.owner_issue_ids
      or handoff.issue not in handoff.owner_issue_ids
      or len(set(handoff.owner_issue_ids))!=len(handoff.owner_issue_ids)
      or any(type(n) is not int or n < 1 for n in handoff.owner_issue_ids)
      or type(handoff.conflict_paths) is not tuple
      or not callable(publish_comment)
      or not callable(read_comment)):
    raise HandoffError("exact immutable failure handoff identity required")
  records=[]
  for issue_id in handoff.owner_issue_ids:
    key=handoff.operation_id+"-issue-"+str(issue_id)
    try:
      publish_comment(issue_id,key,handoff)
    except Exception:
      # An ACK can be lost after provider persistence.
      pass
    try:
      observed=read_comment(issue_id,key)
    except Exception as error:
      raise HandoffError("owner issue handoff readback UNKNOWN") from error
    if (type(observed) is not dict
        or observed.get("issue_id")!=issue_id
        or observed.get("operation_id")!=key
        or observed.get("handoff")!=handoff
        or type(observed.get("comment_ref")) is not str
        or not observed["comment_ref"].strip()):
      raise HandoffError("issue owner handoff missing or changed")
    records.append((issue_id,observed["comment_ref"]))
  return PersistedFailureHandoff(handoff,tuple(records))
