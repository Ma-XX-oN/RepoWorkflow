from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import subprocess
import tempfile


class GitError(RuntimeError):
  pass


@dataclass(frozen=True)
class RepositoryState:
  commit: str
  head_ref: str | None
  refs: dict[str, str]


def git_bytes(
  root: Path, *args: str, check: bool = True, capture: bool = True,
) -> subprocess.CompletedProcess[bytes]:
  try:
    completed = subprocess.run(
      ["git", *args], cwd=root, capture_output=capture, check=False,
    )
  except OSError as exc:
    raise GitError(f"cannot execute git: {exc}") from exc
  if check and completed.returncode:
    detail = (completed.stderr or completed.stdout or b"git command failed")
    raise GitError(f"git {' '.join(args)}: {detail.decode('utf-8', 'backslashreplace').strip()}")
  return completed


def git(
  root: Path, *args: str, check: bool = True, capture: bool = True,
) -> subprocess.CompletedProcess[str]:
  completed = git_bytes(root, *args, check=check, capture=capture)
  try:
    stdout = completed.stdout.decode("utf-8", "strict") if completed.stdout is not None else None
    stderr = completed.stderr.decode("utf-8", "strict") if completed.stderr is not None else None
  except UnicodeDecodeError as exc:
    raise GitError(f"git {' '.join(args)}: invalid UTF-8 protocol output: {exc}") from exc
  return subprocess.CompletedProcess(completed.args, completed.returncode, stdout, stderr)


def git_wire_path(raw: bytes) -> str:
  if not raw or b"\0" in raw:
    raise GitError("empty or NUL-containing Git path")
  try:
    path = raw.decode("utf-8", "strict")
  except UnicodeDecodeError as exc:
    raise GitError("invalid UTF-8 Git path") from exc
  if path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/")):
    raise GitError("non-relative or ambiguous Git path")
  if "\x00" in path or (os.name == "nt" and "\\" in path):
    raise GitError("Git path cannot be represented as a native path")
  return path


def git_native_path(raw: bytes) -> Path:
  return Path(*git_wire_path(raw).split("/"))


def head_sha(root: Path) -> str:
  return git(root, "rev-parse", "HEAD").stdout.strip()


def current_branch(root: Path) -> str:
  return git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def head_reference(root: Path) -> str | None:
  result = git(root, "symbolic-ref", "-q", "HEAD", check=False)
  if result.returncode:
    return None
  value = result.stdout.strip()
  return value or None


def changed_files(root: Path) -> list[str]:
  raw = git_bytes(root, "status", "--porcelain=v1", "--untracked-files=all", "-z").stdout
  if raw and not raw.endswith(b"\0"):
    raise GitError("unterminated Git status -z record")
  parts = raw.split(b"\0") if raw else []
  paths: list[str] = []
  index = 0
  while index < len(parts) - 1:
    entry = parts[index]
    if len(entry) < 4 or entry[2:3] != b" " or entry[:2] == b"  ":
      raise GitError("malformed Git status -z record")
    paths.append(git_wire_path(entry[3:]))
    if b"R" in entry[:2] or b"C" in entry[:2]:
      index += 1
      if index >= len(parts) - 1:
        raise GitError("missing Git rename/copy source path")
      git_wire_path(parts[index])
    index += 1
  return sorted(set(paths))


def git_checkout_bytes(root: Path, relative: str | Path, *, treeish: str = "HEAD") -> bytes | None:
  """Materialize one committed Git path through Git's own checkout machinery.

  The temporary index and output prefix isolate the caller's index/worktree.
  """
  if not isinstance(treeish, str) or not treeish or treeish.startswith("-"):
    raise GitError("invalid checkout treeish")
  wire = relative.as_posix() if isinstance(relative, Path) else relative
  if not isinstance(wire, str):
    raise GitError("checkout path must be str or Path")
  path = git_wire_path(wire.encode("utf-8", "strict"))
  with tempfile.TemporaryDirectory(prefix="rwf-git-checkout-") as scratch:
    index = Path(scratch) / "index"
    output = Path(scratch) / "output"
    output.mkdir()
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = str(index)
    def isolated(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
      try:
        completed = subprocess.run(
          ["git", *args], cwd=root, env=env, capture_output=True, check=False,
        )
      except OSError as exc:
        raise GitError(f"cannot execute git: {exc}") from exc
      if check and completed.returncode:
        detail = completed.stderr.decode("utf-8", "backslashreplace")
        raise GitError(f"git {' '.join(args)}: {detail.strip()}")
      return completed
    isolated("read-tree", treeish)
    probe = isolated("ls-files", "--error-unmatch", "--", path, check=False)
    if probe.returncode == 1:
      return None
    if probe.returncode:
      raise GitError("git ls-files failed: " + probe.stderr.decode("utf-8", "backslashreplace"))
    isolated("checkout-index", "--force", f"--prefix={output}{os.sep}", "--", path)
    materialized = output.joinpath(*path.split("/"))
    try:
      return materialized.read_bytes()
    except OSError as exc:
      raise GitError(f"git checkout output unavailable: {exc}") from exc


def local_ref_snapshot(root: Path) -> dict[str, str]:
  completed = git(root, "for-each-ref", "--format=%(refname)%00%(objectname)")
  values: dict[str, str] = {}
  for line in completed.stdout.splitlines():
    if "\0" not in line:
      continue
    ref, object_name = line.split("\0", 1)
    if ref.startswith("refs/remotes/"):
      continue
    values[ref] = object_name
  return values


def repository_state(root: Path) -> RepositoryState:
  return RepositoryState(head_sha(root), head_reference(root), local_ref_snapshot(root))


def restore_repository_state(root: Path, state: RepositoryState) -> None:
  if state.head_ref is None:
    git(root, "checkout", "--detach", "--force", state.commit)
  else:
    git(root, "update-ref", state.head_ref, state.commit)
    git(root, "symbolic-ref", "HEAD", state.head_ref)
  current = local_ref_snapshot(root)
  for ref in sorted(set(current) - set(state.refs)):
    git(root, "update-ref", "-d", ref)
  for ref, object_name in state.refs.items():
    if current.get(ref) != object_name:
      git(root, "update-ref", ref, object_name)
  git(root, "reset", "--hard", state.commit)
  git(root, "clean", "-fd")
