# worklog

[한국어](README.ko.md) · AI agent asked to install or update this? Read [AGENT.md](AGENT.md).

**Claude Code and Codex forget what was decided when a conversation is compacted or a new session starts. worklog makes them write it down and read it back.** Install it once per project. After that there is nothing to do.

## What it does

- The model writes the goal, decisions, constraints and next action of each work into `.worklog/` in the project folder, and reads it back automatically at session start and after every compaction.
- It cannot end a turn without saving (or saying the turn was read-only). A hook sends it back.
- One project can hold several works. You say which one: `<id> 이어서` ("continue <id>") or `새 작업: <title>` ("new work: <title>"). The model never guesses.
- Claude Code and Codex share the same record.

## Install

Requirements: Python 3 (standard library only; tested on 3.14, expected to work on 3.10+), macOS or Linux. Checked with Claude Code 2.1.x and Codex CLI 0.15x.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project   # Claude Code
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project   # Codex
```

Then, once per project:

- **Codex:** trust the project, then trust the three Worklog hooks in `/hooks`.
- **Claude Code:** if the project is a git repository, accept the folder-trust dialog on first start.

Keep the clone where it is: the hooks call it by its path. The installer writes only inside the project and backs up every file it changes. You can also give this page's address to Claude Code or Codex and ask it to install; it follows [AGENT.md](AGENT.md).

## Using it

- **First session:** say `새 작업: <title>`. Later sessions show the list of works; say `<id> 이어서`.
- **Where things stand:** open `.worklog/works/<id>/state.md`.
- **Pause it in a project:** say `워크로그 꺼` ("worklog off"); the whole project pauses, and the time it was off is not recorded. Say `워크로그 켜` ("worklog on") to resume. Projects where you did not run the installer are not affected at all.

## Update

```sh
cd worklog && git pull
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project   # again, per project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

`git pull` updates the core. Re-running the installer updates the rules inside each project. Hooks are left unchanged, so Codex does not ask you to trust them again.

## Limits

- Whether a constraint ends up inside a produced file is still the model's judgment. In 12 verification runs every content constraint was reflected, but each condition was run only once. If it matters, say "put the constraints in the file too".
- The record detects accidental edits to past entries, not deliberate tampering.
- Pi: rules only, no hooks, untested.
- The model-facing rules and messages are written in Korean.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md) (per-tool setup, recovery, migration from `worklog/1`), [docs/FORMAT.md](docs/FORMAT.md) (record format), [docs/VERIFICATION.md](docs/VERIFICATION.md) (test results).

## License

MIT — see [LICENSE](LICENSE).
