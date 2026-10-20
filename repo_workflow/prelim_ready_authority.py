"""Authoritative #102 PASS and immediate-parent facts for READY publication."""
from pathlib import Path
import re

from .prelim_attempt import _remote_ref
from .prelim_publication import restore_identity
from .prelim_ready import ReadyPublicationError
from .prelim_ready_bridge import PreparedIdentity
from .state_store import durable_store
from .terminal_tag import _remote_target


_TAG = re.compile(r"v[A-Za-z0-9._+-]+\Z")


def verify_ready_authority(root: Path, remote: str,
    identity: PreparedIdentity, *, resolve_parent) -> bool:
  """Fail closed unless published #102 evidence binds source and destination.

  The current target's allow-list is evaluated by #109 at admission time,
  not imported from a PRELIM candidate at publication time.
  """
  if not isinstance(identity, PreparedIdentity):
    raise ReadyPublicationError("prepared READY identity required")
  try:
    parent = resolve_parent(identity.ticket)
  except Exception as error:
    raise ReadyPublicationError("ticket parent unavailable") from error
  if parent != identity.destination:
    raise ReadyPublicationError("ticket not immediate child of destination")
  # Legacy #82 construction bound its historical base to server main only.
  # Do not relabel that physical candidate as verified for a different parent.
  # The destination-qualified v2 producer must supply its own parent proof.
  if identity.destination != "main":
    raise ReadyPublicationError("legacy candidate lacks target-parent provenance")
  destination_ref = "refs/heads/" + identity.destination
  # READY publication is permitted after an offline candidate's destination
  # advances.  The historical base is bound to the immutable #102 PASS
  # record below; current-parent integration requires fresh #109 validation.
  if _remote_ref(root, remote, destination_ref) is None:
    raise ReadyPublicationError("authoritative destination is missing")
  try:
    ref = "refs/heads/prelim-identity-state/" + identity.attempt_guid
    if _remote_ref(root, remote, ref) is None:
      raise ReadyPublicationError("published PRELIM PASS identity absent")
    restore_identity(root, remote, identity.attempt_guid)
    stored = durable_store(root).read(
      "prelim/identities/" + identity.attempt_guid)
  except ReadyPublicationError:
    raise
  except Exception as error:
    raise ReadyPublicationError("PRELIM PASS evidence unreadable") from error
  if type(stored) is not dict or type(stored.get("value")) is not dict:
    raise ReadyPublicationError("PRELIM PASS record malformed")
  value = stored["value"]
  for key, expected in (
      ("attempt", identity.attempt_guid),
      ("issue", str(identity.ticket)),
      ("candidate_sha", identity.candidate_sha),
      ("source_sha", identity.source_sha),
      ("base_sha", identity.base_sha)):
    if value.get(key) != expected:
      raise ReadyPublicationError("PRELIM PASS evidence identity mismatch")
  if value.get("outcome") != "PASS":
    raise ReadyPublicationError("PRELIM validation is not PASS")
  for key in ("regression_tag", "integration_tag"):
    tag = value.get(key)
    if type(tag) is not str or _TAG.fullmatch(tag) is None:
      raise ReadyPublicationError("missing immutable validation tag")
    if _remote_target(root, remote, tag) != identity.candidate_sha:
      raise ReadyPublicationError("PRELIM validation tag target changed")
  return True
