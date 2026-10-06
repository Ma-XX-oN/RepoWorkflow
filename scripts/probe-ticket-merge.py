from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from repo_workflow.ticket_merge import configure_ticket_merge_driver


def run(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", *args],
    cwd=root,
    check=True,
    capture_output=True,
    text=True,
  )
  return result.stdout.strip()


def write(root: Path, text: str) -> None:
  path = root / ".repoworkflow" / "tickets.csv"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8", newline="")


def main() -> int:
  with tempfile.TemporaryDirectory() as directory:
    root = Path(directory) / "repo with spaces"
    root.mkdir()
    run(root, "init")
    run(root, "config", "user.name", "RepoWorkflow Probe")
    run(root, "config", "user.email", "probe@example.invalid")
    (root / ".gitattributes").write_text(
      "/.repoworkflow/tickets.csv merge=rwf-tickets\n",
      encoding="utf-8",
    )
    configure_ticket_merge_driver(root, ROOT)

    base = (
      "issue,title,dependencies\n"
      "10,Ten,\n"
      "30,Thirty,10\n"
    )
    write(root, base)
    run(root, "add", ".")
    run(root, "commit", "-m", "base")
    main_branch = run(root, "branch", "--show-current")

    run(root, "checkout", "-b", "ours")
    write(
      root,
      (
        "issue,title,dependencies\n"
        "10,Ten,\n"
        "20,Twenty,10\n"
        "30,Thirty,10\n"
      ),
    )
    run(root, "add", ".repoworkflow/tickets.csv")
    run(root, "commit", "-m", "ours")

    run(root, "checkout", main_branch)
    run(root, "checkout", "-b", "theirs")
    write(
      root,
      (
        "issue,title,dependencies\n"
        "10,Ten,\n"
        "25,Twenty Five,10\n"
        "30,Thirty,10\n"
      ),
    )
    run(root, "add", ".repoworkflow/tickets.csv")
    run(root, "commit", "-m", "theirs")

    run(root, "checkout", "ours")
    run(root, "merge", "--no-edit", "theirs")

    merged = (root / ".repoworkflow" / "tickets.csv").read_text(
      encoding="utf-8"
    )
    expected = (
      "issue,title,dependencies\n"
      "10,Ten,\n"
      "20,Twenty,10\n"
      "25,Twenty Five,10\n"
      "30,Thirty,10\n"
    )
    if merged != expected:
      raise RuntimeError(
        "semantic ticket merge produced unexpected output:\n" + merged
      )

    driver = run(
      root,
      "config",
      "--local",
      "--get",
      "merge.rwf-tickets.driver",
    )
    if "merge-ticket-state.py" not in driver:
      raise RuntimeError("ticket merge driver was not configured")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
