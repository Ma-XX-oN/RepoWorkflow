"""Exact tested source identity across disposable .ci/rwf request commits.

The DONE executor integrates source, never a disposable command branch.
Only a contiguous chain of authenticated single-file invocation commits may
be peeled, and exact hosted tested-source provenance is mandatory.
"""
from dataclasses import dataclass
import re


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_MARKERS=frozenset({".ci/run",".ci/rwf"})


class SourceIdentityError(RuntimeError):
  """Tested source and request-commit lineage cannot be authenticated."""


@dataclass(frozen=True)
class InvocationCommit:
  sha: str
  parents: tuple[str,...]
  changed_paths: tuple[str,...]
  invocation_marker: str | None


@dataclass(frozen=True)
class EffectiveSource:
  command_head_sha: str
  tested_source_sha: str
  peeled_requests: tuple[InvocationCommit,...]


def peel_tested_source(*, command_head_sha, expected_tested_sha,
                       read_commit, verify_invocation, max_requests=128):
  """Strip only a verified trailing chain; reject mixed/forged markers.

  verify_invocation is an independently authenticated request oracle:
  returning True only if this request belongs to the exact operation/source.
  Absence of the oracle never licenses peeling request commits.
  """
  if (any(type(v) is not str or _SHA.fullmatch(v) is None
          for v in (command_head_sha,expected_tested_sha))
      or not callable(read_commit)
      or not callable(verify_invocation)
      or type(max_requests) is not int
      or not 1<=max_requests<=512):
    raise SourceIdentityError("exact source and authenticated readers required")
  cursor=command_head_sha
  peeled=[]
  for _ in range(max_requests+1):
    if cursor==expected_tested_sha:
      return EffectiveSource(
        command_head_sha,expected_tested_sha,tuple(peeled))
    try:
      observed=read_commit(cursor)
    except Exception as error:
      raise SourceIdentityError("invocation ancestry readback UNKNOWN") from error
    if (not isinstance(observed,InvocationCommit)
        or observed.sha != cursor
        or type(observed.parents) is not tuple
        or type(observed.changed_paths) is not tuple
        or any(type(path) is not str or not path
               for path in observed.changed_paths)):
      raise SourceIdentityError("commit ancestry is malformed")
    marker=observed.invocation_marker
    if marker not in _MARKERS:
      raise SourceIdentityError("material source changed since tested SHA")
    if (len(observed.parents)!=1
        or _SHA.fullmatch(observed.parents[0]) is None
        or observed.changed_paths!=(marker,)
        or len(peeled)>=max_requests):
      raise SourceIdentityError("invocation commit has mixed or invalid changes")
    try:
      trusted=verify_invocation(observed,expected_tested_sha)
    except Exception as error:
      raise SourceIdentityError("request authenticity UNKNOWN") from error
    if trusted is not True:
      raise SourceIdentityError("invocation request is not authenticated")
    peeled.append(observed)
    cursor=observed.parents[0]
  raise SourceIdentityError("invocation chain is over configured limit")
