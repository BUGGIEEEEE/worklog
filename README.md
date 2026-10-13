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
| Delegating | Subagent in the same session: put "do not run Worklog commands (use·save·skip)" in its prompt; the delegating session records the result in the same turn (`[위임: …]`, files as artifacts+check). Separate session: open it with the hooks and start it with `<id> 이어서. 하위 작업: <name>`; it records by itself, and the opener adopts the result after `show`. For an independent goal, list in that prompt which decisions and constraints carry over |
| Pause | `워크로그 꺼` ("worklog off", whole project). `워크로그 켜` resumes. Nothing is recorded while off |
| Update | a git clone checks the origin tags in the background once a day (session start, never waits) and the next session shows one line when a newer version exists. Nothing changes by itself: run `python3 -B worklog/core/wl.py update` to fast-forward to the newest tag of the same major version and reinstall the current project; `update rollback` goes back; `update --mode off` silences the line. A new major version is announced only. Hooks stay unchanged, so no re-trust |

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

Check the install: `python3 -B worklog/core/wl.py version` prints the core version (see `CHANGELOG.md`).

Requirements: Python 3.9+ (tested on 3.9.6 and 3.14), macOS or Linux. Keep the clone where it is (the hooks call it by path). The installer writes only inside the project and backs up every file it changes.

## Good to know

- `save` results tell you whether the hooks are alive (`hooks`, and a `warning` when they are not) and whether a `check` quote merely repeated the rule's own text (`self_quoted`, not evidence that the rule was followed).
- The record detects accidental edits, not deliberate tampering.
- Pi is untested. The model-facing rules and messages are in Korean.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · MIT ([LICENSE](LICENSE))
