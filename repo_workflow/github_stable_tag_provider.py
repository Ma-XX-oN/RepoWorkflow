"""GitHub REST provider for immutable remote stable tag publication.

Credential acquisition and #80 authority verification occur outside this adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote

from .remote_stable_publisher import PublicationRefused


@dataclass(frozen=True)
class Response:
  status: int
  body: dict


Transport = Callable[[str, str, dict | None], Response]


class GitHubStableTagProvider:
  """Provider-safe create; API never exposes force update or deletion."""

  def __init__(
    self,
    transport: Transport,
    authenticated_actor: str,
    expected_finalizer_actor: str,
  ):
    self._send = transport
    self._actor = authenticated_actor
    self._expected_actor = expected_finalizer_actor

  def _request(self, method: str, path: str, data: dict | None = None) -> dict:
    try:
      response = self._send(method, path, data)
    except Exception as exc:
      raise PublicationRefused("GitHub provider unavailable") from exc
    if response.status == 404 and method == "GET":
      raise LookupError(path)
    if not 200 <= response.status < 300:
      raise PublicationRefused(
        f"GitHub provider {method} refused ({response.status})"
      )
    if not isinstance(response.body, dict):
      raise PublicationRefused("invalid GitHub response")
    return response.body

  @staticmethod
  def _repo(repository: str) -> str:
    if repository.count("/") != 1:
      raise PublicationRefused("invalid repository identity")
    owner, name = repository.split("/")
    if not owner or not name or any(
      char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
      "0123456789-._" for char in owner + name
    ):
      raise PublicationRefused("invalid repository identity")
    return f"/repos/{owner}/{name}"

  def authenticated_finalizer(self) -> bool:
    if not self._actor or self._actor != self._expected_actor:
      return False
    try:
      identity = self._request("GET", "/user")
    except (PublicationRefused, LookupError):
      return False
    return identity.get("login") == self._expected_actor

  def main_tip(self, repository: str) -> str:
    value = self._request(
      "GET", self._repo(repository) + "/git/ref/heads/main"
    )
    return value.get("object", {}).get("sha", "")

  def accepted_base(self, repository: str, sha: str) -> str:
    value = self._request(
      "GET", self._repo(repository) + "/git/commits/" + sha
    )
    parents = value.get("parents")
    if not isinstance(parents, list) or not parents:
      raise PublicationRefused("cannot prove accepted base")
    return parents[0].get("sha", "")

  def read_tag(self, repository: str, ref: str) -> str | None:
    if not ref.startswith("refs/tags/"):
      raise PublicationRefused("not a tag reference")
    path = self._repo(repository)
    try:
      value = self._request(
        "GET", path + "/git/ref/" + quote(ref.removeprefix("refs/"), safe="/")
      )
    except LookupError:
      return None
    obj = value.get("object")
    if not isinstance(obj, dict):
      raise PublicationRefused("invalid tag reference")
    for _ in range(8):
      if obj.get("type") == "commit":
        return obj.get("sha", "")
      if obj.get("type") != "tag":
        raise PublicationRefused("tag does not resolve to commit")
      value = self._request(
        "GET", path + "/git/tags/" + str(obj.get("sha", ""))
      )
      obj = value.get("object")
      if not isinstance(obj, dict):
        raise PublicationRefused("invalid annotated tag")
    raise PublicationRefused("tag dereference limit exceeded")

  def create_tag_if_absent(
    self, repository: str, ref: str, sha: str
  ) -> None:
    if not ref.startswith("refs/tags/v"):
      raise PublicationRefused("only stable tags permitted")
    self._request(
      "POST", self._repo(repository) + "/git/refs",
      {"ref": ref, "sha": sha},
    )
