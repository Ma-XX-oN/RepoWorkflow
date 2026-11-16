"""Read exact provider destination SHA and policy from one immutable Git tip.

The provider owns observation; #108/#109 own interpretation of ticket policy.
No extrapolation of ancestor tickets, and no mutation or queue records.
"""
import base64
import binascii
import re


class DestinationProviderError(RuntimeError):
  """Destination or exact-SHA policy readback is unavailable or malformed."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")


def _destination(destination):
  if (type(destination) is not str or destination.startswith("-")
      or _DEST.fullmatch(destination) is None
      or any(segment in ("", ".", "..")
             for segment in destination.split("/"))):
    raise DestinationProviderError("invalid destination branch identity")
  return "refs/heads/" + destination


def read_destination_snapshot(backend, destination):
  """Return exact old destination and unparsed allow-list at that commit."""
  ref = _destination(destination)
  owner_repo = getattr(backend, "repository", None)
  if (type(owner_repo) is not str or
      re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", owner_repo) is None):
    raise DestinationProviderError("provider repository identity invalid")
  try:
    repository = backend.get("")
  except Exception as error:
    raise DestinationProviderError("provider repository identity UNKNOWN") from error
  if (type(repository) is not dict
      or repository.get("full_name") != backend.repository):
    raise DestinationProviderError("provider destination repository mismatch")

  def ref_sha():
    try:
      value = backend.get("git/ref/" + ref.removeprefix("refs/"))
    except Exception as error:
      raise DestinationProviderError("destination ref read UNKNOWN") from error
    if (type(value) is not dict or value.get("ref") != ref
        or type(value.get("object")) is not dict
        or value["object"].get("type") != "commit"):
      raise DestinationProviderError("destination ref response malformed")
    sha = value["object"].get("sha")
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
      raise DestinationProviderError("destination SHA malformed")
    return sha

  sha = ref_sha()
  policy_path = ".repoworkflow/allow-tickets/to-" + destination
  route = "contents/" + policy_path + "?ref=" + sha
  present = True
  try:
    file = backend.get(route)
  except Exception as error:
    if getattr(error, "code", None) != "not_found":
      raise DestinationProviderError("destination policy read UNKNOWN") from error
    present = False
    content = None
  else:
    if (type(file) is not dict or file.get("type") != "file"
        or file.get("path") != policy_path
        or file.get("encoding") != "base64"
        or type(file.get("content")) is not str
        or len(file["content"]) > 1400000):
      raise DestinationProviderError("destination policy payload invalid")
    try:
      encoded = "".join(file["content"].split())
      raw = base64.b64decode(encoded, validate=True)
      if len(raw) > 1048576:
        raise ValueError("allow-list exceeds one MiB")
      content = raw.decode("utf-8")
    except (binascii.Error, ValueError, UnicodeError) as error:
      raise DestinationProviderError("destination policy encoding invalid") from error
  if ref_sha() != sha:
    raise DestinationProviderError("destination changed during policy read")
  return {
    "destination": destination, "ref": ref, "sha": sha,
    "policy_present": present, "policy_text": content,
  }
