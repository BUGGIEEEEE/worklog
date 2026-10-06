# worklog

[한국어](README.ko.md)

**Install it once per project. After that there is nothing to do.** Claude Code and Codex write what matters about the work — goal, decisions, constraints, next action — into `.worklog/` in the project folder, and read it back automatically when a session starts or the conversation is compacted.

## What it does

- **Keeps context across compaction and new sessions.** The current state is injected into the model at session start and after every compaction, so the model continues from the record instead of guessing.
- **Does not let a turn end without a record.** If the model ends a turn without saving (or declaring the turn read-only), a Stop hook sends it back to save.
- **Keeps separate works apart.** One project can hold several works. At session start the model shows the list, and you pick one with `<id> 이어서` ("continue <id>") or `새 작업: <title>` ("new work: <title>"). Nothing is saved before you pick; if you don't, the model asks.
- **Lets several tools share one record.** Claude Code and Codex can work on the same project in turn; each reads the other's entries before writing.

## Install

Requirements: Python 3 (standard library only; developed and tested on 3.14, expected to work on 3.10+), macOS or Linux. Checked with Claude Code 2.1.x and Codex CLI 0.15x.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project   # Claude Code
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project   # Codex
```

Then, once per project:

- **Codex:** trust the project, then trust the three Worklog hooks in `/hooks`.
- **Claude Code:** if the project is a git repository, accept the folder-trust dialog on first start.

The installer writes only inside the project (a rules block in `CLAUDE.md`/`AGENTS.md`, three hooks, a skill, an empty `.worklog/`), backs up every file it changes, and can be re-run safely. Keep the clone where it is — the hooks call it by absolute path. Per-tool details, Pi, and recovery: [docs/ADAPTERS.md](docs/ADAPTERS.md).

## After install

Work as usual.

- **In the first session:** say `새 작업: <title>` to create your first work.
- **To see where things stand:** open `.worklog/works/<id>/state.md` (goal, active decisions, constraints, next action).
- **To change a decision or lift a constraint:** say so in the conversation. The model records your words; a constraint is lifted only on your say-so.
- **If something looks wrong:** run `python3 -B worklog/core/wl.py verify --all` in the project folder. The state files are projections of each work's ledger (`.worklog/works/<id>/events.jsonl`) and `show` rebuilds them from it.
- **Coming from `worklog/1`:** run `python3 -B worklog/tools/migrate_v1_to_v2.py --project /path/to/project --work-id <id>` to preview, add `--apply` to migrate, then re-run the installer.

## Limits — read before relying on it

- **Whether a constraint ends up inside a produced file is still the model's judgment.** In 12 verification runs the model reported every constraint as reflected in 8; a keyword check of the produced files found 7. If it matters, say "put the constraints in the file too".
- **The ledger detects accidental edits to past entries, not deliberate tampering.** Each entry is hash-chained to the previous one, but the last entry has no independent anchor.
- Pi: rules only, no hooks, untested. Each verification condition was run once. Interaction with your own user-level hooks was not checked.

Verification results: [docs/VERIFICATION.md](docs/VERIFICATION.md). Record format `worklog/2` (stable; a format change means re-migrating existing ledgers): [docs/FORMAT.md](docs/FORMAT.md). The model-facing rules and CLI messages are written in Korean.

## Tests

```sh
python3 -B -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
