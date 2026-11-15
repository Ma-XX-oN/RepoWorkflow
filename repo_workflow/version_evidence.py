"""Version preparation follows tested source identity, never tag consumption."""
from pathlib import Path
import re

from .git import git as _git
from .source_tip import source_tip
from .phase_terminal import plan_phase
from .test_results_reader import TestCommandError


def tested_source_changed(root: Path, issue: int, version: str,
                                  *, remote: str = "origin") -> bool:
  """Compare verified report identities instead of consuming a terminal tag.

  Parameters
  ----------
  root : Path
      Repository under test.
  issue : int
      Current issue number.
  version : str
      Version being prepared for testing.
  remote : str
      Authoritative remote holding fixed-source terminal tags.

  Returns
  -------
  bool
      Whether this version was tested on different material source.
  """
  from .test_results_reader import parse_testing_log
  from .terminal_tag import _remote_target, _local_target

  log = root / ".repoworkflow/validation" / f"testResults-{issue}.jsonl"
  raw = _git(root, "show", "HEAD:" + log.relative_to(root).as_posix(), check=False)
  records = parse_testing_log(raw.stdout) if raw.returncode == 0 else []
  current = source_tip(root)
  for record in records:
    if record.get("testVersion") == version:
      tested = record.get("testSHA")
      if not isinstance(tested, str) or not re.fullmatch(r"[0-9a-f]{40}", tested):
        raise TestCommandError("version report has no exact source identity")
      if source_tip(root, tested) != current:
        return True
  for stage in ("regression", "integration"):
    for outcome in ("PASS", "FAIL"):
      tag = plan_phase(version, phase=stage, outcome=outcome).terminal_tag
      remote_source = _remote_target(root, remote, tag)
      local_source = _local_target(root, tag)
      for tested in {remote_source, local_source} - {None}:
        if _git(root, "cat-file", "-e", tested + "^{commit}", check=False).returncode:
          if tested != remote_source:
            raise TestCommandError("local terminal source object unavailable")
          _git(root, "fetch", "--no-tags", remote, "refs/tags/" + tag)
        if source_tip(root, tested) != current:
          return True
  return False

