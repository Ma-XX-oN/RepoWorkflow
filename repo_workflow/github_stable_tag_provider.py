"""GitHub REST provider for immutable remote stable tag publication.

Credential acquisition and #80 authority verification occur outside this adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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


class GitHubRestTransport:
  """Concrete authenticated transport for api.github.com.

  Callers obtain short-lived credentials externally; tokens are never logged.
  """

  def __init__(self, token: str, *, timeout: float = 15):
    if not token or timeout <= 0:
      raise ValueError("token and positive timeout are required")
    self._token = token
    self._timeout = timeout

  def __call__(
    self, method: str, path: str, data: dict | None
  ) -> Response:
    if method not in ("GET", "POST"):
      raise PublicationRefused("unsupported GitHub API operation")
    if not path.startswith("/") or "//" in path:
      raise PublicationRefused("invalid GitHub API path")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(
      "https://api.github.com" + path,
      data=body,
      method=method,
      headers={
        "Authorization": "Bearer " + self._token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
    )
    try:
      with urlopen(request, timeout=self._timeout) as response:
        status = response.status
        payload = response.read()
    except HTTPError as exc:
      status = exc.code
      payload = exc.read()
    except (OSError, URLError) as exc:
      raise PublicationRefused("GitHub API transport unavailable") from exc
    try:
      value = json.loads(payload) if payload else {}
    except (ValueError, UnicodeDecodeError) as exc:
      raise PublicationRefused("malformed GitHub API response") from exc
    if not isinstance(value, dict):
      raise PublicationRefused("unexpected GitHub API response shape")
    return Response(status, value)
