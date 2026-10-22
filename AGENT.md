# AGENT.md — for an AI agent asked to install, update or explain worklog

You are reading this because a user gave you this repository and asked you to install or update it. Explain things to the user in their language. Human-facing overview: [README.md](README.md) / [README.ko.md](README.ko.md).

## What to tell the user

Human-facing explanations live in [README.md](README.md) (English) and [README.ko.md](README.ko.md) (Korean): purpose, how it works, what changes in their project, the trust steps, pausing, update and removal. Most of each README is figures (PNG); the same content as text, section by section, is in [docs/figures.en.html](docs/figures.en.html) and [docs/figures.ko.html](docs/figures.ko.html) — read those when you need to quote or explain it. Point the user to the README or repeat it in their language. Two things to always say: the model-facing rules and CLI messages are Korean, and (2.25.0) a project's record starts with the first request worth recording in it — `새 작업: <title>` names the work, otherwise the title is taken from the request (the work id is built from the Latin letters and digits in the title; none → `work`); `"auto": "off"` in `~/.worklog/config.json` restores "nothing until `새 작업:`".

## Install

0. **Ask which tools to install for, before anything else.** An agent tends to install only for itself; the user may use several tools. Look for `~/.claude` (Claude Code), `~/.codex` (Codex), `~/.gemini` (agy) and `~/.pi` (pi) on this machine. If more than one exists, ask one question that says: which tools to install for (propose your own tool plus every other tool found); that they all share the same `.worklog/` of a project, so each sees the others' records; that Codex needs the user to trust the three hooks in `/hooks` after installing (you cannot do that); and that Claude Code shows a folder-trust dialog in a git repository. If only your own tool exists, install for it without asking. Do not install while the answer is pending: end your turn with the question. Then run the installer once per chosen tool and never for a tool the user did not choose. Running it without `--tool` writes nothing and prints this same instruction plus which tools were found.
1. Check: `python3 --version` is 3.9 or newer (the macOS Command Line Tools python3 is 3.9.6 and works), macOS or Linux.
2. Clone to a permanent location. The hooks call `core/wl.py` by absolute path, so moving the clone later breaks them until the installer is re-run.
   ```sh
   git clone https://github.com/BUGGIEEEEE/worklog.git
   ```
3. Preview, then install, once per tool for the whole machine (`--user`, 2.21.0):
   ```sh
   python3 -B worklog/tools/install_project.py --tool claude --user --dry-run
   python3 -B worklog/tools/install_project.py --tool claude --user
   python3 -B worklog/tools/install_project.py --tool codex  --user
   python3 -B worklog/tools/install_project.py --tool agy    --user   # Antigravity CLI (2.24.0)
   python3 -B worklog/tools/install_project.py --tool pi     --user   # pi (2.24.0)
   ```
   `--user` writes the rules block, the three hooks and the skill into the tool's user-level files (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/skills/worklog/`; `~/.codex/AGENTS.md`, `~/.codex/hooks.json`, `~/.agents/skills/worklog/`; agy: `~/.gemini/config/rules/worklog.md`, the named hook `worklog` in `~/.gemini/config/hooks.json`, `~/.gemini/config/skills/worklog/`; pi: `~/.pi/agent/AGENTS.md`, the extension `~/.pi/agent/extensions/worklog.ts`, `~/.pi/agent/skills/worklog/`) and the manifest `~/.worklog/install.json`. Nothing is written into any project. The output is JSON: `changed` lists the files it wrote. A refusal (exit 2, `error`) means nothing was written; show it to the user. If the refusal names projects that still have project-level hooks, see Migrate below.
   To install for one project only (the 2.x way), use `--root /path/to/project` instead of `--user`; `--no-worklog-dir` then installs rules and hooks only, for a parent folder whose subfolders each keep their own `.worklog/`.
4. How a project gets connected: opening a session writes nothing. With `"auto": "on"` (the default; `--user` adds the key to `~/.worklog/config.json` when it is missing, reported as `config`) the first request worth recording in a folder with no works runs `new-work … --root <root>` (root = the git top level, or the nearest folder inside it that already has records; outside git, the folder itself); with `"auto": "off"` only `새 작업: <title>` does. `new-work` creates `.worklog/`, adds `.worklog/` to `.gitignore` in a git project, lists the folder in `~/.worklog/installs.json` and writes `.worklog/install.json`. Until then the SessionStart hook injects one line `[Worklog … | NOT_CONNECTED | root=… | auto=… | git=…]`. Do not create works for the user during installation. Commands for a misfiled record: `reassign <wrong id> <right id> --events E0003-E0005 --quote "…"` and `rename <id> "<title>" --quote "…"` (see docs/FORMAT.md). If the user opens their home folder as the project root and says `새 작업:`, the record lands in `~/.worklog/` — point that out before running it.
5. If a project already has `.worklog/events.jsonl` at its root, it uses the old format `worklog/1`. Migrate first: `python3 -B worklog/tools/migrate_v1_to_v2.py --project /path/to/project --work-id <id>` to preview, `--apply` to migrate.
6. Tell the user: Codex users trust the three hooks once in `/hooks`; sessions that were already open do not see the new hooks, so restart them; in a project that already has works, a new session asks once which work to record into unless the first message says `<id> 이어서`.
7. After the first turn in a connected project, check that the hooks really run: the JSON result of `save`/`skip` (or `wl.py verify --all --tool <tool> --session <id>`) has `hooks` with `session_start`, `turn_start` and `stop`, and no `warning`. A `warning` "Hook 미작동 의심" (no hook record at all) means the hooks are not trusted, not installed, or run under another session ID; report it to the user instead of working around it. `turn_start: false` by itself is normal in a Claude Code session driven by `!` shell input or other sessions' notifications (UserPromptSubmit does not fire there).

