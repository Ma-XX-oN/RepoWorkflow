# RepoWorkflow local initialization

`rwf init` configures a local consumer clone for normal interactive use.
`repo-workflow init` is the identical long-name entry point.

Run it once from anywhere inside the Git worktree:

```bash
rwf init
```

Initialization:

- installs or refreshes the RepoWorkflow-managed `pre-commit`, `pre-push`, and
  `pre-rebase` hooks for that clone;
- installs the managed Bash integration under
  `~/.config/repoworkflow/bash/repo-workflow.bash`;
- adds one managed source block to `~/.bashrc`;
- registers completion for both `rwf` and `repo-workflow`;
- installs shell functions for both names that discover the current Git worktree
  on every invocation.

The shell functions prefer the consumer's stable launcher:

```text
scripts/repoworkflow.py
```

That keeps the repository's gitlink-pinned RepoWorkflow version authoritative.
Fallbacks exist for RepoWorkflow itself and for consumers that have not yet
installed the stable launcher.

Because a child process cannot modify its parent shell, normal `rwf init` makes
persistent setup available to future Bash sessions. To activate the same setup
in the current Bash immediately, source the generated setup stream:

```bash
source <(rwf init --bash)
```

The sourceable form still performs the normal persistent initialization first;
its standard output contains only Bash code so `source` can consume it safely.
After it returns, both command names and their completion are active in that same
shell.

The functions resolve the repository on every invocation. A single shell can
therefore move between different RepoWorkflow-enabled repositories and each
`rwf` invocation will use that repository's own launcher and pinned engine.

Initialization is idempotent. Re-running it refreshes RepoWorkflow-managed
content without duplicating the `.bashrc` block. Existing unrelated hooks or
shell-integration files are not overwritten silently; use `--force` only when
replacement is intentional.

Outside a Git worktree, or in a worktree without `.ci/repoworkflow.json`, the
command fails with an actionable error instead of guessing a repository.
