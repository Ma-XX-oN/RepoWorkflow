"""Provider-backed read-only host observations for #104.

#542 must perform the authoritative acceptance-time recheck.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote
from urllib.request import Request, urlopen


class HostFactsError(ValueError):
  pass


@dataclass(frozen=True)
class HostFacts:
  head: str
  current_base: str
  candidate_exists: bool
  base_is_ancestor: bool


def read_host_facts(repository, source, destination, candidate, token, *, fetch=None):
  """Read source/base tips and compare ancestry from the host provider."""
  sha = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
  repo = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
  ref = r"[A-Za-z0-9_./-]+"
  if (not isinstance(repository, str) or re.fullmatch(repo, repository) is None
      or any(part in (".", "..") for part in repository.split("/"))):
    raise HostFactsError("invalid repository")
  for branch in (source, destination):
    if (not isinstance(branch, str) or re.fullmatch(ref, branch) is None
        or branch.startswith(("/", "-")) or branch.endswith("/")
        or "//" in branch or any(p in (".", "..") for p in branch.split("/"))):
      raise HostFactsError("invalid ref")
  if not isinstance(candidate, str) or re.fullmatch(sha, candidate) is None:
    raise HostFactsError("invalid candidate")
  if not isinstance(token, str) or not token.strip():
    raise HostFactsError("missing provider credentials")

  def get(path):
    if fetch is not None:
      result = fetch(path)
    else:
      request = Request(
        "https://api.github.com/repos/" + repository + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json"},
      )
      with urlopen(request, timeout=12) as response:
        result = json.load(response)
    if not isinstance(result, dict):
      raise HostFactsError("malformed provider result")
    return result

  try:
    head = get("/branches/" + quote(source, safe=""))["commit"]["sha"]
    base = get("/branches/" + quote(destination, safe=""))["commit"]["sha"]
    if (not isinstance(head, str) or re.fullmatch(sha, head) is None
        or not isinstance(base, str) or re.fullmatch(sha, base) is None
        or len({len(candidate), len(head), len(base)}) != 1):
      raise HostFactsError("invalid provider SHA")
    comparison = get("/compare/" + base + "..." + candidate)
    status = comparison.get("status")
    if (comparison.get("base_commit", {}).get("sha") != base
        or status not in ("ahead", "identical", "behind", "diverged")):
      raise HostFactsError("invalid provider ancestry")
    return HostFacts(head, base, True, status in ("ahead", "identical"))
  except HostFactsError:
    raise
  except (OSError, KeyError, ValueError, TypeError, AttributeError) as error:
    raise HostFactsError("provider facts unavailable") from error


def decide_with_github_host(facts, repository, source, destination, token, *, fetch=None):
  """One-shot provider-fact binding for the portable #104 semantic decision.

  Re-query at each invocation. Never cache an ALLOW result. #542 must enforce
  a separate final acceptance-time check against the live destination.
  """
  from dataclasses import replace
  from .candidate_eligibility import Facts, decide

  if not isinstance(facts, Facts):
    return decide(facts)
  try:
    host = read_host_facts(
      repository, source, destination, facts.candidate, token, fetch=fetch,
    )
  except HostFactsError:
    return False, ("host-facts-unavailable",)
  return decide(replace(
    facts, head=host.head, current_base=host.current_base,
    candidate_exists=host.candidate_exists,
    base_is_ancestor=host.base_is_ancestor,
  ))


def decide_with_verified_sources(
  store, requirements, record_ids, *, candidate, version, source,
  destination, recorded_base, repository, token, coverage_evaluator,
  fetch=None,
):
  """Combine #69/#95 trusted-publisher evidence and provider-observed host facts.

  Callers must supply the authoritative complete requirements manifest. Both
  observations are freshly read for every decision; #542 owns final acceptance.
  """
  from .candidate_eligibility import Facts
  from .candidate_evidence import EvidenceGateError, read_evidence_gate

  try:
    evidence = read_evidence_gate(
      store, requirements, record_ids, candidate=candidate,
      version=version, branch=source, coverage_evaluator=coverage_evaluator,
    )
  except EvidenceGateError:
    return False, ("validation-evidence-unavailable",)
  facts = Facts(
    candidate, evidence.tested, candidate, recorded_base, recorded_base,
    evidence.authenticated, evidence.complete, evidence.passed,
    evidence.inputs_current, evidence.required_checks_complete,
    evidence.applicable, False, False,
  )
  return decide_with_github_host(
    facts, repository, source, destination, token, fetch=fetch,
  )
