from __future__ import annotations

"""Strict UTF-8 output for RWF-controlled Python entry points.

Call configure_utf8_output() before invoking a command or emitting diagnostics.
Ordinary print(), stream.write(), logging, and tracebacks then use UTF-8
independently of the Windows host console encoding. In-memory Unicode captures
retain their native semantics.
"""

import codecs
import io
import os
import sys


def configure_utf8_output() -> bool:
  """Configure both live text streams; fail closed if either cannot comply."""
  for name in ("stdout", "stderr"):
    try:
      stream = getattr(sys, name)
      if isinstance(stream, io.StringIO):
        if stream.closed:
          raise ValueError("closed Unicode text capture")
        continue
      if getattr(stream, "closed", False):
        raise ValueError("closed text output stream")
      reconfigure = getattr(stream, "reconfigure", None)
      if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict", newline="\n")
      # An already strict-UTF-8 text capture requires no reconfiguration.
      # Metadata-free custom streams must fail closed: their byte contract
      # cannot be established without a supported reconfigure() operation.
      if codecs.lookup(stream.encoding).name != "utf-8":
        raise ValueError("stdout/stderr codec is not UTF-8")
      if stream.errors != "strict":
        raise ValueError("stdout/stderr codec is not strict")
      if not callable(getattr(stream, "write", None)):
        raise ValueError("stdout/stderr is not writable")
    except (AttributeError, LookupError, OSError, RuntimeError, TypeError, ValueError):
      diagnostic = f"RepoWorkflow error: cannot configure UTF-8 {name} output\n"
      try:
        if sys.__stderr__ is None:
          raise OSError("original stderr is unavailable")
        sys.__stderr__.write(diagnostic)
      except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        try:
          os.write(2, diagnostic.encode("ascii"))
        except (OSError, ValueError):
          pass
      return False
  return True
