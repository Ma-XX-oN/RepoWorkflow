"""Read-only #809 subprocess profiler loaded through PYTHONPATH on diagnostic jobs.

Records process command *classification*, elapsed wall time, Python caller, and
currently running unittest ID; NEVER records raw command arguments or secrets.
"""
import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

_original_popen = subprocess.Popen
_original_test_run = unittest.TestCase.run
_current_test = threading.local()
_log_file = None
_log_lock = threading.Lock()
_recorded = 0


def _git_operation(args):
  if not isinstance(args, (list, tuple)) or not args:
    return "unknown"
  tokens = [os.fspath(x) for x in args]
  skip_arg = False
  for token in tokens[1:]:
    if skip_arg:
      skip_arg = False
      continue
    if token in ("-C", "-c", "--git-dir", "--work-tree", "--config-env"):
      skip_arg = True
      continue
    if token.startswith("--git-dir=") or token.startswith("--work-tree="):
      continue
    if token.startswith("-"):
      continue
    # Allowlist command verbs only; never log refs, values, paths, URLs or tokens.
    if token in {"init", "clone", "commit", "push", "fetch", "pull", "add",
                 "status", "rev-parse", "show", "log", "diff", "cat-file",
                 "config", "branch", "checkout", "switch", "tag", "reset",
                 "clean", "update-ref", "symbolic-ref", "merge-base",
                 "for-each-ref", "ls-remote", "remote", "submodule",
                 "worktree", "merge", "rebase", "version", "--version"}:
      return token
    return "other"
  return "other"


def _write(record):
  global _log_file, _recorded
  path = os.environ.get("RWF809_TRACE_DIR")
  if not path:
    return
  with _log_lock:
    if _log_file is None:
      dest = Path(path)
      dest.mkdir(parents=True, exist_ok=True)
      _log_file = (dest / ("process-" + str(os.getpid()) + ".jsonl")).open(
        "a", encoding="utf-8", buffering=8192
      )
    _log_file.write(json.dumps(record, sort_keys=True) + "\n")
    _recorded += 1


class ProfiledPopen(_original_popen):
  def __init__(self, args, *other, **kwargs):
    frame = sys._getframe(1)
    while frame is not None and Path(frame.f_code.co_filename).name in ("subprocess.py", "sitecustomize.py"):
      frame = frame.f_back
    self._rwf809_started = time.perf_counter_ns()
    self._rwf809_recorded = False
    self._rwf809_caller = (Path(frame.f_code.co_filename).name + ":" + str(frame.f_lineno)) if frame is not None else "unknown"
    self._rwf809_test = getattr(_current_test, "test", None)
    executable = args[0] if isinstance(args, (list, tuple)) and args else args
    binary = os.path.basename(os.fsdecode(os.fspath(executable))).lower() if isinstance(executable, (str, bytes, os.PathLike)) else "unknown"
    self._rwf809_kind = (
      "git" if binary in ("git", "git.exe") else
      "python" if binary.startswith("python") else
      "other"
    )
    self._rwf809_operation = _git_operation(args) if self._rwf809_kind == "git" else "other"
    super().__init__(args, *other, **kwargs)

  def _rwf809_record(self):
    if self._rwf809_recorded or self.poll() is None:
      return
    self._rwf809_recorded = True
    _write({
      "kind": self._rwf809_kind, "operation": self._rwf809_operation,
      "caller": self._rwf809_caller, "test": self._rwf809_test,
      "elapsed_ms": (time.perf_counter_ns() - self._rwf809_started) / 1e6,
      "returncode": self.returncode,
    })

  def wait(self, *args, **kwargs):
    result = super().wait(*args, **kwargs)
    self._rwf809_record()
    return result

  def communicate(self, *args, **kwargs):
    result = super().communicate(*args, **kwargs)
    self._rwf809_record()
    return result


def _test_run(self, result=None):
  old = getattr(_current_test, "test", None)
  _current_test.test = self.id()
  try:
    return _original_test_run(self, result)
  finally:
    _current_test.test = old


def _close():
  if _log_file is not None:
    _log_file.flush()
    _log_file.close()


subprocess.Popen = ProfiledPopen
unittest.TestCase.run = _test_run
atexit.register(_close)
