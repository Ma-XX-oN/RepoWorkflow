"""GUID-scoped PRELIM candidate construction (#82).

A construction attempt is not PRELIM acceptance. A different owner validates
and binds immutable PRELIM identity under #102.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import os
import time
import json
from pathlib import Path
import re
import uuid

from .git import git
from .lifecycle_store import LifecycleStore
from .runtime_identity import runtime_writer_identity
from .state_store import (
  JsonRecordStore, StateStoreError, _validate_record,
  _write_json_atomic, durable_store,
)
from .version_adapter import read_version, run_transition

SHA = re.compile(r"^[0-9a-f]{40}$")
ISSUE = re.compile(r"^[1-9][0-9]*$")


class PrelimError(RuntimeError):
  """A preliminary candidate is invalid, stale or needs operator resolution."""


@dataclass(frozen=True)
class PrelimAttempt:
  attempt: str
  state: str
  branch: str
  base_sha: str
  source_sha: str
  candidate_sha: str | None
  proposed_version: str | None
  revision: int


def _sha(value: str, name: str) -> str:
  if not isinstance(value, str) or SHA.fullmatch(value) is None:
    raise PrelimError(f"invalid full Git SHA for {name}")
  return value


def _remote_ref(root: Path, remote: str, ref: str) -> str | None:
  output = git(root, "ls-remote", remote, ref).stdout.splitlines()
  if not output:
    return None
  if len(output) != 1:
    raise PrelimError(f"ambiguous authoritative ref: {ref}")
  sha, found = output[0].split("\t", 1)
  if found != ref:
    raise PrelimError(f"remote returned an unexpected ref for {ref}")
  return _sha(sha, ref)


def _local_ref(root: Path, ref: str) -> str | None:
  result = git(root, "show-ref", "--verify", ref, check=False)
  if result.returncode:
    return None
  return _sha(result.stdout.split()[0], ref)


def _key(attempt: str) -> str:
  return f"prelim/attempts/{attempt}"


def _record(store: JsonRecordStore, attempt: str) -> dict | None:
  try:
    return store.read(_key(attempt))
  except StateStoreError as exc:
    if "record is missing:" in str(exc):
      return None
    raise


def _restore_remote_record(root: Path, remote: str, store: JsonRecordStore,
                           attempt: str) -> dict | None:
  """Recover an immutable provider-backed attempt after clone or process loss."""
  ref = f"refs/heads/prelim-state/{attempt}"
  advertised = _remote_ref(root, remote, ref)
  if advertised is None:
    return None
  git(root, "fetch", remote, ref)
  fetched = _sha(git(root, "rev-parse", "FETCH_HEAD").stdout.strip(), "state")
  if fetched != advertised:
    raise PrelimError("remote attempt state moved during recovery")
  key = _key(attempt)
  relative = f".repoworkflow/state/{key}.json"
  try:
    payload = json.loads(git(root, "show", f"FETCH_HEAD:{relative}").stdout)
    _validate_record(payload, key)
  except (ValueError, StateStoreError, TypeError, KeyError) as error:
    raise PrelimError("remote PRELIM attempt record is invalid") from error
  if (payload["value"].get("attempt") != attempt
      or payload["value"].get("state") != "ready"):
    raise PrelimError("remote PRELIM attempt identity is invalid")
  path = store._path(key)
  if path.exists():
    if store.read(key) != payload:
      raise PrelimError("remote and local attempt records conflict")
  else:
    # This is restoration of an exact validated provider record, not
    # creation of another semantic attempt or revision.
    _write_json_atomic(path, payload)
  result = store.read(key)
  if result != payload:
    raise PrelimError("restored PRELIM attempt differs from provider record")
  return result


def _snapshot(record: dict) -> PrelimAttempt:
  value = record["value"]
  return PrelimAttempt(
    value["attempt"], value["state"], value["branch"],
    value["base_sha"], value["source_sha"], value["candidate_sha"],
    value["proposed_version"], record["revision"],
  )


def _workspace(root: Path, attempt: str) -> Path:
  common = Path(git(root, "rev-parse", "--git-common-dir").stdout.strip())
  if not common.is_absolute():
    common = (root / common).resolve()
  return common / "repoworkflow" / "prelim-worktrees" / attempt


def _trusted_inputs(root: Path, remote: str, issue: str,
                    source_ref: str, source_sha: str, base_sha: str,
                    lifecycle_revision: int) -> None:
  if _remote_ref(root, remote, "refs/heads/main") != base_sha:
    raise PrelimError("authoritative server main moved: new attempt required")
  if _local_ref(root, source_ref) != source_sha:
    raise PrelimError("accepted source ref changed: new acceptance required")
  lifecycle = LifecycleStore(root).read(issue)
  if lifecycle.revision != lifecycle_revision:
    raise PrelimError("accepted lifecycle revision changed")
  if lifecycle.lifecycle.state != "accepted":
    raise PrelimError("issue lifecycle is not accepted")
  if not lifecycle.lifecycle.history or (
    lifecycle.lifecycle.history[-1].candidate != source_sha
  ):
    raise PrelimError("accepted lifecycle does not identify exact source SHA")


def _persist(store: JsonRecordStore, record: dict, writer,
             **updates) -> dict:
  value = dict(record["value"])
  value.update(updates)
  return store.replace(record["key"], record["revision"], value, writer)


def _merge_workspace(root: Path, base: str, source: str,
                     attempt: str, config: dict, bump: str,
                     proposed: str | None) -> tuple[Path, str, bool]:
  worktree = _workspace(root, attempt)
  if not worktree.exists():
    worktree.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", str(worktree), base)
  if proposed is None:
    current = git(worktree, "rev-parse", "HEAD").stdout.strip()
    if git(worktree, "status", "--porcelain").stdout.strip():
      raise PrelimError("attempt workspace is dirty; explicit recovery required")
    if current == base:
      result = run_transition(worktree, config, "integrate", "--increment", bump)
      proposed = result.after
      git(worktree, "add", "-u")
      git(worktree, "commit", "-m", f"PRELIM proposed version {proposed}")
    else:
      # Recover a version commit created before the durable CAS update.
      parent = git(worktree, "rev-parse", "HEAD^").stdout.strip()
      message = git(worktree, "log", "-1", "--format=%s").stdout.strip()
      proposed = read_version(worktree, config)
      if parent != base or message != f"PRELIM proposed version {proposed}":
        raise PrelimError("unrecognized partial version transaction")
  elif read_version(worktree, config) != proposed:
    raise PrelimError("proposed version changed during recovery")
  if git(worktree, "rev-parse", "MERGE_HEAD", check=False).returncode == 0:
    clean = not git(worktree, "ls-files", "-u").stdout.strip()
    return worktree, proposed, clean
  result = git(worktree, "merge", "--no-ff", "--no-commit", source, check=False)
  if result.returncode:
    merging = git(worktree, "rev-parse", "MERGE_HEAD", check=False)
    if merging.returncode:
      raise PrelimError(
        "accepted-source merge failed without recoverable conflict: "
        + (result.stderr or result.stdout).strip()
      )
  return worktree, proposed, result.returncode == 0


def _publish(root: Path, remote: str, store: JsonRecordStore,
             record: dict) -> None:
  value = record["value"]
  attempt = value["attempt"]
  if (value["branch"] != f"prelim-main-{attempt}"
      or value["source_ref"] != f"refs/heads/issue-{value['issue']}"
      or value["state"] != "ready"):
    raise PrelimError("invalid recorded attempt identity")
  _trusted_inputs(root, remote, value["issue"], value["source_ref"],
                  value["source_sha"], value["base_sha"],
                  value["lifecycle_revision"])
  ref = f"refs/heads/{value['branch']}"
  candidate = _sha(value["candidate_sha"], "candidate")
  if _local_ref(root, ref) is None:
    # A restarted clone has the durable provider record but no local attempt
    # ref yet. Restore the exact remote ref; never reconstruct a new commit.
    git(root, "fetch", remote, f"{ref}:{ref}")
  if _local_ref(root, ref) != candidate:
    raise PrelimError("local candidate ref differs from recorded exact SHA")
  actual = _remote_ref(root, remote, ref)
  if actual is None:
    git(root, "push", remote, f"{ref}:{ref}")
    actual = _remote_ref(root, remote, ref)
  if actual != candidate:
    raise PrelimError("remote candidate does not match recorded SHA")
  _trusted_inputs(root, remote, value["issue"], value["source_ref"],
                  value["source_sha"], value["base_sha"],
                  value["lifecycle_revision"])

  state_ref = f"refs/heads/prelim-state/{attempt}"
  stored = _remote_ref(root, remote, state_ref)
  relative = f".repoworkflow/state/{_key(attempt)}.json"
  if stored is None:
    existing_local = _local_ref(root, state_ref)
    if existing_local is not None:
      # Re-publish the original immutable commit after remote ref deletion.
      # Reconstructing it produces another commit SHA and loses identity.
      saved = json.loads(git(root, "show", f"{state_ref}:{relative}").stdout)
      if saved != record:
        raise PrelimError("local state publication ref has mismatched record")
      git(root, "push", remote, f"{state_ref}:{state_ref}")
    else:
      workspace = _workspace(root, f"state-{attempt}")
      if not workspace.exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        git(root, "worktree", "add", "--detach", str(workspace), value["base_sha"])
      path = workspace / relative
      path.parent.mkdir(parents=True, exist_ok=True)
      if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
          raise PrelimError("stale partial state publication")
      else:
        path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
      existing_commit = git(workspace, "log", "-1", "--format=%s").stdout.strip()
      if existing_commit != f"Durable PRELIM attempt {attempt}":
        git(workspace, "add", "--", relative)
        git(workspace, "commit", "-m", f"Durable PRELIM attempt {attempt}")
      state_sha = _sha(git(workspace, "rev-parse", "HEAD").stdout.strip(), "state")
      git(root, "update-ref", state_ref, state_sha, "0" * 40)
      git(root, "push", remote, f"{state_ref}:{state_ref}")
      git(root, "worktree", "remove", str(workspace))
  git(root, "fetch", remote, state_ref)
  remote_record = json.loads(git(root, "show", f"FETCH_HEAD:{relative}").stdout)
  if remote_record != record:
    raise PrelimError("remote persisted attempt record differs from local")


def _construct_prelim_unlocked(root: Path, issue: str, source_ref: str, config: dict,
                     *, bump: str = "patch", attempt_id: str | None = None,
                     store: JsonRecordStore | None = None) -> PrelimAttempt:
  """Start/resume exactly one attempt; an unresolved merge remains recoverable."""
  root = Path(root).resolve()
  if not isinstance(issue, str) or ISSUE.fullmatch(issue) is None:
    raise PrelimError("issue must be a positive decimal string")
  if bump not in {"patch", "minor"}:
    raise PrelimError("unsupported development integration version request")
  if not isinstance(source_ref, str) or not source_ref.startswith("refs/heads/issue-"):
    raise PrelimError("expected an explicit accepted issue branch ref")
  if source_ref != f"refs/heads/issue-{issue}":
    raise PrelimError("accepted branch does not match issue")
  identity = runtime_writer_identity()
  remote = config["repository"]["authoritativeRemote"]
  store = store or durable_store(root)
  try:
    attempt = str(uuid.UUID(attempt_id)) if attempt_id else str(uuid.uuid4())
  except (ValueError, AttributeError, TypeError) as exc:
    raise PrelimError("invalid attempt GUID") from exc
  record = _record(store, attempt)
  if record is None and attempt_id is not None:
    record = _restore_remote_record(root, remote, store, attempt)
  if record is None:
    base = _remote_ref(root, remote, "refs/heads/main")
    if base is None:
      raise PrelimError("authoritative server main unavailable")
    source = _local_ref(root, source_ref)
    if source is None:
      raise PrelimError("accepted issue branch unavailable")
    lifecycle = LifecycleStore(root).read(issue)
    if lifecycle.revision is None:
      raise PrelimError("accepted lifecycle lacks durable revision")
    _trusted_inputs(root, remote, issue, source_ref, source, base,
                    lifecycle.revision)
    value = {
      "attempt": attempt, "issue": issue,
      "branch": f"prelim-main-{attempt}",
      "source_ref": source_ref, "source_sha": source,
      "base_sha": base, "lifecycle_revision": lifecycle.revision,
      "bump": bump, "state": "prepared", "candidate_sha": None,
      "proposed_version": None,
    }
    record = store.create(_key(attempt), value, identity)
  value = record["value"]
  if (value["issue"], value["source_ref"], value["bump"]) != (issue, source_ref, bump):
    raise PrelimError("attempt parameters differ on retry")
  _trusted_inputs(root, remote, issue, source_ref, value["source_sha"],
                  value["base_sha"], value["lifecycle_revision"])
  if value["state"] == "ready":
    _publish(root, remote, store, record)
    workspace = _workspace(root, attempt)
    if workspace.exists():
      if git(workspace, "rev-parse", "HEAD").stdout.strip() != value["candidate_sha"]:
        raise PrelimError("ready workspace has an unexpected tip")
      git(root, "worktree", "remove", str(workspace))
    return _snapshot(record)
  if value["state"] not in {"prepared", "conflict", "versioned"}:
    raise PrelimError("unsupported PRELIM attempt state")
  workspace = _workspace(root, attempt)
  if value["state"] == "conflict":
    raise PrelimError(f"merge conflict requires explicit resolution in {workspace}")
  workspace, proposed, clean = _merge_workspace(
    root, value["base_sha"], value["source_sha"], attempt, config,
    bump, value["proposed_version"],
  )
  if value["proposed_version"] is None:
    record = _persist(store, record, identity,
                      proposed_version=proposed, state="versioned")
  if not clean:
    _persist(store, record, identity, state="conflict")
    raise PrelimError(f"merge conflicts require explicit resolution in {workspace}")
  return _finish_prelim_unlocked(root, attempt, config, store=store)


def _finish_prelim_unlocked(root: Path, attempt: str, config: dict,
                  *, store: JsonRecordStore | None = None) -> PrelimAttempt:
  """Finalize a resolved merge and publish exact candidate and state readback."""
  root = Path(root).resolve()
  identity = runtime_writer_identity()
  store = store or durable_store(root)
  attempt = str(uuid.UUID(attempt))
  record = store.read(_key(attempt))
  value = record["value"]
  if value["attempt"] != attempt or value["branch"] != f"prelim-main-{attempt}":
    raise PrelimError("attempt identity mismatch")
  remote = config["repository"]["authoritativeRemote"]
  _trusted_inputs(root, remote, value["issue"], value["source_ref"],
                  value["source_sha"], value["base_sha"],
                  value["lifecycle_revision"])
  if value["state"] == "ready":
    _publish(root, remote, store, record)
    return _snapshot(record)
  if value["state"] not in {"versioned", "conflict"}:
    raise PrelimError("attempt is not ready for finalization")
  workspace = _workspace(root, attempt)
  if not workspace.exists():
    raise PrelimError("recoverable attempt workspace is missing")
  if git(workspace, "ls-files", "-u").stdout.strip():
    raise PrelimError("unresolved merge conflicts remain")
  if read_version(workspace, config) != value["proposed_version"]:
    raise PrelimError("resolved candidate changed the proposed adapter version")
  merging = git(workspace, "rev-parse", "MERGE_HEAD", check=False).returncode == 0
  if merging:
    git(workspace, "add", "-u")
    git(workspace, "diff", "--cached", "--check")
    git(workspace, "commit", "-m", f"Construct PRELIM candidate {attempt}")
  else:
    message = git(workspace, "log", "-1", "--format=%s").stdout.strip()
    if message != f"Construct PRELIM candidate {attempt}":
      # An already-integrated source needs no merge commit. The version
      # commit is itself the physical candidate when it contains the source.
      no_op_merge = (
        message == f"PRELIM proposed version {value['proposed_version']}"
        and git(workspace, "merge-base", "--is-ancestor",
                value["source_sha"], "HEAD", check=False).returncode == 0
      )
      if not no_op_merge:
        raise PrelimError("accepted source has not been merged")
    if git(workspace, "status", "--porcelain").stdout.strip():
      raise PrelimError("recovered candidate workspace is dirty")
  candidate = _sha(git(workspace, "rev-parse", "HEAD").stdout.strip(), "candidate")
  if git(workspace, "merge-base", "--is-ancestor", value["source_sha"], candidate,
         check=False).returncode:
    raise PrelimError("candidate does not contain accepted source")
  _trusted_inputs(root, remote, value["issue"], value["source_ref"],
                  value["source_sha"], value["base_sha"],
                  value["lifecycle_revision"])
  ref = f"refs/heads/{value['branch']}"
  old = _local_ref(root, ref)
  if old is None:
    git(root, "update-ref", ref, candidate, "0" * 40)
  elif old != candidate:
    raise PrelimError("attempt branch was changed concurrently")
  record = _persist(store, record, identity, state="ready", candidate_sha=candidate)
  _publish(root, remote, store, record)
  git(root, "worktree", "remove", str(workspace))
  return _snapshot(record)


@contextmanager
def _attempt_lock(root: Path, store: JsonRecordStore, attempt: str):
  """Process-scoped lock released by the OS even after an abrupt crash."""
  path = store.root / f".prelim-attempt-{attempt}.lock"
  path.parent.mkdir(parents=True, exist_ok=True)
  fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
  locked = False
  try:
    if os.fstat(fd).st_size == 0:
      os.write(fd, b"0")
    deadline = time.monotonic() + 5.0
    while True:
      try:
        if os.name == "nt":
          import msvcrt
          os.lseek(fd, 0, os.SEEK_SET)
          msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
          import fcntl
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        break
      except OSError as exc:
        if time.monotonic() >= deadline:
          raise PrelimError(f"attempt lock is busy: {path}") from exc
        time.sleep(0.01)
    yield
  finally:
    if locked:
      if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
      else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def construct_prelim(root: Path, issue: str, source_ref: str, config: dict,
                     *, bump: str = "patch", attempt_id: str | None = None,
                     store: JsonRecordStore | None = None) -> PrelimAttempt:
  """Serialize full attempt mutation, not only individual record writes."""
  root = Path(root).resolve()
  store = store or durable_store(root)
  try:
    attempt = str(uuid.UUID(attempt_id)) if attempt_id else str(uuid.uuid4())
  except (ValueError, AttributeError, TypeError) as exc:
    raise PrelimError("invalid attempt GUID") from exc
  with _attempt_lock(root, store, attempt):
    return _construct_prelim_unlocked(
      root, issue, source_ref, config, bump=bump,
      attempt_id=attempt, store=store,
    )


def finish_prelim(root: Path, attempt: str, config: dict,
                  *, store: JsonRecordStore | None = None) -> PrelimAttempt:
  """Prevent simultaneous explicit resolution and construction replay."""
  root = Path(root).resolve()
  store = store or durable_store(root)
  try:
    attempt = str(uuid.UUID(attempt))
  except (ValueError, AttributeError, TypeError) as exc:
    raise PrelimError("invalid attempt GUID") from exc
  with _attempt_lock(root, store, attempt):
    return _finish_prelim_unlocked(root, attempt, config, store=store)
