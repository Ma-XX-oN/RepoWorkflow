from pathlib import Path
import os
import subprocess
import shutil
import tempfile
import unittest

from repo_workflow.shell_init import render_bash_init


ROOT = Path(__file__).resolve().parents[1]


def bash_path(path: Path) -> str:
  value = path.resolve().as_posix()
  if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
    value = f"/{value[0].lower()}{value[2:]}"
  return value


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


def bash_source_path(path: Path) -> str:
  if os.name != "nt":
    return path.resolve().as_posix()
  result = subprocess.run(
    [bash_executable(), "-c", 'cygpath -u "$1"', "bash", str(path.resolve())],
    capture_output=True,
    text=True,
  )
  if result.returncode:
    raise AssertionError(
      f"cygpath failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
  return result.stdout.strip()


class BashInitTests(unittest.TestCase):
  def test_output_ends_with_source_instructions(self):
    output = render_bash_init(ROOT, ROOT)
    self.assertEqual(
      output.splitlines()[-6:],
      [
        "# To activate this Bash initialization portably, run:",
        '#   source /dev/stdin <<<"$(rwf init bash)"',
        "# On Bash 4+ this shorter form is also supported:",
        "#   source <(rwf init bash)",
        "# Equivalent portable dot form:",
        '#   . /dev/stdin <<<"$(rwf init bash)"',
      ],
    )
    self.assertNotIn("eval", output)

  def test_emitted_source_registers_completion_for_both_names(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          "source \"$1\"; complete -p rwf; complete -p repo-workflow",
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
    self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")
    self.assertIn("-F _repo_workflow_complete rwf", result.stdout)
    self.assertIn("-F _repo_workflow_complete repo-workflow", result.stdout)

  def test_repeated_sourcing_is_safe(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          "source \"$1\"; source \"$1\"; complete -p rwf >/dev/null",
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
    self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")


  def test_shell_sensitive_repository_path_round_trips(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo space (x)'quote"
      root.mkdir()
      subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )
      subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
      )
      subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=root,
        check=True,
      )
      subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )
      (root / "rwf").write_text("#!/bin/sh\n", encoding="utf-8")
      (root / "repo_workflow.py").write_text("", encoding="utf-8")

      output = render_bash_init(root, ROOT)
      source = Path(td) / "init.bash"
      source.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          "source \"$1\"; printf '%s\\n' \"$REPO_WORKFLOW_ROOT\"",
          "bash",
          bash_source_path(source),
        ],
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")
    self.assertEqual(result.stdout.strip(), root.resolve().as_posix())

  def test_source_and_dot_forms_both_parse(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      for command in ('source "$1"', '. "$1"'):
        with self.subTest(command=command):
          result = subprocess.run(
            [bash_executable(), "-c", command + "; type rwf >/dev/null", "bash", bash_source_path(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
          )
          self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")


  def test_sourced_completion_function_returns_top_level_candidate(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'source "$1"; '
            'COMP_WORDS=(rwf la); COMP_CWORD=1; '
            'COMP_LINE="rwf la"; COMP_POINT=6; '
            '_repo_workflow_complete; '
            'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"; '
            'printf "REPLY:%s\\n" "${COMPREPLY[@]}"'
          ),
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
    self.assertEqual(
      result.returncode,
      0,
      f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )
    self.assertIn("COUNT:1", result.stdout)
    self.assertIn("REPLY:lanes", result.stdout)

  def test_sourced_rwf_complete_command_returns_candidate(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; rwf complete -- la',
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
    self.assertEqual(
      result.returncode,
      0,
      f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )
    self.assertEqual(result.stdout.splitlines(), ["lanes"])


  def test_activation_preserves_unrelated_shell_state(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'RWF_UNRELATED_SENTINEL=keep; '
            'rwf_unrelated_function() { printf "function-ok"; }; '
            'source "$1"; '
            'printf "VAR:%s\\n" "$RWF_UNRELATED_SENTINEL"; '
            'printf "FN:%s\\n" "$(rwf_unrelated_function)"'
          ),
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
    self.assertEqual(
      result.returncode,
      0,
      f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )
    self.assertIn("VAR:keep", result.stdout)
    self.assertIn("FN:function-ok", result.stdout)


  def make_consumer_repo(self, root: Path) -> Path:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "--allow-empty", "-m", "initial"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    commit = subprocess.run(
      ["git", "rev-parse", "HEAD"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    ).stdout.strip()
    scripts = root / "scripts"
    scripts.mkdir()
    launcher = scripts / "repoworkflow.py"
    launcher.write_text(
      "import sys\nprint('CONSUMER:' + '|'.join(sys.argv[1:]))\n",
      encoding="utf-8",
    )
    subprocess.run(
      [
        "git",
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},RepoWorkflow",
      ],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "add", "scripts/repoworkflow.py"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "-m", "pin RepoWorkflow"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    return launcher

  def test_consumer_wrapper_falls_back_from_broken_python3_to_python(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      shim_dir = Path(td) / "shim"
      shim_dir.mkdir()
      python3 = shim_dir / "python3"
      python3.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
      python3.chmod(0o755)
      shim = bash_source_path(shim_dir)
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; PATH="$2:$PATH"; rwf alpha beta',
          "bash",
          bash_source_path(source),
          shim,
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(
      result.returncode,
      0,
      f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )
    self.assertIn("CONSUMER:alpha|beta", result.stdout)

  def test_consumer_wrapper_fails_actionably_without_python(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      empty_path = Path(td) / "empty-path"
      empty_path.mkdir()
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'source "$1"; PATH="$2"; rwf alpha; '
            'status=$?; printf "STATUS:%s\\n" "$status"; exit "$status"'
          ),
          "bash",
          bash_source_path(source),
          bash_source_path(empty_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 127)
    self.assertIn("STATUS:127", result.stdout)
    self.assertIn("Python 3 is required", result.stderr)

  def test_activation_survives_changing_directory(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      elsewhere = Path(td) / "elsewhere"
      elsewhere.mkdir()
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'source "$1"; cd "$2"; '
            'printf "ROOT:%s\\n" "$REPO_WORKFLOW_ROOT"; '
            'rwf complete -- la; '
            'COMP_WORDS=(rwf la); COMP_CWORD=1; '
            'COMP_LINE="rwf la"; COMP_POINT=6; '
            '_repo_workflow_complete; '
            'printf "REPLY:%s\\n" "${COMPREPLY[@]}"'
          ),
          "bash",
          bash_source_path(path),
          bash_source_path(elsewhere),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn(f"ROOT:{ROOT.resolve().as_posix()}", result.stdout)
    self.assertIn("lanes", result.stdout.splitlines())
    self.assertIn("REPLY:lanes", result.stdout)

  def test_missing_completion_source_fails_actionably(self):
    with tempfile.TemporaryDirectory() as td:
      with self.assertRaisesRegex(
        ValueError,
        "Bash completion source is missing",
      ):
        render_bash_init(ROOT, Path(td))

  def test_owned_command_names_are_replaced_but_unrelated_state_survives(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'rwf() { printf "old-rwf"; }; '
            'repo-workflow() { printf "old-repo-workflow"; }; '
            'unrelated() { printf "keep"; }; '
            'source "$1"; '
            'printf "UNRELATED:%s\\n" "$(unrelated)"; '
            'rwf complete -- la; '
            'repo-workflow complete -- la'
          ),
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("UNRELATED:keep", result.stdout)
    self.assertNotIn("old-rwf", result.stdout)
    self.assertNotIn("old-repo-workflow", result.stdout)
    self.assertGreaterEqual(result.stdout.splitlines().count("lanes"), 2)


  def test_repo_workflow_alias_executes_same_consumer_launcher(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; repo-workflow alpha "two words"',
          "bash",
          bash_source_path(source),
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("CONSUMER:alpha|two words", result.stdout)

  def test_consumer_wrapper_preserves_launcher_exit_status_for_both_names(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      launcher = self.make_consumer_repo(root)
      launcher.write_text(
        (
          "import sys\n"
          "code = int(sys.argv[1])\n"
          "print('EXIT:' + str(code))\n"
          "raise SystemExit(code)\n"
        ),
        encoding="utf-8",
      )
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      for name in ("rwf", "repo-workflow"):
        with self.subTest(name=name):
          result = subprocess.run(
            [
              bash_executable(),
              "-c",
              f'source "$1"; {name} 23',
              "bash",
              bash_source_path(source),
            ],
            cwd=root,
            capture_output=True,
            text=True,
          )
          self.assertEqual(result.returncode, 23)
          self.assertIn("EXIT:23", result.stdout)

  def test_consumer_shell_sensitive_path_executes(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer space (x)'quote"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; rwf alpha',
          "bash",
          bash_source_path(source),
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("CONSUMER:alpha", result.stdout)


  def test_consumer_prefers_working_python3(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      shim_dir = Path(td) / "shim"
      shim_dir.mkdir()
      python3 = shim_dir / "python3"
      python = shim_dir / "python"
      python3.write_text(
        (
          "#!/bin/sh\n"
          "if [ \"$1\" = \"-c\" ]; then exit 0; fi\n"
          "printf 'PYTHON3:%s\\n' \"$*\"\n"
        ),
        encoding="utf-8",
      )
      python.write_text(
        "#!/bin/sh\nprintf 'PYTHON:%s\\n' \"$*\"\n",
        encoding="utf-8",
      )
      python3.chmod(0o755)
      python.chmod(0o755)
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; PATH="$2"; rwf alpha',
          "bash",
          bash_source_path(source),
          bash_source_path(shim_dir),
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("PYTHON3:", result.stdout)
    self.assertNotIn("PYTHON:", result.stdout)

  def test_non_python3_interpreters_are_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      self.make_consumer_repo(root)
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      shim_dir = Path(td) / "shim"
      shim_dir.mkdir()
      for name in ("python3", "python"):
        candidate = shim_dir / name
        candidate.write_text(
          (
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
            "exit 99\n"
          ),
          encoding="utf-8",
        )
        candidate.chmod(0o755)
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; PATH="$2"; rwf alpha',
          "bash",
          bash_source_path(source),
          bash_source_path(shim_dir),
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 127)
    self.assertIn("Python 3 is required", result.stderr)


  def test_direct_init_execution_does_not_mutate_parent_shell(self):
    result = subprocess.run(
      [
        bash_executable(),
        "-c",
        (
          'RWF_SENTINEL=keep; '
          'rwf() { printf "old-rwf"; }; '
          'repo-workflow() { printf "old-repo"; }; '
          './rwf init bash >/dev/null; '
          'printf "VAR:%s\\n" "$RWF_SENTINEL"; '
          'printf "RWF:%s\\n" "$(rwf)"; '
          'printf "REPO:%s\\n" "$(repo-workflow)"'
        ),
      ],
      cwd=ROOT,
      capture_output=True,
      text=True,
    )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("VAR:keep", result.stdout)
    self.assertIn("RWF:old-rwf", result.stdout)
    self.assertIn("REPO:old-repo", result.stdout)

  def test_activation_replaces_owned_aliases(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'shopt -s expand_aliases; '
            'alias rwf="printf old-rwf"; '
            'alias repo-workflow="printf old-repo"; '
            'source "$1"; '
            'type -t rwf; type -t repo-workflow; '
            'rwf complete -- la; '
            'repo-workflow complete -- la'
          ),
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout.splitlines()[:2], ["function", "function"])
    self.assertNotIn("old-rwf", result.stdout)
    self.assertNotIn("old-repo", result.stdout)
    self.assertGreaterEqual(result.stdout.splitlines().count("lanes"), 2)


  def test_activation_replaces_each_owned_alias_independently(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      for name in ("rwf", "repo-workflow"):
        with self.subTest(name=name):
          result = subprocess.run(
            [
              bash_executable(),
              "-c",
              (
                'shopt -s expand_aliases; '
                f'alias {name}="printf old"; '
                'source "$1"; '
                'type -t rwf; type -t repo-workflow'
              ),
              "bash",
              bash_source_path(path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
          )
          self.assertEqual(result.returncode, 0, result.stderr)
          self.assertEqual(
            result.stdout.splitlines()[-2:],
            ["function", "function"],
          )


  def test_activation_and_completion_work_with_strict_shell_options(self):
    output = render_bash_init(ROOT, ROOT)
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "init.bash"
      path.write_text(output, encoding="utf-8")
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'set -euo pipefail; '
            'source "$1"; '
            'COMP_WORDS=(rwf la); COMP_CWORD=1; '
            'COMP_LINE="rwf la"; COMP_POINT=6; '
            '_repo_workflow_complete; '
            'printf "REPLY:%s\\n" "${COMPREPLY[@]}"'
          ),
          "bash",
          bash_source_path(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("REPLY:lanes", result.stdout)

  def test_consumer_wrapper_preserves_shell_sensitive_arguments_exactly(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "consumer"
      root.mkdir()
      launcher = self.make_consumer_repo(root)
      launcher.write_text(
        "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
      )
      source = Path(td) / "init.bash"
      source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
      args = ["", "two words", "*", "$HOME", "semi;colon", "quo\'te", '\"double\"']
      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          'source "$1"; shift; rwf "$@"',
          "bash",
          bash_source_path(source),
          *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    import json
    self.assertEqual(json.loads(result.stdout), args)

  def test_changed_repository_activation_rebinds_command_and_completion(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      roots = []
      sources = []
      for label in ("A", "B"):
        root = base / f"consumer-{label}"
        root.mkdir()
        launcher = self.make_consumer_repo(root)
        launcher.write_text(
          (
            "import sys\n"
            f"label = {label!r}\n"
            "args = sys.argv[1:]\n"
            "if args[-3:] == ['complete', '--', 'la'] and args[:1] == ['--root']:\n"
            "  print(label.lower())\n"
            "else:\n"
            "  print(label + ':' + '|'.join(args))\n"
          ),
          encoding="utf-8",
        )
        source = base / f"init-{label}.bash"
        source.write_text(render_bash_init(root, ROOT), encoding="utf-8")
        roots.append(root)
        sources.append(source)

      result = subprocess.run(
        [
          bash_executable(),
          "-c",
          (
            'source "$1"; '
            'rwf first; '
            'COMP_WORDS=(rwf la); COMP_CWORD=1; '
            'COMP_LINE="rwf la"; COMP_POINT=6; '
            '_repo_workflow_complete; '
            'printf "A-REPLY:%s\\n" "${COMPREPLY[@]}"; '
            'source "$2"; '
            'rwf second; '
            'COMP_WORDS=(rwf la); COMP_CWORD=1; '
            'COMP_LINE="rwf la"; COMP_POINT=6; '
            '_repo_workflow_complete; '
            'printf "B-REPLY:%s\\n" "${COMPREPLY[@]}"; '
            'printf "ROOT:%s\\n" "$REPO_WORKFLOW_ROOT"'
          ),
          "bash",
          bash_source_path(sources[0]),
          bash_source_path(sources[1]),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("A:first", result.stdout)
    self.assertIn("A-REPLY:a", result.stdout)
    self.assertIn("B:second", result.stdout)
    self.assertIn("B-REPLY:b", result.stdout)
    self.assertIn(f"ROOT:{roots[1].resolve().as_posix()}", result.stdout)

  def test_shipped_rwf_launcher_runs_init_from_nested_directory(self):
    nested = ROOT / "tests"
    result = subprocess.run(
      [
        bash_executable(),
        "-c",
        '"$1" init bash',
        "bash",
        bash_source_path(ROOT / "rwf"),
      ],
      cwd=nested,
      capture_output=True,
      text=True,
    )

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn(ROOT.resolve().as_posix(), result.stdout)
    self.assertIn("source /dev/stdin", result.stdout)

if __name__ == "__main__":
  unittest.main()
