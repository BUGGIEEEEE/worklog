# AGENT.md — for an AI agent asked to install, update or explain worklog

You are reading this because a user gave you this repository and asked you to install or update it. Explain things to the user in their language. Human-facing overview: [README.md](README.md) / [README.ko.md](README.ko.md).

## What to tell the user

Human-facing explanations live in [README.md](README.md) (English) and [README.ko.md](README.ko.md) (Korean): purpose, how it works, what changes in their project, the trust steps, pausing, update and removal. Most of each README is figures (PNG); the same content as text, section by section, is in [docs/figures.en.html](docs/figures.en.html) and [docs/figures.ko.html](docs/figures.ko.html) — read those when you need to quote or explain it. Point the user to the README or repeat it in their language. Two things to always say: the model-facing rules and CLI messages are Korean, and the first session starts with `새 작업: <title>` (the work id is built from the Latin letters and digits in the title; none → `work`).

## Install

0. **Ask which tools to install for, before anything else.** An agent tends to install only for itself; the user may use both. Look for `~/.claude` (Claude Code) and `~/.codex` (Codex) on this machine. If both exist, ask one question that says: which tools to install for (propose your own tool plus every other tool found); that both share the same `.worklog/`, so each sees the other's records; that Codex needs the user to trust the three hooks in `/hooks` after installing (you cannot do that); and that Claude Code shows a folder-trust dialog in a git repository. If only your own tool exists, install for it without asking. Do not install while the answer is pending: end your turn with the question. Pi is unverified: never propose it, install for it only when the user names it. Then run the installer once per chosen tool and never for a tool the user did not choose. Running it without `--tool` writes nothing and prints this same instruction plus which tools were found.
1. Check: `python3 --version` is 3.9 or newer (the macOS Command Line Tools python3 is 3.9.6 and works), macOS or Linux.
2. Clone to a permanent location. The hooks call `core/wl.py` by absolute path, so moving the clone later breaks them until the installer is re-run.
   ```sh
   git clone https://github.com/BUGGIEEEEE/worklog.git
   ```
3. Preview, then install, once per tool per project:
   ```sh
   python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project --dry-run
   python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project
   python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
   ```
   The output is JSON: `changed` lists the files it wrote. A refusal (exit 2, `error`) means nothing was written; show it to the user. `--no-worklog-dir` installs rules and hooks only, for a parent folder whose subfolders each keep their own `.worklog/`.
4. If the project already has `.worklog/events.jsonl` at its root, it uses the old format `worklog/1`. Migrate first: `python3 -B worklog/tools/migrate_v1_to_v2.py --project /path/to/project --work-id <id>` to preview, `--apply` to migrate, then run the installer.
5. Tell the user the trust steps above, and that the first session starts with `새 작업: <title>`.
6. After the first turn, check that the hooks really run: the JSON result of `save`/`skip` (or `wl.py verify --all --tool <tool> --session <id>`) has `hooks` with `session_start`, `turn_start` and `stop`, and no `warning`. A `warning` "Hook 미작동 의심" (no hook record at all) means the hooks are not trusted, not installed, or run under another session ID; report it to the user instead of working around it. `turn_start: false` by itself is normal in a Claude Code session driven by `!` shell input or other sessions' notifications (UserPromptSubmit does not fire there).

## Update

```sh
cd worklog && git pull
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project   # again, per tool and project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

`git pull` updates the core, which the hooks run directly. Re-running the installer refreshes the rules block and the skill in each project. An unchanged hook is left byte-for-byte, so Codex does not ask for trust again; only if the clone was moved are the hooks rewritten, and then the user must re-trust them in `/hooks`.

When an update changes how `state.md`/`state.json` are rendered (2026-10-09 did: source tags, current scope line, artifact summary), `verify` reports the old projections as mismatched until the next `show`, `use` or save rebuilds them from the ledger. The ledgers themselves are untouched; run `python3 -B worklog/core/wl.py show --work <id> --root /path/to/project` once per work if you want `verify --all` clean right away.

## Uninstall

0. **Ask what to remove, before anything else.** First see what is installed in the project without writing anything: `--tool all --dry-run` (or run it without `--tool`: it refuses and lists the installed tools). If two or more tools are installed, ask one question: remove codex only, claude only, or all (add "pi only" once Pi is supported). Only when the last tool would go, the same question also asks whether the records in `.worklog/` (`works/`, `index.json`, `project.md`) should stay (`--keep-records`) or go (`--delete-records`); the script refuses without that choice outside a terminal. If one tool is installed, ask only about the records. Tell the user that removing one tool keeps the records and the shared state (lock, off marker, `.gitignore` line) for the other, and that Codex hook trust in `~/.codex/config.toml` is not touched. Do not run while the answer is pending.

```sh
python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool all --keep-records --dry-run   # preview
python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool codex                          # one tool, another stays: no records choice needed
python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool all --keep-records             # or --delete-records
```

`--tool claude|codex|pi|all` is required with `--root`; the records and shared state stay while another tool is installed, and `--delete-records` is refused then. It reverts the rules block, the three hooks (other hooks and settings in the same file stay), the skill folder, the `.gitignore` lines, the session files and the manifest; a later reinstall continues kept records. Files it edits or deletes are backed up as `.bak-worklog-<timestamp>` (`--no-backup` to skip; `--purge-backups` also deletes the installer's earlier backups). The output is JSON (`removed`, `changed`, `kept`, `backups`, `notes`); a refusal (exit 2, `error`) changed nothing.

To remove worklog completely: `--all-projects --delete-records --home` (or `--keep-records`; `--all-projects` means every tool) uninstalls every project listed in `~/.worklog/installs.json` and then deletes `~/.worklog`; projects installed before 2.17.0 are not listed, so pass them with `--root` first. The script never deletes the clone; tell the user the printed `rm -rf` command. It also never touches Codex hook trust in `~/.codex/config.toml` or Claude Code folder trust; Codex users can remove the stale trust entries themselves if they wish.

## Verify

- In the clone: `python3 -B -m unittest discover -s tests` (all must pass; verified on Python 3.9.6 and 3.14).
- In a project: `python3 -B worklog/core/wl.py verify --all` checks every ledger's hash chain and the index. With `--tool <tool> --session <id>` it also reports `hooks` (which of the three hooks ran in that session).
- A dry-run of the installer right after installing lists no `changed` files.

## Rules while you do this

- Write only inside the project and the clone. Never edit the hook commands, `.worklog/` contents or ledgers by hand; the installer and `wl.py` are the only writers.
- Do not create works or save records for the user during installation. Do not turn worklog off on your own; `off` requires the user's words.
- If something refuses or fails, stop and report; do not work around it.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/FORMAT.md](docs/FORMAT.md), [docs/VERIFICATION.md](docs/VERIFICATION.md).
