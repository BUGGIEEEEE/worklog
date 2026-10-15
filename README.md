# worklog

[한국어](README.ko.md) · AI agent? Read [AGENT.md](AGENT.md)

**Keeps Claude Code and Codex from forgetting what was decided, even after a compaction or a new session.** Ask the AI to install it; after that you only name the work you want to continue.

The phrases you type are Korean (the model-facing rules and messages are Korean too). They are short; copy them from this page.

## How to use it

### Install — ask the AI

Say to the AI: `Clone https://github.com/BUGGIEEEEE/worklog and install Worklog in this project`

The agent first asks which tools to install for (Claude Code, Codex, or both), then runs the commands below. Clone once; connect (install) once per project and tool. You can also run them yourself.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /path/to/project
python3 -B worklog/tools/install_project.py --tool codex  --root /path/to/project
```

Only you can do: Codex — in the first session, trust the project, then run `/hooks` and trust the three hooks it lists. Claude Code — accept the folder-trust dialog if the project is a git repository.

Check the install — it prints the core version (see `CHANGELOG.md`):

```sh
python3 -B worklog/core/wl.py version
```

Requirements: Python 3.9+ (tested on 3.9.6 and 3.14), macOS or Linux. Keep the clone where it is (the hooks call it by path). The installer writes only inside the project, backs up every file it changes, and lists the project in `~/.worklog/installs.json` (used by the uninstaller).

### What you say while working

| When | You say | Then |
|---|---|---|
| First session | `새 작업: 종이 노트 습관 계획 guide` — "new work: paper-notebook habit plan guide" | The work `guide` is created. The id is built from the Latin letters and digits in the title (none → `work`) |
| Next session | `guide 이어서. plan.md 써 줘.` — "continue guide. write plan.md" | The record is loaded and the work picks up where it left off |
| Refer to another work | `guide에서 정한 시간 배분을 참고해 줘` — "use the time split decided in guide" | The model reads guide's record. Only what you asked for is brought over |
| Delegating | Just tell the agent to delegate. If you open a separate session yourself, start its first prompt with `<id> 이어서. 하위 작업: <name>` ("continue <id>. subtask: <name>"); for an independent work that finishes on its own, use `새 작업: <title>` and list which decisions and constraints it inherits | The agent keeps the record as the rules say |
| Several works | — | At session start the model lists them and asks which one to continue |
| Saving | — | The model saves every turn (a read-only turn records a skip). Nothing for you to do |

### Now and then

| When | You say |
|---|---|
| Pause | `워크로그 꺼` ("worklog off", whole project). `워크로그 켜` resumes. Nothing is recorded while off |
| Update | A newer version is announced in one line at session start (a git clone checks the origin tags in the background once a day). Say `Worklog 업데이트해 줘` ("update Worklog") → `python3 -B worklog/core/wl.py update` fast-forwards to the newest tag of the same major version and reinstalls the current project. `update rollback` undoes it, `update --mode off` silences the notice |
| Current state | Say `현재 작업 상태 보여 줘` ("show the current work state"), or open `.worklog/works/<id>/state.md` |
| Remove | Say `Worklog 제거해 줘` ("remove Worklog"). The agent asks which tool to remove and, only when the last tool goes, whether to keep the records in `.worklog/`. Example: `python3 -B worklog/tools/uninstall_project.py --root /path/to/project --tool all --keep-records` (`--delete-records` removes the records too; `--tool codex` removes one tool only). It reverts the rules block, the three hooks, the skill and the `.gitignore` line, backing up what it changes. Full removal and all options: [AGENT.md](AGENT.md) |

## Unit of record

```
project/
└── .worklog/                  one per project
    └── works/                 one folder per work — decisions and constraints never mix between works
        ├── guide/
        │   ├── events.jsonl   history: every decision and result, in order, append-only
        │   └── state.md       current state: the goal, decisions, constraints and next step in force now
        └── report/
```

- Every save appends one line to the history; the current state is recomputed from it. When a value changes, the old decision stays in the history and only the newest is in the current state.
- Claude Code and Codex share the same `.worklog/`. In a git project `.worklog/` is added to `.gitignore` (the record is per-machine state and quotes you, so it stays out of git).
- What appears in your project: one rules block in `CLAUDE.md` or `AGENTS.md` (your own content is kept), 3 hooks, `skills/worklog/` (Claude: `.claude/`, Codex: `.agents/`), one `.gitignore` line.

## How it works (figures)

Decisions and constraints set in session 1 still apply in a new session, and after a long conversation has been compacted several times.

![Example: what was set in session 1 holds in session 2 and after compaction](docs/img/en-03-example.png)

Worklog adds only two layers to the model's input: the rules block (always the same) and a record summary attached at session start. The user message is unchanged. Numbers are from one run each, Claude opus, 2026-10-15.

![What the model receives on the first turn of session 2, without and with Worklog](docs/img/en-04-context.png)

The actual text of the record summary, and what the model takes from each line.

![Inside the injected record summary](docs/img/en-05-injection.png)

The order in which one turn actually runs: what the user, the Worklog tool and the model each do.

![One turn with Worklog](docs/img/en-06-flow.png)

## Good to know

- **Claude Code and Codex work the same way.** In both, the model input gets the rules block and the record summary in the same way, and both read and write the same `.worklog/` of a project. Only the settings file names differ. Pi support is planned (untested today). The model-facing rules and messages are Korean.

  | | File holding the rules block | Hook settings |
  |---|---|---|
  | Claude Code | `CLAUDE.md` | `.claude/settings.local.json` |
  | Codex | `AGENTS.md` | `.codex/hooks.json` |

- **If another window changed the same work**: the record summary arrives once, at session start, so another session may save in the meantime. When this session saves, the tool refuses with "the record has changed" and the model re-reads the record and saves again. Nothing for you to do.
- Situations where the record and reality can drift — `/rewind`, git worktrees, a deleted artifact — are reported by the tool as warnings. Details: [docs/ADAPTERS.md](docs/ADAPTERS.md) (Korean).
- The record detects accidental edits, not deliberate tampering.

Details: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · MIT ([LICENSE](LICENSE))
