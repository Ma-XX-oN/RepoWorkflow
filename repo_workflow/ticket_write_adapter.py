from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from .git import changed_files, repository_state
from .process import run_command

class TicketWriteError(RuntimeError):
  pass

def body_digest(body: str) -> str:
  return hashlib.sha256(body.encode("utf-8")).hexdigest()

def replace_issue_body(root: Path, config: dict, issue_number: int, expected_digest: str, body: str) -> dict[str, Any]:
  command = config.get("ticketCommand")
  if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
    raise TicketWriteError("ticket write adapter is not configured")
  if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number <= 0:
    raise TicketWriteError("issue number must be positive")
  if not isinstance(expected_digest, str) or len(expected_digest) != 64:
    raise TicketWriteError("expected ticket body digest is invalid")
  if not isinstance(body, str):
    raise TicketWriteError("ticket body must be text")
  before_state = repository_state(root)
  before_changes = changed_files(root)
  with tempfile.TemporaryDirectory() as td:
    body_path = Path(td) / "body.md"
    body_path.write_text(body, encoding="utf-8")
    result = run_command([*command, "issue", "body", "replace", str(issue_number), expected_digest, str(body_path)], root)
  if repository_state(root) != before_state or changed_files(root) != before_changes:
    raise TicketWriteError("ticket write adapter modified repository state")
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise TicketWriteError("ticket write adapter failed" + (f": {detail}" if detail else ""))
  try:
    value = json.loads(result.stdout)
  except json.JSONDecodeError as exc:
    raise TicketWriteError("ticket write adapter returned malformed JSON") from exc
  expected = {"schema_version", "number", "body_digest"}
  if not isinstance(value, dict) or set(value) != expected or value.get("schema_version") != 1 or value.get("number") != issue_number or value.get("body_digest") != body_digest(body):
    raise TicketWriteError("ticket write adapter returned unconfirmed body replacement")
  return value