## Migrate (from per-project installs, 2.21.0)

A project that still has this tool's project-level hooks would run them twice next to the user-level hooks (two turn counts, two Stop checks), so `--user` refuses while `~/.worklog/installs.json` lists such a project. Ask the user, then:

```sh
python3 -B worklog/tools/install_project.py --tool claude --user --migrate --dry-run   # shows what goes in each project
python3 -B worklog/tools/install_project.py --tool claude --user --migrate
```

`--migrate` removes the rules block, the three hooks, the skill and the manifest entry from those projects (backups as usual) and keeps their records, session files, `.worklog/` and the `.gitignore` line, so they stay connected. Projects installed before 2.17.0 are not in the registry: if the user sees the SessionStart injection twice in a project, run `python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool <tool> --keep-records` there. Codex: the user-level hooks need one trust in `/hooks`; the removed project hooks need nothing.

## Update

```sh
cd worklog && git pull
python3 -B worklog/tools/install_project.py --tool claude --user   # again, per tool
python3 -B worklog/tools/install_project.py --tool codex  --user
```

`git pull` updates the core, which the hooks run directly. Re-running the installer refreshes the rules block and the skill. An unchanged hook is left byte-for-byte, so Codex does not ask for trust again; only if the clone was moved are the hooks rewritten, and then the user must re-trust them in `/hooks`. `wl.py update` does the pull (same major version, tags only) and the `--user` reinstall together; a project installed with `--root` is reinstalled with `--root` again (or by `wl.py update --root <project>`).

When an update changes how `state.md`/`state.json` are rendered (2026-10-09 did: source tags, current scope line, artifact summary), `verify` reports the old projections as mismatched until the next `show`, `use` or save rebuilds them from the ledger. The ledgers themselves are untouched; run `python3 -B worklog/core/wl.py show --work <id> --root /path/to/project` once per work if you want `verify --all` clean right away.

## Uninstall

0. **Ask what to remove, before anything else.** Machine-level: ask whether to remove for codex only, claude only, or all; the projects' records stay either way. Project-level (`--root`): first see what is installed there without writing anything: `--tool all --dry-run` (or run it without `--tool`: it refuses and lists the installed tools, including a folder that is only connected). If two or more tools are installed, ask which; only when the last tool would go, the same question also asks whether the records in `.worklog/` (`works/`, `index.json`, `project.md`) should stay (`--keep-records`) or go (`--delete-records`); the script refuses without that choice outside a terminal. Tell the user that with user-level hooks a folder whose `.worklog/` stays is still connected (pause it with `워크로그 꺼`, disconnect it with `--delete-records`), and that Codex hook trust in `~/.codex/config.toml` is not touched. Do not run while the answer is pending.

```sh
python3 -B worklog/tools/uninstall_project.py --user --tool all --dry-run                                  # preview
python3 -B worklog/tools/uninstall_project.py --user --tool codex                                          # one tool
python3 -B worklog/tools/uninstall_project.py --user --tool all                                            # the machine-level install; records stay
python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool all --delete-records          # one project's record (or --keep-records)
```

`--user` reverts the user-level rules block, the three hooks (other hooks and settings in the same file stay), the skill folder and the manifest entries. `--root` reverts a project-level install (`--tool claude|codex|pi|all` required): block, hooks, skill folder, the session files and the manifest entry; the records and shared state stay while another tool is installed, and `--delete-records` is refused then. The `.gitignore` line goes only with `--delete-records` (2.21.0: a kept record must not end up in a commit). Files it edits or deletes are backed up as `.bak-worklog-<timestamp>` (`--no-backup` to skip; `--purge-backups` also deletes the installer's earlier backups). The output is JSON (`removed`, `changed`, `kept`, `backups`, `notes`); a refusal (exit 2, `error`) changed nothing.

To remove worklog completely: `--user --tool all`, then `--all-projects --delete-records --home` (or `--keep-records`; `--all-projects` means every tool) uninstalls every project listed in `~/.worklog/installs.json` and then deletes `~/.worklog`; projects connected before 2.17.0 are not listed, so pass them with `--root` first. The script never deletes the clone; tell the user the printed `rm -rf` command. It also never touches Codex hook trust in `~/.codex/config.toml` or Claude Code folder trust; Codex users can remove the stale trust entries themselves if they wish.

## Verify

- In the clone: `python3 -B -m unittest discover -s tests` (all must pass; verified on Python 3.9.6 and 3.14).
- In a project: `python3 -B worklog/core/wl.py verify --all` checks every ledger's hash chain and the index. With `--tool <tool> --session <id>` it also reports `hooks` (which of the three hooks ran in that session).
- A dry-run of the installer right after installing lists no `changed` files (with `--user`, only the manifest).
- In a folder without `.worklog/`, `python3 -B worklog/core/wl.py show` prints "연결되지 않은 폴더" and the SessionStart hook injects a single NOT_CONNECTED line: nothing else should happen there.

## Rules while you do this

- Write only inside the tool's user-level files (`--user`), the project (`--root`) and the clone. Never edit the hook commands, `.worklog/` contents or ledgers by hand; the installer and `wl.py` are the only writers.
- Do not create works or save records for the user during installation. Do not turn worklog off on your own; `off` requires the user's words.
- If something refuses or fails, stop and report; do not work around it.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/FORMAT.md](docs/FORMAT.md), [docs/VERIFICATION.md](docs/VERIFICATION.md).
