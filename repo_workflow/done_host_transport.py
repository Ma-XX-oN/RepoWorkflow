"""Trusted engine-owned subprocess transport for the certified provider-v2 adapter.

The transport does not grant approval, issue checks, or invent DONE.
The fixed adapter enforces provider authorization, and IntegrationHost
validates every response before any higher-level consumer can use it.
"""
import json
from pathlib import Path
import subprocess
import sys

from .integration_host_v2 import IntegrationHost


class NativeHostTransportError(RuntimeError):
  """An authenticated provider response was not established."""


def bind_native_integration_host(*, repository, engine_root,
                                 project_root=None, timeout=120):
  """Bind the installed v2 adapter, never a candidate-controlled command."""
  if type(timeout) is not int or not 1 <= timeout <= 120:
    raise NativeHostTransportError("invalid provider timeout")
  try:
    root = Path(engine_root).resolve(strict=True)
    adapter = root / "adapters" / "repo-host-integration-v2.py"
    if not adapter.is_file() or adapter.is_symlink():
      raise NativeHostTransportError("trusted provider adapter unavailable")
    # This is a package-owned path, not a command from the tested candidate.
    if adapter.resolve(strict=True).parent != root / "adapters":
      raise NativeHostTransportError("provider adapter escaped engine root")
  except (OSError, RuntimeError) as error:
    raise NativeHostTransportError("trusted provider installation unavailable") from error

  workspace = root
  if project_root is not None:
    try:
      workspace = Path(project_root).resolve(strict=True)
      if not workspace.is_dir():
        raise NativeHostTransportError("trusted project checkout unavailable")
    except (OSError, RuntimeError) as error:
      raise NativeHostTransportError("trusted project checkout unavailable") from error

  def transport(request):
    # A read-only provider observation needs no local checkout. Writes do.
    read_only = {"refs.list", "destination.read", "lease.read",
                 "attempt.read", "retirement.read",
                 "mit.deferred.read", "mit.resume.read"}
    if request.get("operation") not in read_only and project_root is None:
      raise NativeHostTransportError("trusted project checkout required for mutation")
    try:
      result = subprocess.run(
        [sys.executable, str(adapter)],
        input=json.dumps(request, sort_keys=True, separators=(",", ":")),
        capture_output=True, text=True, encoding="utf-8", errors="strict",
        timeout=timeout, cwd=str(workspace), check=False,
      )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
      raise NativeHostTransportError("provider outcome UNKNOWN") from error
    if (result.returncode != 0 or result.stderr.strip()
        or not result.stdout or len(result.stdout) > 1048576):
      raise NativeHostTransportError("provider outcome UNKNOWN")
    try:
      response = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
      raise NativeHostTransportError("malformed provider response") from error
    return response

  return IntegrationHost(repository, transport)
