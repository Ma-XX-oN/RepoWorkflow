from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from .config import load_config
from .current_work_store import CurrentWorkStore
from .git import git
from .issue_test_contract import IssueTestContract, IssueTestContractError, IssueTestContractStore, SECTION_END, SECTION_START, parse_ticket_test_section, render_ticket_test_section
from .issue_test_policy import review_ticket_test_changes, validate_inline_test_limits
from .issue_test_sync import admit_ticket_tests, compare_ticket_tests
from .repo_info_adapter import issue_body
from .runtime_identity import runtime_writer_identity
from .ticket_write_adapter import replace_issue_body

class IssueTestReviewError(RuntimeError):
  pass

def _issue(root: Path) -> int:
  current = CurrentWorkStore(root).read().value.current
  if current is None:
    raise IssueTestReviewError("no current issue; run rwf start first")
  return int(current.issue)

def _review_dir(root: Path) -> Path:
  git_dir = Path(git(root, "rev-parse", "--git-dir").stdout.strip())
  if not git_dir.is_absolute(): git_dir = (root / git_dir).resolve()
  return git_dir / "repoworkflow" / "test-review"

def _contract(root: Path, issue: int) -> IssueTestContract | None:
  try: return IssueTestContractStore(root).read(issue)
  except IssueTestContractError as error:
    if "record is missing:" in str(error): return None
    raise

def _replace_section(markdown: str, section: str) -> str:
  starts=markdown.count(SECTION_START); ends=markdown.count(SECTION_END)
  if starts==0 and ends==0:
    separator="" if not markdown or markdown.endswith("\n") else "\n"
    return markdown + separator + section + "\n"
  if starts!=1 or ends!=1: raise IssueTestReviewError("ticket executable-test section is ambiguous")
  start=markdown.index(SECTION_START); end=markdown.index(SECTION_END,start)+len(SECTION_END)
  return markdown[:start] + section + markdown[end:]

def _digest(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _write_review(root: Path, issue: int, old: IssueTestContract, new: IssueTestContract, source_digest: str) -> None:
  validate_inline_test_limits(old); validate_inline_test_limits(new)
  directory=_review_dir(root)
  if directory.exists(): shutil.rmtree(directory)
  directory.mkdir(parents=True)
  before=render_ticket_test_section(old); after=render_ticket_test_section(new)
  (directory/"before.md").write_text(before,encoding="utf-8")
  (directory/"after.md").write_text(after,encoding="utf-8")
  (directory/"review.json").write_text(json.dumps({"schema_version":1,"issue":issue,"source_body_digest":source_digest,"before_digest":_digest(before),"after_digest":_digest(after)},sort_keys=True)+"\n",encoding="utf-8")

def _pending(root: Path) -> tuple[dict, Path, Path]:
  directory=_review_dir(root); meta=directory/"review.json"; before=directory/"before.md"; after=directory/"after.md"
  try: value=json.loads(meta.read_text(encoding="utf-8")); old=before.read_text(encoding="utf-8"); new=after.read_text(encoding="utf-8")
  except (FileNotFoundError,json.JSONDecodeError) as error: raise IssueTestReviewError("no pending executable-test review; run rwf tests sync") from error
  if set(value)!={"schema_version","issue","source_body_digest","before_digest","after_digest"} or value["schema_version"]!=1 or value["before_digest"]!=_digest(old) or value["after_digest"]!=_digest(new): raise IssueTestReviewError("pending executable-test review is invalid or modified")
  if value["issue"]!=_issue(root): raise IssueTestReviewError("pending executable-test review is for a different current issue")
  return value,before,after

def sync_tests(root: Path) -> tuple[str,str]:
  issue=_issue(root); config=load_config(root); info=issue_body(root,config,issue); repository=_contract(root,issue)
  status=compare_ticket_tests(issue,info["body"],repository)
  if status=="match": return "match", "Executable tests already match the ticket."
  if status=="repository-only":
    validate_inline_test_limits(repository)
    updated=_replace_section(info["body"],render_ticket_test_section(repository))
    replace_issue_body(root,config,issue,info["body_digest"],updated)
    return "published", "Published repository executable tests to the ticket."
  ticket=parse_ticket_test_section(issue,info["body"])
  if ticket is None: raise IssueTestReviewError("ticket test comparison produced no proposal")
  old=repository or IssueTestContract(issue=issue,tests=(),trust="repository")
  _write_review(root,issue,old,ticket,info["body_digest"])
  return "review", review_ticket_test_changes(old,ticket)

def view_tests(root: Path, which: str="new") -> str:
  _,before,after=_pending(root)
  if which=="old": return before
  if which in {"new",""}: return after
  raise IssueTestReviewError("tests view accepts only old or new")

def accept_tests(root: Path) -> IssueTestContract:
  value,_,after=_pending(root); issue=value["issue"]; config=load_config(root); info=issue_body(root,config,issue)
  if info["body_digest"]!=value["source_body_digest"]: raise IssueTestReviewError("ticket tests changed after review; run rwf tests sync and review again")
  proposed=parse_ticket_test_section(issue,after)
  if proposed is None: raise IssueTestReviewError("pending proposal has no executable tests")
  admitted=admit_ticket_tests(proposed)
  stored=IssueTestContractStore(root).write(admitted,runtime_writer_identity())
  shutil.rmtree(_review_dir(root))
  return stored

def git_review(root: Path, arguments: list[str]) -> int:
  if not arguments: raise IssueTestReviewError("a Git review command is required")
  value,before,after=_pending(root); directory=_review_dir(root); before_path=directory/"before.md"; after_path=directory/"after.md"
  result=subprocess.run(["git",*arguments,"--no-index","--",str(before_path),str(after_path)],cwd=root)
  _pending(root)
  return result.returncode
