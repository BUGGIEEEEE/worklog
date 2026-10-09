# AGENT.md — for an AI agent asked to install, update or explain worklog

You are reading this because a user gave you this repository and asked you to install or update it. Explain things to the user in their language. Human-facing overview: [README.md](README.md) / [README.ko.md](README.ko.md).

## What to tell the user (the essentials)

- **Purpose.** Coding agents lose decisions when a conversation is compacted or a new session starts. worklog makes the agent write each work's goal, decisions, constraints and next action into `.worklog/` in the project, and read it back at session start and after compaction.
- **How it works.** Three hooks per project: SessionStart injects the current state, UserPromptSubmit counts the turn, Stop blocks a turn that ended without a save (or an explicit read-only `skip`). Records live in `.worklog/works/<id>/`: an append-only, hash-chained `events.jsonl` plus `state.json`/`state.md` rebuilt from it. One project can hold several works; the user names the work (`<id> 이어서` / `새 작업: <title>`) and the agent never guesses.
- **What changes in their project.** Claude Code: a rules block in `CLAUDE.md`, hooks in `.claude/settings.local.json`, a skill in `.claude/skills/worklog/`, an empty `.worklog/`. Codex: a rules block in `AGENTS.md`, hooks in `.codex/hooks.json`, a skill in `.agents/skills/worklog/`, an empty `.worklog/`. Nothing outside the project is touched. Every changed file is backed up as `<file>.bak-worklog-<timestamp>`.
- **What they must do themselves.** Codex: trust the project, then trust the three hooks in `/hooks`. Claude Code: accept the folder-trust dialog on first start if the project is a git repository. You cannot do these for them; do not edit `~/.codex/config.toml` or any global settings.
- **Pausing.** Saying `워크로그 꺼` pauses the whole project (marker file `.worklog/off`); `워크로그 켜` resumes. Time spent off is not recorded. Only the user's words can turn it off.
- The model-facing rules and CLI messages are written in Korean.

## Install

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
6. After the first turn, check that the hooks really run: the JSON result of `save`/`skip` (or `wl.py verify --all --tool <tool> --session <id>`) has `hooks` with `turn_start: true`. A `warning` "Hook 미작동 의심" means the hooks are not trusted, not installed, or run under another session ID; report it to the user instead of working around it.

## Update

```sh
cd worklog && git pull
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project   # again, per tool and project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

`git pull` updates the core, which the hooks run directly. Re-running the installer refreshes the rules block and the skill in each project. An unchanged hook is left byte-for-byte, so Codex does not ask for trust again; only if the clone was moved are the hooks rewritten, and then the user must re-trust them in `/hooks`.

When an update changes how `state.md`/`state.json` are rendered (2026-10-09 did: source tags, current scope line, artifact summary), `verify` reports the old projections as mismatched until the next `show`, `use` or save rebuilds them from the ledger. The ledgers themselves are untouched; run `python3 -B worklog/core/wl.py show --work <id> --root /path/to/project` once per work if you want `verify --all` clean right away.

## Verify

- In the clone: `python3 -B -m unittest discover -s tests` (74 tests, all must pass; verified on Python 3.9.6 and 3.14).
- In a project: `python3 -B worklog/core/wl.py verify --all` checks every ledger's hash chain and the index. With `--tool <tool> --session <id>` it also reports `hooks` (which of the three hooks ran in that session).
- A dry-run of the installer right after installing lists no `changed` files.

## Rules while you do this

- Write only inside the project and the clone. Never edit the hook commands, `.worklog/` contents or ledgers by hand; the installer and `wl.py` are the only writers.
- Do not create works or save records for the user during installation. Do not turn worklog off on your own; `off` requires the user's words.
- If something refuses or fails, stop and report; do not work around it.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/FORMAT.md](docs/FORMAT.md), [docs/VERIFICATION.md](docs/VERIFICATION.md).
