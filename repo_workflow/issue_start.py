from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .config import load_config
from .current_work_store import CurrentWorkStore
from .git import git
from .lifecycle_store import LifecycleStore
from .relationship_store import RelationshipStore
from .repo_info_adapter import issue_info
from .runtime_identity import runtime_writer_identity
from .state_store import durable_store
from .transaction import (
  SemanticTransactionCoordinator,
  StateReference,
  StateWrite,
)
from .version_adapter import DEVELOPMENT_VERSION_RE, read_version, run_transition


class IssueStartError(RuntimeError):
  """Raised when canonical issue start cannot complete safely."""


@dataclass(frozen=True)
class IssueStartResult:
  issue: str
  version: str
  branch: str
  relationship_revision: int
  lifecycle_revision: int

  def to_json_value(self) -> dict:
    return {
      "issue": self.issue,
      "version": self.version,
      "branch": self.branch,
      "relationship_revision": self.relationship_revision,
      "lifecycle_revision": self.lifecycle_revision,
    }


def start_issue(
  repository_root: Path,
  issue: str | int,
  *,
  config: dict | None = None,
) -> IssueStartResult:
  root = Path(repository_root).resolve()
  issue_id = _issue_id(issue)
  if config is None:
    config = load_config(root)
  identity = runtime_writer_identity()

  info = issue_info(root, config, int(issue_id))
  if info["state"] != "open":
    raise IssueStartError(f"issue {issue_id} is not open")

  relationships = RelationshipStore(root).read()
  try:
    relation = relationships.graph.issue(issue_id)
  except Exception as error:
    raise IssueStartError(
      f"issue {issue_id} has no registered canonical relationships"
    ) from error

  lifecycle_store = LifecycleStore(root)
  lifecycle = lifecycle_store.read(issue_id)
  current_store = CurrentWorkStore(root)
  current = current_store.read()
  version_before = read_version(root, config)
  parent = relation.parent
  if parent is None:
    raise IssueStartError(f"issue {issue_id} has no canonical parent")
  base_sha = git(root, "rev-parse", parent).stdout.strip()

  transaction_id = _transaction_id(issue_id, identity.session_id)
  coordinator = SemanticTransactionCoordinator(durable_store(root))
  reads = (
    StateReference(
      "relationships",
      "graph",
      relationships.revision,
    ),
    StateReference(
      "lifecycle",
      issue_id,
      _encoded_revision(lifecycle.revision),
      _presence(lifecycle.revision),
    ),
    StateReference(
      "current-work",
      "context",
      _encoded_revision(current.revision),
      _presence(current.revision),
    ),
    StateReference("version", "canonical", 0, version_before),
    StateReference("git", "parent", 0, base_sha),
  )
  writes = (
    StateWrite("version", "canonical", {"issue": issue_id}),
    StateWrite("git", f"issue-{issue_id}", {"base": parent}),
    StateWrite("lifecycle", issue_id, {"state": "active"}),
    StateWrite("current-work", "context", {"issue": issue_id}),
  )

  try:
    coordinator.prepare(transaction_id, reads, writes, identity)
  except Exception as error:
    try:
      record = coordinator.read(transaction_id)
    except Exception:
      raise IssueStartError(str(error)) from error
    if record["value"]["status"] not in {"prepared", "committed"}:
      raise IssueStartError(str(error)) from error

  def validate(references):
    return _validate_reads(
      root,
      config,
      issue_id,
      parent,
      references,
    )

  def materialize(_writes):
    _materialize(
      root,
      config,
      issue_id,
      parent,
      relationships.revision,
      identity,
    )

  try:
    coordinator.commit(transaction_id, identity, validate, materialize)
  except Exception as error:
    raise IssueStartError(str(error)) from error

  final_lifecycle = lifecycle_store.read(issue_id)
  if final_lifecycle.revision is None:
    raise IssueStartError("issue start did not materialize lifecycle state")
  return IssueStartResult(
    issue=issue_id,
    version=read_version(root, config),
    branch=f"issue-{issue_id}",
    relationship_revision=relationships.revision,
    lifecycle_revision=final_lifecycle.revision,
  )


