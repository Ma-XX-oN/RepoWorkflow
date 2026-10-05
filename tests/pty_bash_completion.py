from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PROMPT = "__RWF_PROMPT__ "
SYNC = "__RWF_SYNC_RESULT__"
COMPLETION_SYNC = "__RWF_COMPLETION_RESULT__"


class Terminal:
  def send(self, text: str) -> None:
    raise NotImplementedError

  def expect(self, text: str, timeout: float = 15.0) -> str:
    raise NotImplementedError

  def close(self) -> None:
    raise NotImplementedError


class PosixTerminal(Terminal):
  def __init__(self, bash: str, env: dict[str, str]):
    import pexpect

    self._pexpect = pexpect
    self._child = pexpect.spawn(
      bash,
      ["--noprofile", "--norc", "-i"],
      cwd=os.fspath(ROOT),
      env=env,
      encoding="utf-8",
      timeout=15,
      echo=True,
      dimensions=(40, 160),
    )

  def send(self, text: str) -> None:
    self._child.send(text)

  def expect(self, text: str, timeout: float = 15.0) -> str:
    self._child.timeout = timeout
    self._child.expect(re.escape(text))
    return self._child.before + self._child.after

  def close(self) -> None:
    if self._child.isalive():
      self._child.send("exit\n")
      try:
        self._child.expect(self._pexpect.EOF, timeout=3)
      except Exception:
        self._child.close(force=True)


class WindowsTerminal(Terminal):
  def __init__(self, bash: str, env: dict[str, str]):
    from winpty import PtyProcess

    os.environ["PYWINPTY_BLOCK"] = "0"
    self._proc = PtyProcess.spawn(
      [bash, "--noprofile", "--norc", "-i"],
      cwd=os.fspath(ROOT),
      env=env,
      dimensions=(40, 160),
    )
    self._buffer = ""

  def send(self, text: str) -> None:
    self._proc.write(text)

  def expect(self, text: str, timeout: float = 15.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if text in self._buffer:
        end = self._buffer.index(text) + len(text)
        value = self._buffer[:end]
        self._buffer = self._buffer[end:]
        return value
      try:
        chunk = self._proc.read(4096)
      except EOFError as error:
        raise AssertionError(
          f"PTY closed before {text!r}; buffered output: {self._buffer!r}"
        ) from error
      if chunk:
        self._buffer += chunk.replace("\r\n", "\n")
      else:
        time.sleep(0.02)
    raise AssertionError(
      f"timed out waiting for {text!r}; buffered output: {self._buffer!r}"
    )

  def close(self) -> None:
    if self._proc.isalive():
      self._proc.write("exit\r\n")
      time.sleep(0.1)
    self._proc.close(force=True)


def bash_executable() -> str:
  if os.name != "nt":
    value = shutil.which("bash")
    if value is None:
      raise AssertionError("bash is not available on PATH")
    return value
  git = shutil.which("git")
  if git is None:
    raise AssertionError("Git for Windows is not available on PATH")
  git_path = Path(git).resolve()
  for parent in [git_path.parent, *git_path.parents]:
    candidate = parent / "bin" / "bash.exe"
    if candidate.is_file():
      return str(candidate)
    candidate = parent / "bash.exe"
    if candidate.is_file():
      return str(candidate)
  raise AssertionError(f"Git Bash was not found beside {git_path}")


def open_terminal() -> Terminal:
  bash = bash_executable()
  env = dict(os.environ)
  env["TERM"] = "xterm"
  env["PS1"] = PROMPT
  env["RWF_PTY_SYNC"] = SYNC
  env["RWF_PTY_COMPLETION_SYNC"] = COMPLETION_SYNC
  if os.name == "nt":
    return WindowsTerminal(bash, env)
  return PosixTerminal(bash, env)


def send_line(terminal: Terminal, line: str) -> None:
  terminal.send(line + ("\r\n" if os.name == "nt" else "\n"))


def clear_line(terminal: Terminal) -> None:
  terminal.send("\x15")


def expect_prompt(terminal: Terminal) -> str:
  return terminal.expect(PROMPT)


def sync_command(terminal: Terminal, command: str) -> str:
  send_line(
    terminal,
    command + '; printf "%s\\n" "$RWF_PTY_SYNC"',
  )
  output = terminal.expect(SYNC)
  expect_prompt(terminal)
  return output


def setup_shell(terminal: Terminal) -> None:
  expect_prompt(terminal)
  sync_command(
    terminal,
    'source /dev/stdin <<<"$(./rwf init bash)"',
  )
  send_line(
    terminal,
    (
      "eval \"$(declare -f _repo_workflow_complete | "
      "sed '1s/_repo_workflow_complete/_rwf_completion_under_test/')\"; "
      "_repo_workflow_complete() { "
      "_rwf_completion_under_test \"$@\"; "
      "printf '\\n%s\\n' \"$RWF_PTY_COMPLETION_SYNC\" >&2; "
      "}"
    ),
  )
  expect_prompt(terminal)


def assert_completion_executes(
  terminal: Terminal,
  typed: str,
  expected_output: str,
) -> None:
  terminal.send(typed)
  terminal.send("\t")
  terminal.expect(COMPLETION_SYNC)
  terminal.send('--help; printf "%s\\n" "$RWF_PTY_SYNC"')
  send_line(terminal, "")
  output = terminal.expect(SYNC)
  expect_prompt(terminal)
  if expected_output not in output:
    raise AssertionError(
      f"Tab completion did not produce the expected command: "
      f"typed={typed!r}, output={output!r}"
    )


def main() -> int:
  terminal = open_terminal()
  try:
    setup_shell(terminal)

    assert_completion_executes(
      terminal,
      "rwf la",
      "List selected issues grouped by lane",
    )
    assert_completion_executes(
      terminal,
      "rwf lanes se",
      "remove",
    )
    assert_completion_executes(
      terminal,
      "repo-workflow la",
      "List selected issues grouped by lane",
    )

    terminal.send("rwf lanes ")
    terminal.send("\t")
    terminal.expect(COMPLETION_SYNC)
    terminal.send("\t")
    terminal.expect("List selected issues grouped by lane")
    terminal.expect(COMPLETION_SYNC)
    clear_line(terminal)
    sync_command(terminal, ":")

    sync_command(
      terminal,
      '. /dev/stdin <<<"$(./rwf init bash)"',
    )
    if sys.platform != "darwin":
      sync_command(terminal, "source <(./rwf init bash)")

    broken = ROOT / ".pty-test-bin"
    broken.mkdir(exist_ok=True)
    python3 = broken / "python3"
    python3.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    python3.chmod(0o755)
    try:
      quoted = broken.as_posix().replace("'", "'\\''")
      sync_command(terminal, f"PATH='{quoted}':$PATH")
      sync_command(terminal, "rwf --help >/dev/null")
    finally:
      python3.unlink(missing_ok=True)
      broken.rmdir()

    return 0
  finally:
    terminal.close()


if __name__ == "__main__":
  raise SystemExit(main())
