"""Bind immutable PRELIM publication to the authenticated provider repository.

The caller may have more than one GitHub remote or a separate push URL.
Read both before any provider write. An unverified remote is not READY.
"""
from pathlib import Path
import re

from .git import git
from .prelim_ready import ReadyPublicationError


_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def verify_ready_provider_scope(root: Path, remote: str, backend) -> None:
  """Fail closed unless the Git fetch/push target is the exact provider repo."""
  repository = getattr(backend, "repository", None)
  if (type(repository) is not str or _REPO.fullmatch(repository) is None
      or type(remote) is not str or not remote or remote.startswith("-")):
    raise ReadyPublicationError("provider READY repository identity unavailable")
  try:
    details = backend.get("")
  except Exception as error:
    raise ReadyPublicationError("provider READY repository read UNKNOWN") from error
  if type(details) is not dict or details.get("full_name") != repository:
    raise ReadyPublicationError("provider READY repository identity mismatch")
  approved = {
    url for url in (details.get("clone_url"), details.get("ssh_url"))
    if type(url) is str and url and not any(
      ch in url for ch in ("\n", "\r", "\x00"))
  }
  if not approved:
    raise ReadyPublicationError("provider READY remote endpoint unavailable")
  try:
    fetch = git(root, "remote", "get-url", remote, check=False)
    push = git(root, "remote", "get-url", "--push", remote, check=False)
  except Exception as error:
    raise ReadyPublicationError("provider READY Git URL read UNKNOWN") from error
  if (fetch.returncode or push.returncode
      or fetch.stdout.strip() != push.stdout.strip()
      or fetch.stdout.strip() not in approved):
    raise ReadyPublicationError("PRELIM provider repository or push URL differs")
