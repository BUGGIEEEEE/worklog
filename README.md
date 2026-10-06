# worklog

[한국어](README.ko.md)

A shared, append-only work ledger for AI coding agents (Claude Code, Codex, Pi). Keeps goal / decisions / constraints / next action across compaction and new sessions, and enforces end-of-turn saves with hooks.

## Why

When a conversation is compacted or a new session starts, agents lose context: the goal drifts, earlier decisions are forgotten, and constraints the user stated ("no reminders", "don't touch other projects") quietly fall out of the final artifact. Rebuilding that context by re-reading notes and history is also expensive.

In a side-by-side comparison on the same task (2026-09-30), working without a ledger (plain built-in memory) took 9 tool calls and about 0.44M tokens, while the previous version of this tool (0.3.0) took 58 tool calls and about 3.1M tokens. The redesigned current core takes 5–8 tool calls and about 0.2–0.5M tokens (12 verification runs): about one tenth of the previous version, and on par with working without a ledger.

## How it works

```
save (once per turn)  →  .worklog/events.jsonl   append-only, hash-chained ledger
                      →  .worklog/state.json/.md current state, recomputed from the ledger
SessionStart hook     →  injects state.md at startup / resume / after compaction
UserPromptSubmit hook →  counts the turn
Stop hook             →  blocks the end of a turn that has neither save nor skip
skip "reason"         →  marks a read-only turn; writes nothing to the ledger
```

Each event is one JSON line chained to the previous one by sha256: a change to an earlier line that later events follow is detected on read. The last event has no independent reference point, so a change to it is not detected — this is not a defense against deliberate tampering. The state files are projections; if they disagree with the ledger, the ledger wins and `show` rebuilds them. The full format is in [docs/FORMAT.md](docs/FORMAT.md).

## Requirements

- Python 3.10+, standard library only.
- macOS or Linux (uses `flock`).
- Checked with Claude Code 2.1.x and Codex CLI 0.15x.

## Install

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git && cd worklog
```

Then, for each project you want to connect:

```sh
python3 -B tools/install_project.py --tool claude --root /path/to/project   # Claude Code
python3 -B tools/install_project.py --tool codex  --root /path/to/project   # Codex
```

Add `--dry-run` to see what would change. The installer writes only inside `--root`: it refuses if any write target (file, backup, new directory, or `.worklog`) would lead outside through a link, and refuses a `.worklog` that is a link at all. It backs up any file it changes to `<file>.bak-worklog-<date-time>` (adding `-1`, `-2`, … rather than overwriting an existing backup), and can be re-run safely (the managed block and Worklog hooks, including those from an earlier clone location, are replaced, not duplicated). It checks every target and prepares all content before writing, so a refusal (exit 2, e.g. an unreadable hook settings file) changes nothing.

If an install still fails partway (e.g. a disk or permission error while writing), restore each changed file from its `<file>.bak-worklog-<date-time>` copy, delete files that had no backup (they were newly created), and run the installer again.

What it creates:

| Tool | Files |
|---|---|
| Claude Code | `CLAUDE.md` rules block · three hooks in `.claude/settings.local.json` · `.claude/skills/worklog/SKILL.md` · empty `.worklog/` |
| Codex | `AGENTS.md` rules block · three hooks in `.codex/hooks.json` · `.agents/skills/worklog/SKILL.md` · empty `.worklog/` |
| Pi (`--tool pi`) | `AGENTS.md` rules block · `.pi/skills/worklog/SKILL.md` (no hooks) |

The empty `.worklog/` folder is the connection signal: hooks stay silent in folders without it. The ledger itself is created by the first `save`.

Hooks call `core/wl.py` by absolute path, so keep the clone where it is (or re-run the installer after moving it).

One-time trust steps:

- **Codex:** trust the project, then trust the three hooks in `/hooks`. If the hook definitions change, they must be trusted again.
- **Claude Code:** if the project is a git repository, the folder trust dialog appears once on first start.

Per-tool details: [docs/ADAPTERS.md](docs/ADAPTERS.md).

## Daily use

The installed rules tell the model to:

- **Turn start:** if it has not seen the current state since the last compaction (via the SessionStart injection or its own last save), run `show` once.
- **Turn end:** run `save` once with a JSON event on stdin. User requests and decisions carry a verbatim `quote`; constraints persist until the user changes them.
- **Read-only turn:** run `skip "reason"` instead of saving.
- **Artifacts:** a save that lists `artifacts` must `check` every active decision and constraint against the artifact body — a verbatim quote, or `미반영: <reason>` ("not reflected").

To see where things stand yourself, open `.worklog/state.md`.

| Command | Purpose |
|---|---|
| `wl.py show` | Print the current state (and mark it as read for this session) |
| `wl.py save` | Append one event from stdin JSON; verifies and rebuilds the state |
| `wl.py skip "reason"` | Declare a read-only turn; nothing is written to the ledger |
| `wl.py verify` | Check that state.json/state.md match the ledger |
| `wl.py hook` | SessionStart hook: inject state.md |
| `wl.py turn-start` | UserPromptSubmit hook: count the turn |
| `wl.py stop-hook` | Stop hook: block a turn that has neither save nor skip |

`wl.py help` prints the save input format. The model-facing rules and CLI messages are currently written in Korean.

## Multiple tools on one project

Several tools and sessions can share one `.worklog/`. Saves are serialized with a lock, and a save is rejected if another session has written since this session last read the state ("the record changed") — the model runs `show` and saves again. There is no exclusive owner; when the user explicitly hands work over, a save can record it with `takeover` (reason) plus the user's `quote`.

## Limitations

- Pi has no hooks here: instructions only, not enforced, and not tested.
- Whether a constraint is written into an artifact is still the model's judgment: runs in which the model reported no constraint as not reflected were 8/12; by the artifact-body keyword check it was 7/12 (sonnet-medium omitted one phrase without reporting it). The rules state this requirement explicitly in one line.
- Each verification condition was run once.
- Interaction with global (user-level) hooks has not been checked.

Verification details: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Format stability

The on-disk format is `worklog/1`. Changing the format means re-migrating existing ledgers; only additions that leave existing ledgers' meaning unchanged keep the same version.

## Tests

```sh
python3 -B -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
