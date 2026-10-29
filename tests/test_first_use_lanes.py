"""RWF #721 hermetic first-use contracts: FirstUseGraphTests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.p4_provider_fixture import (
  CLI, FIXTURE, ROOT, FirstUseFixture, provider_calls, decode_git_common_dir,
  set_metadata_titles, set_provider_failure, verify_provider,
)


class FirstUseGraphTests(FirstUseFixture, unittest.TestCase):
  def test_git_common_dir_decoder_preserves_path_whitespace(self):
    """Remove only Git's line delimiter, never valid filename spaces."""
    raw = os.fsencode("  directory ending with space ")
    self.assertEqual(decode_git_common_dir(raw + b"\n"),
                     "  directory ending with space ")
    self.assertEqual(
      decode_git_common_dir(raw + b"\r\n"),
      "  directory ending with space " + ("" if os.name == "nt" else "\r"),
    )
    with self.assertRaisesRegex(ValueError, "line terminator"):
      decode_git_common_dir(raw)
    with self.assertRaisesRegex(ValueError, "lacks pathname"):
      decode_git_common_dir(b"\n")
    if os.name == "nt":
      with self.assertRaisesRegex(ValueError, "lacks pathname"):
        decode_git_common_dir(b"\r\n")
    else:
      self.assertEqual(decode_git_common_dir(b"\r\n"), "\r")
    for invalid in (b"\x00\n", b"directory\x00name\n"):
      with self.assertRaisesRegex(ValueError, "contains NUL"):
        decode_git_common_dir(invalid)
    if os.name != "nt":
      with tempfile.TemporaryDirectory() as td:
        for name in ("\r", "\n", "\r\n", "\n\r", "bare-trailing-CR\r"):
          git_dir = Path(td) / name
          subprocess.run(
            ["git", "init", "--bare", str(git_dir)],
            check=True, capture_output=True,
          )
          common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=git_dir, check=True, capture_output=True,
          ).stdout
          self.assertEqual(
            Path(decode_git_common_dir(common)).resolve(), git_dir.resolve(),
          )

  def test_unicode_git_init_and_common_dir_survive_restricted_locale(self):
    """Git's filesystem path bytes must not use host-default text decoding."""
    with tempfile.TemporaryDirectory() as td:
      root = (Path(td) / os.fsdecode("É 空🚀 workspace".encode("utf-8"))
              / "repo")
      root.mkdir(parents=True)
      env = dict(os.environ)
      env.update({
        "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
        "RWF_P4_UNICODE_ROOT": str(root),
        "RWF_P4_LINKED_NAME": os.fsdecode(
          "linked Ç 中文🚀 worktree".encode("utf-8")),
      })
      code = "\n".join((
        "import os,subprocess,sys",
        "from pathlib import Path",
        "from tests.p4_provider_fixture import FirstUseFixture, decode_git_common_dir",
        "if sys.flags.utf8_mode != 0: raise RuntimeError('UTF8 mode active')",
        "r=Path(os.environ['RWF_P4_UNICODE_ROOT'])",
        "FirstUseFixture().make_repo(r)",
        "def common(path):",
        "  raw=subprocess.run(['git','rev-parse','--git-common-dir'],"
        "cwd=path,check=True,capture_output=True).stdout",
        "  return (path/decode_git_common_dir(raw)).resolve()",
        "if common(r)!=(r/'.git').resolve(): "
        "raise RuntimeError('root common-dir mismatch')",
        "linked=r.parent/os.environ['RWF_P4_LINKED_NAME']",
        "subprocess.run(['git','worktree','add','-b','p4-proof',"
        "str(linked)],cwd=r,check=True,capture_output=True)",
        "if common(linked)!=(r/'.git').resolve(): "
        "raise RuntimeError('worktree common-dir mismatch')",
      ))
      result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT,
        env=env, capture_output=True,
      )
      self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
      self.assertTrue((root / ".git").is_dir())

  def test_github_fixture_never_executes_real_provider(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      verify_provider(root, env)
      self.assertNotIn("GH_TOKEN", env)
      self.assertNotIn("GITHUB_TOKEN", env)
      selected = self.run_rwf(root, env, "lanes", "select", "203", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      calls = provider_calls(env)
      self.assertGreaterEqual(len(calls), 4)
      for number in (201, 203):
        self.assertIn({
          "kind": "info", "args": ["issue", "get", str(number)],
        }, calls)
        self.assertIn({
          "kind": "dependency",
          "args": ["dependency", "related", str(number)],
        }, calls)
      invalid = subprocess.run(
        [sys.executable, str(FIXTURE), "dependency", str(base),
         "issue", "delete", "203"],
        capture_output=True, text=True, encoding="utf-8",
      )
      self.assertEqual(invalid.returncode, 2)
      self.assertIn("unexpected provider arguments", invalid.stderr)
      self.assertEqual(provider_calls(env)[-1], {
        "kind": "dependency", "args": ["issue", "delete", "203"],
      })

      before = Path(env["RWF_TEST_DEPS"]).read_bytes()
      mutation = subprocess.run(
        [sys.executable, str(FIXTURE), "dependency", str(base),
         "dependency", "replace", "203", "201"],
        capture_output=True, text=True, encoding="utf-8",
      )
      self.assertEqual(mutation.returncode, 2)
      self.assertIn("unexpected provider arguments", mutation.stderr)
      self.assertEqual(Path(env["RWF_TEST_DEPS"]).read_bytes(), before)

  def test_fresh_checkout_selects_and_renders_ticket_dependency_closure(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "203", "206", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["203", "206"])
      self.assertEqual(value["closure"], ["201", "203", "206"])

      tickets = root / ".repoworkflow" / "tickets.csv"
      self.assertTrue(tickets.is_file())
      rows = self.ticket_rows(root)
      self.assertEqual(rows["203"]["dependencies"], "201")
      self.assertEqual(rows["203"]["title"], "Root 203")

      common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        check=True,
        capture_output=True,
      ).stdout
      common = decode_git_common_dir(common)
      writer = (root / common / "repoworkflow" / "runtime-writer-id").resolve()
      self.assertTrue(writer.is_file())
      self.assertTrue(writer.read_text(encoding="utf-8").startswith("local-"))

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("Lane A", listed.stdout)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)
      self.assertIn("Lane B", listed.stdout)
      self.assertIn("#206  Root 206", listed.stdout)
      self.assertNotIn("─", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A201", viewed.stdout)
      self.assertIn("A203", viewed.stdout)
      self.assertIn("B206", viewed.stdout)
      self.assertIn("─", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

  def test_leaf_focus_discovers_complete_component_from_provider(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base, {
        435: [439],
        436: [],
        437: [436],
        438: [436],
        439: [437, 438],
      })

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "436",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["436"])
      self.assertEqual(value["closure"], ["435", "436", "437", "438", "439"])
      self.assertEqual(set(self.dependency_calls(env)), {
        435, 436, 437, 438, 439
      })

      rendered = self.run_rwf(root, env, "lanes", "select", "436")
      self.assertEqual(rendered.returncode, 0, rendered.stderr)
      self.assertIn("*?A436", rendered.stdout)
      self.assertEqual(rendered.stdout.count("*"), 1)

  def test_group_boundary_stops_provider_component_until_followed(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      dependencies = {
        1: [],
        2: [1],
        3: [2],
        4: [3],
      }
      env = self.fake_github(
        base,
        dependencies,
        titles={
          1: "Issue 1",
          2: "Feature: Boundary",
          3: "Issue 3",
          4: "Issue 4",
        },
      )

      stopped = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--json",
      )
      self.assertEqual(stopped.returncode, 0, stopped.stderr)
      self.assertEqual(json.loads(stopped.stdout)["closure"], ["1", "2"])
      self.assertEqual(set(self.dependency_calls(env)), {1, 2})

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      followed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--follow",
        "feature",
        "--refresh",
        "--json",
      )
      self.assertEqual(followed.returncode, 0, followed.stderr)
      self.assertEqual(
        json.loads(followed.stdout)["closure"],
        ["1", "2", "3", "4"],
      )
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3, 4})

  def test_show_children_fetches_one_hop_without_recursive_traversal(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
        },
        titles={
          1: "Issue 1",
          2: "Feature: Boundary",
          3: "Issue 3",
          4: "Issue 4",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--show-children",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["1", "2", "3"],
      )
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3})

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertNotIn(4, self.dependency_calls(env))

      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertTrue(
        record["value"]["show_children"]["feature"],
      )

  def test_show_children_support_fetch_does_not_expand_projection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
        },
        titles={
          1: "Issue 1",
          2: "Issue 2",
          3: "Feature: Boundary",
          4: "Issue 4",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "4",
        "--show-children",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["2", "3", "4"],
      )
      self.assertNotIn("1", json.loads(selected.stdout)["closure"])
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3, 4})

  def test_refresh_preserves_consumed_follow_budget(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
          5: [4],
        },
        titles={
          1: "Issue 1",
          2: "Feature: First",
          3: "Issue 3",
          4: "Feature: Second",
          5: "Issue 5",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--follow",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["1", "2", "3", "4"],
      )

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertNotIn(5, self.dependency_calls(env))

      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertEqual(
        record["value"]["closure"],
        ["1", "2", "3", "4"],
      )
      self.assertEqual(record["value"]["follow"]["feature"], 1)

  def test_human_select_renders_graph_and_list_uses_same_selection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "203", "206")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertNotIn('"schema_version"', selected.stdout)
      self.assertIn("─", selected.stdout)
      self.assertIn("*", selected.stdout)
      self.assertIn("A201", selected.stdout)
      self.assertIn("A203", selected.stdout)

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)
      self.assertIn("#206  Root 206", listed.stdout)
      self.assertNotIn("─", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A201", viewed.stdout)
      self.assertIn("A203", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

