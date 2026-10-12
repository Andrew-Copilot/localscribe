# Create the roadmap issues from an Android phone

This turns the roadmap backlog (R01–R18) into GitHub issues with one command, run inside a GitHub Codespace in your phone's browser. No personal access token is needed: Codespaces signs the GitHub CLI (`gh`) in for you.

- Issue definitions: [`roadmap-issues.json`](roadmap-issues.json) (kept in sync with [`issue-backlog.md`](issue-backlog.md); checked by the tests)
- Importer: [`scripts/create_roadmap_issues.py`](../../scripts/create_roadmap_issues.py)
- Result after a run: `issue-index.md` in this folder

The importer is safe to rerun. It only changes anything when you add `--apply`, and it finds existing issues by a hidden `<!-- roadmap-id:R01 -->` marker, so it never creates duplicates. The PHI/Box governance wording from the backlog is copied into the issues unchanged; R01 stays labelled `blocked`.

## Steps (Codespaces, about 5 minutes)

1. **Open the repository.** In Chrome, go to `https://github.com/Andrew-Copilot/localscribe`. If the page looks cut down, open Chrome's ⋮ menu and tick **Desktop site**.
2. **Create a Codespace.** Tap the green **Code** button → **Codespaces** tab → **Create codespace on main**. (If these files are not merged yet, switch the branch selector to the branch that contains them first.) If you already have one, tap its name to reopen it.
3. **Wait for setup.** The editor opens in the browser. The first start takes a few minutes; it is done when this file (`CREATE_ISSUES.md`) opens in the editor. The setup log ends with `Definitions OK: 18 issues, ...`.
4. **Open a terminal** if none is visible: ☰ menu → **Terminal** → **New Terminal**.
5. **Dry run** — shows what would happen and changes nothing. Copy and paste:

   ```bash
   python scripts/create_roadmap_issues.py
   ```

   Check the summary: `would create: 18` the first time, and a target of `Andrew-Copilot/localscribe`.
6. **Apply** — creates labels, milestones, and the issues:

   ```bash
   python scripts/create_roadmap_issues.py --apply
   ```

   The summary lists `created`, `reused`, `updated`, and `failed`. If it warns that milestones could not be created, the issues are still created, just without a milestone.
7. **Inspect the results.** Open `docs/roadmap/issue-index.md` in the editor, or view the issues at `https://github.com/Andrew-Copilot/localscribe/issues`. Running step 6 again is harmless; it should report `reused: 18`.
8. **Save the index to the repository:**

   ```bash
   git add docs/roadmap/issue-index.md
   git commit -m "docs: add generated roadmap issue index"
   git push
   ```

9. **Stop the Codespace** to save free hours: go to `https://github.com/codespaces`, tap ⋯ next to the codespace → **Stop codespace**. (It also stops by itself after 30 minutes of inactivity.)

## If GitHub asks you to sign in

If a command says `gh` is not signed in, or fails with `Resource not accessible by integration` / `HTTP 403`, sign in interactively in the same terminal:

```bash
unset GITHUB_TOKEN
gh auth login --web --hostname github.com --git-protocol https
```

`gh` shows a one-time code. Open `https://github.com/login/device` in another tab, enter the code, approve, then repeat step 6. Never paste an access token into any file in this repository.

## Optional: run from the Actions tab instead

After the workflow file is on the default branch:

1. Repository → **Actions** → **Create roadmap issues** → **Run workflow**.
2. Leave **confirm** empty for a dry run, or type exactly `CREATE_ROADMAP_ISSUES` to create the issues.
3. Open the finished run: the issue index appears in the run summary and as the `roadmap-issue-index` artifact. The workflow does not commit it; copy it into `docs/roadmap/issue-index.md` from a Codespace (step 8) if you want it in the repository.

The workflow uses only `issues: write` and read-only `contents`.

## Other options

| Option | Use |
|---|---|
| `--update-existing` | Rewrite existing roadmap issues to match the definitions (overwrites edits such as ticked checkboxes). Use with `--apply`. |
| `--validate-only` | Check the definitions file without contacting GitHub. |
| `python -m tests.test_roadmap_issues` | Run the offline tests for the importer. |
