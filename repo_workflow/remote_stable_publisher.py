"""Remote-only immutable stable-tag publisher (#638).

The caller supplies independently authenticated authority and provider adapters.
No local Git repository, tag or ref is read or modified by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)


class PublicationRefused(RuntimeError):
  """Publication was not proven safe or authoritative."""


@dataclass(frozen=True)
class PublicationRequest:
  repository: str
  version: str
  landed_sha: str
  candidate_sha: str
  expected_base_sha: str
  request_id: str
  authorization_ref: str
  protection_ref: str
  certification_ref: str
  release_class: str


class RemoteProvider(Protocol):
  def authenticated_finalizer(self) -> bool: ...
  def main_tip(self, repository: str) -> str: ...
  def accepted_base(self, repository: str, sha: str) -> str: ...
  def read_tag(self, repository: str, ref: str) -> str | None: ...
  def create_tag_if_absent(
    self, repository: str, ref: str, sha: str
  ) -> None: ...


class PublicationAuthority(Protocol):
  def authorize(
    self, request: PublicationRequest, ref: str
  ) -> bool: ...

  def certified(
    self, request: PublicationRequest, ref: str
  ) -> bool: ...


def publish_stable_tag(
  request: PublicationRequest,
  provider: RemoteProvider,
  authority: PublicationAuthority,
) -> str:
  """Publish exact landed SHA or refuse; reconcile ambiguous create results.

  Provider read_tag MUST return the peeled commit for annotated tags.
  Provider create_tag_if_absent MUST be an atomic server-side create.
  Authority is responsible for #80 grant validation and consumption.
  """
  if not _VERSION.fullmatch(request.version):
    raise PublicationRefused("noncanonical stable version")
  if not _SHA.fullmatch(request.landed_sha):
    raise PublicationRefused("invalid landed SHA")
  if not _SHA.fullmatch(request.candidate_sha):
    raise PublicationRefused("invalid candidate SHA")
  if not _SHA.fullmatch(request.expected_base_sha):
    raise PublicationRefused("invalid base SHA")
  if request.candidate_sha != request.landed_sha:
    raise PublicationRefused("candidate differs from landed SHA")
  if not request.repository or not request.request_id:
    raise PublicationRefused("missing repository or request identity")
  if not all((request.authorization_ref, request.protection_ref,
              request.certification_ref)):
    raise PublicationRefused("required authority evidence missing")
  if request.release_class not in ("patch", "minor", "major"):
    raise PublicationRefused("invalid release class")

  ref = f"refs/tags/v{request.version}"
  try:
    if not provider.authenticated_finalizer():
      raise PublicationRefused("unauthenticated remote finalizer")
    if not authority.authorize(request, ref):
      raise PublicationRefused("authorization denied")
    if not authority.certified(request, ref):
      raise PublicationRefused("protection or certification not accepted")
    if provider.main_tip(request.repository) != request.landed_sha:
      raise PublicationRefused("landed SHA is not server main tip")
    if provider.accepted_base(request.repository, request.landed_sha) != (
      request.expected_base_sha
    ):
      raise PublicationRefused("accepted base differs")
    failed_ref = ref + "-CI-FAIL"
    if provider.read_tag(request.repository, failed_ref) is not None:
      raise PublicationRefused("conflicting immutable terminal result")
    existing = provider.read_tag(request.repository, ref)
    if existing is not None:
      if existing != request.landed_sha:
        raise PublicationRefused("conflicting immutable tag")
      return ref

    try:
      provider.create_tag_if_absent(
        request.repository, ref, request.landed_sha
      )
    except Exception:
      # A timeout can mean the server committed.  Reconcile by readback.
      if provider.read_tag(request.repository, ref) != request.landed_sha:
        raise PublicationRefused("creation failed or outcome unknown")
    if provider.read_tag(request.repository, ref) != request.landed_sha:
      raise PublicationRefused("remote tag readback differs")
    if provider.read_tag(request.repository, failed_ref) is not None:
      raise PublicationRefused("competing terminal result appeared")
    return ref
  except PublicationRefused:
    raise
  except Exception as exc:
    raise PublicationRefused("remote authority or provider unavailable") from exc
