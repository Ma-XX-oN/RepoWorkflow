from __future__ import annotations

from dataclasses import dataclass

from .lifecycle_store import LifecycleStore
from .relationship_store import RelationshipStore


@dataclass(frozen=True)
class ReadinessResult:
  issue: str
  status: str
  lifecycle_state: str
  blockers: tuple[str, ...]

  def to_json_value(self) -> dict:
    return {
      "issue": int(self.issue),
      "status": self.status,
      "lifecycle_state": self.lifecycle_state,
      "blockers": [int(issue) for issue in self.blockers],
    }


def workspace_readiness(repository_root) -> tuple[ReadinessResult, ...]:
  graph = RelationshipStore(repository_root).read().graph
  lifecycle_store = LifecycleStore(repository_root)
  lifecycles = {
    issue: lifecycle_store.read(issue).lifecycle
    for issue in graph.issues
  }

  results = []
  for issue in sorted(graph.issues, key=int):
    lifecycle = lifecycles[issue]
    if lifecycle.state == "completed":
      status = "terminal"
      blockers = ()
    elif lifecycle.state == "active":
      status = "active"
      blockers = ()
    elif lifecycle.state == "accepted":
      status = "accepted"
      blockers = ()
    else:
      blockers = tuple(
        dependency
        for dependency in graph.issue(issue).depends_on
        if not lifecycles[dependency].dependency_satisfied
      )
      status = "blocked" if blockers else "ready"
    results.append(
      ReadinessResult(
        issue=issue,
        status=status,
        lifecycle_state=lifecycle.state,
        blockers=blockers,
      )
    )
  return tuple(results)


def readiness_json(repository_root) -> dict:
  results = workspace_readiness(repository_root)
  return {
    "ready": [
      int(result.issue)
      for result in results
      if result.status == "ready"
    ],
    "issues": [result.to_json_value() for result in results],
  }