def _materialize(
  root: Path,
  config: dict,
  issue_id: str,
  parent: str,
  relationship_revision: int,
  identity,
) -> None:
  version = read_version(root, config)
  match = DEVELOPMENT_VERSION_RE.fullmatch(version)
  if match is None:
    run_transition(root, config, "task", "--issue", issue_id)
    version = read_version(root, config)
    match = DEVELOPMENT_VERSION_RE.fullmatch(version)
  if match is None or int(match.group(4)) != int(issue_id):
    raise IssueStartError(
      f"canonical version is not assigned to issue {issue_id}: {version}"
    )

  branch = f"issue-{issue_id}"
  exists = git(root, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
  if exists.returncode:
    git(root, "branch", branch, parent)
  ancestor = git(
    root,
    "merge-base",
    "--is-ancestor",
    parent,
    branch,
    check=False,
  )
  if ancestor.returncode:
    raise IssueStartError(
      f"existing branch {branch} is not based on canonical parent {parent}"
    )
  current_branch = git(root, "branch", "--show-current").stdout.strip()
  if current_branch != branch:
    git(root, "checkout", branch)

  lifecycle_store = LifecycleStore(root)
  lifecycle = lifecycle_store.read(issue_id)
  if lifecycle.lifecycle.state in {"unstarted", "aborted"}:
    transition = (
      "start" if lifecycle.lifecycle.state == "unstarted" else "re-enter"
    )
    lifecycle = lifecycle_store.transition(
      issue_id,
      transition,
      version,
      relationship_revision,
      identity,
      lifecycle.revision,
    )
  elif lifecycle.lifecycle.state != "active":
    raise IssueStartError(
      f"issue {issue_id} cannot start from {lifecycle.lifecycle.state}"
    )
  if lifecycle.lifecycle.relationship_revision != relationship_revision:
    raise IssueStartError("active lifecycle uses a stale relationship revision")
  if lifecycle.revision is None:
    raise IssueStartError("active lifecycle lacks a durable revision")

  current_store = CurrentWorkStore(root)
  current = current_store.read()
  reference = current.value.current
  if not (
    reference is not None
    and reference.issue == issue_id
    and reference.lifecycle_revision == lifecycle.revision
    and reference.relationship_revision == relationship_revision
  ):
    current_store.project_start(
      issue_id,
      lifecycle.revision,
      relationship_revision,
      identity,
      current.revision,
    )


def _validate_reads(
  root: Path,
  config: dict,
  issue_id: str,
  parent: str,
  references,
) -> bool:
  expected = {(item.domain, item.key): item for item in references}
  relationships = RelationshipStore(root).read()
  if relationships.revision != expected[("relationships", "graph")].revision:
    return False
  lifecycle = LifecycleStore(root).read(issue_id)
  lifecycle_ref = expected[("lifecycle", issue_id)]
  if (
    _encoded_revision(lifecycle.revision) != lifecycle_ref.revision
    or _presence(lifecycle.revision) != lifecycle_ref.identity
  ):
    return False
  current = CurrentWorkStore(root).read()
  current_ref = expected[("current-work", "context")]
  if (
    _encoded_revision(current.revision) != current_ref.revision
    or _presence(current.revision) != current_ref.identity
  ):
    return False
  if read_version(root, config) != expected[("version", "canonical")].identity:
    return False
  base_sha = git(root, "rev-parse", parent).stdout.strip()
  return base_sha == expected[("git", "parent")].identity


def _transaction_id(issue_id: str, session_id: str) -> str:
  digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
  return f"issue-start-{issue_id}-{digest}"


def _encoded_revision(value: int | None) -> int:
  return 0 if value is None else value + 1


def _presence(value: int | None) -> str:
  return "absent" if value is None else "present"


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise IssueStartError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1:
    raise IssueStartError(f"invalid issue id: {value!r}")
  return str(int(text))
