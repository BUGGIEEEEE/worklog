# worklog

[한국어](README.ko.md) · AI agent? Read [AGENT.md](AGENT.md)

**Keeps Claude Code and Codex from forgetting what was decided after a compaction or a new session.** Install once per project. After that there is nothing to do.

## How it works

```
Install (once per project)
   │
   ▼
Session start ── the model reads the record in .worklog/
   │               several works? it asks → you: "<id> 이어서" (continue) or "새 작업: <title>" (new work)
   ▼
Working ──────── every turn it saves goal, decisions, constraints, next action
   │               a turn cannot end without a save (a hook sends it back)
   ▼
Compaction or new session ── it reads the record again and continues
```

## What appears in your project

```
project/
├── .worklog/works/<id>/state.md   current state: open it to see goal, decisions, constraints, next action
├── CLAUDE.md or AGENTS.md         one rules block for the model (your own content is kept)
└── 3 hooks                        read at session start, check for a save at turn end
```

Claude Code and Codex share the same `.worklog/`.

## What you do

| When | What |
|---|---|
| Install | commands below. Codex: trust the project and the 3 hooks in `/hooks`. Claude Code: accept the folder-trust dialog if the project is a git repository |
| First session | `새 작업: <title>` |
| Later sessions | pick from the list: `<id> 이어서` |
| Pause | `워크로그 꺼` ("worklog off", whole project). `워크로그 켜` resumes. Nothing is recorded while off |
| Update | `git pull`, then run the install commands again. Hooks stay unchanged, so no re-trust |

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

Requirements: Python 3.10+ (tested on 3.14), macOS or Linux. Keep the clone where it is (the hooks call it by path). The installer writes only inside the project and backs up every file it changes.

## Good to know

- Whether a constraint ends up inside a produced file is the model's judgment. If it matters, say "put the constraints in the file too".
- The record detects accidental edits, not deliberate tampering.
- Pi is untested. The model-facing rules and messages are in Korean.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · MIT ([LICENSE](LICENSE))
