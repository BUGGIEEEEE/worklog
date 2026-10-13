# Changelog

Tags are set by the author only; an external PR gets a tag only after the author merges and reviews it.
Numbering x.y.z — decided by *what changed*, never by what the user has to do afterwards. A unit test keeps `VERSION` equal to the first heading below and every heading exactly one step above the previous one.
- **x (major)**: the ledger structure changes (`FORMAT`, e.g. `worklog/2` → `worklog/3`). Ships with a migration script. `update` never crosses this line by itself.
- **y (minor)**: anything the model can notice changes — what the core writes (ledger fields), refuses or shows (JSON keys and values, injection lines, refusal and warning text), what the installer writes, `update.py`, and the model-facing rules (`adapters/rules.md`, `SAVE_HELP`). Touching the rules file is always y, even for a typo, so nobody has to argue what counts. Rule of thumb: if an existing test expectation must change, it is at least y.
- **z (patch)**: everything the model cannot notice — comments, refactors with identical output, tests only, text meant for people (stderr, docstrings). Cores that differ only in z read each other's ledgers without `warning_core`.
- Docs only (README, docs/, this file): no new number, no tag.
`python3 -B core/wl.py version` prints the installed number.

tag는 작성자만 붙인다. 번호 x.y.z는 *무엇이 바뀌었나*로 정한다(사용자가 할 일로 정하지 않는다). 단위 테스트가 `VERSION` = 아래 첫 제목, 그리고 모든 제목이 바로 앞 제목보다 정확히 한 자리만 큰지 지킨다.
- **x(주)**: 원장 구조 변경(`FORMAT`, 예: `worklog/2` → `worklog/3`). 마이그레이션 스크립트 동반. `update`는 이 경계를 스스로 넘지 않는다.
- **y(부)**: 모델이 알아챌 수 있는 변경 — 코어가 쓰는 것(기록 필드), 거부하는 것, 보여 주는 것(JSON 키·값, 주입 줄, 거부·경고 문장), 설치기가 쓰는 파일, `update.py`, 모델이 읽는 규칙(`adapters/rules.md`, `SAVE_HELP`). 규칙 파일은 오타 수정이라도 항상 y다(무엇이 해당하는지 다투지 않기 위해). 판정 요령: 기존 테스트의 기대값을 고쳐야 하면 최소 y.
- **z(끝)**: 모델이 알아챌 수 없는 변경 — 주석, 출력이 같은 리팩터, 테스트만, 사람이 보는 글(stderr, docstring). z만 다른 코어끼리는 서로의 기록을 `warning_core` 없이 읽는다.
- 문서만(README, docs/, 이 파일): 번호·tag 없음.
`python3 -B core/wl.py version`으로 설치된 번호를 확인한다.

## 2.11.0 — 2026-10-13
Installer: when the project is a git repository, `.gitignore` gets `.worklog/sessions/` and `.worklog/.lock` (lines already present are left alone; an existing `.gitignore` is backed up like every other file). Session files change on every turn and are per-machine state; committing them made Claude Code's auto mode show a diff after every save or skip. The record under `works/` stays committable. Existing projects that already track them: run `git rm -r --cached .worklog/sessions .worklog/.lock` once after reinstalling. Not applied with `--no-worklog-dir`. Core logic unchanged.
설치기: 프로젝트가 git 저장소면 `.gitignore`에 `.worklog/sessions/`와 `.worklog/.lock`을 추가한다(이미 있는 줄은 그대로, 기존 `.gitignore`는 다른 파일처럼 백업). 세션 파일은 턴마다 바뀌는 기기별 상태라 커밋하면 Claude Code auto 모드가 save·skip마다 diff를 보여 줬다. `works/`의 기록은 그대로 커밋할 수 있다. 이미 추적 중인 프로젝트는 재설치 뒤 `git rm -r --cached .worklog/sessions .worklog/.lock`을 한 번 실행한다. `--no-worklog-dir`에는 적용하지 않는다. 코어 논리 변경 없음.

## 2.10.1 — 2026-10-13
Tests only: `test_core_warning_on_newer_event` derived its "newer core" version from a hard-coded `2.10.0`, which stopped being newer once 2.10.0 shipped; it now uses the current minor number plus one. No change the model can notice.
테스트만: `test_core_warning_on_newer_event`가 "더 새로운 코어"로 `2.10.0`을 고정해 두어 2.10.0 배포 뒤에는 더 새롭지 않았다. 이제 현재 부 번호 +1을 쓴다. 모델이 알아챌 변경 없음.

## 2.10.0 — 2026-10-13
The `new-work` notice now matches rule 2.9.0 B': "decisions and constraints to inherit are only those written in the prompt that delegated this work; if the prompt has none, ask the user" (was: "ask the user"). `SAVE_HELP` comment updated to the same wording. Core logic unchanged; only the text the model reads.
`new-work`의 notice를 2.9.0 B'와 맞췄다: "이어받을 결정·제약은 이 작업을 맡긴 프롬프트에 적힌 것만 다시 저장하세요. 프롬프트에 없으면 사용자에게 확인하세요."(이전: "사용자에게 확인"). `SAVE_HELP` 주석도 같은 문구. 코어 논리는 그대로이고 모델이 읽는 문장만 바뀐다.

## 2.9.0 — 2026-10-13
Two sentences added to rules.md (and one comment line in `SAVE_HELP`). (A) Operating instructions to the agent — about tools, subagents, evaluators, hooks, goals, how to ask, whether to run tests ("do / don't do X") — are not saved as constraints: follow them in that turn and mention them in the summary only; if the user says they persist ("from now on"), save a constraint. Seen in I5, where two Codex runs stored a harness instruction as a fifth constraint. (B) A turn that delegates an independent goal to a separate session (`새 작업:`) may save `[위임: …] 별도 작업 <id>로 맡김` on the parent work (optional); after that neither work is saved while the sub-session runs. When delegating an independent goal, the opener lists in the sub-session's prompt which decisions and constraints carry over (or "none"); the sub-session takes that as the user's instruction and does not ask again. Seen in M8b, where the text left this open and Codex sub-sessions stopped to ask about inheritance (the `new-work` notice) instead of writing the file. No core behaviour change.
rules.md에 두 문장(그리고 `SAVE_HELP` 주석 한 줄)을 추가했다. (A) 에이전트 운영 지시(도구·서브에이전트·평가기·Hook·Goal·질문 방식·테스트 실행 여부에 대한 "~하지 마/써라")는 제약으로 적지 않는다. 그 턴에 지키고 summary에만 남기며, 사용자가 "앞으로"처럼 지속을 말하면 제약으로 적는다. I5에서 Codex 2회가 시험 운영 지시를 다섯째 제약으로 저장한 것을 보고 넣었다. (B) 독립 목표를 `새 작업:`으로 별도 세션에 맡긴 턴은 상위 작업에 `[위임: …] 별도 작업 <id>로 맡김`을 save해도 된다(선택). 그 뒤 하위가 도는 동안 두 작업 모두 save하지 않는다. 독립 목표를 맡길 때는 하위 프롬프트에 이어받을 결정·제약을 적고(없으면 "없음"), 하위 세션은 그것을 사용자 지시로 보고 승계 여부를 다시 묻지 않는다. M8b에서 규칙이 비워 둔 부분이며, Codex 하위 세션이 파일을 쓰지 않고 `new-work` notice대로 승계 여부를 물으며 멈춘 원인이다. 코어 동작 변경 없음.

## 2.8.0 — 2026-10-13
Delegation rule split into two bullets (rules.md). Subagent (same session): the session given the work saves in the same turn, the delegation prompt forbids Worklog commands, `[위임: …]` summary, artifacts+check, proposals as `"source": "model"`. Separate session: opened with hooks running, first prompt `"<work id> 이어서. 하위 작업: <name>"`, **no forbidding line** (the sub-session saves for itself), same goal keeps the same work id, the opening session skips while the sub-session runs and saves what it adopts after `show`; if the sub-session ended without saving, the opening session saves on its behalf with "하위 세션 기록 없음". The 2.7.0 wording applied the forbidding line and the same-turn save to both cases, which contradicted the separate-session half. Core unchanged.
위임 규칙을 두 줄로 나눴다(rules.md). 서브에이전트(같은 세션 안): 지정받은 세션이 같은 턴에 save, 위임 프롬프트에 Worklog 명령 금지문, `[위임: …]` summary, artifacts+check, 제안은 `"source": "model"`. 별도 세션: Hook이 도는 방식으로 열고 첫 프롬프트 `"<작업 id> 이어서. 하위 작업: <이름>"`, **금지문은 넣지 않는다**(하위 세션이 스스로 save), 같은 목표는 같은 작업 id, 도는 동안 skip, 끝나면 `show` 뒤 채택 save, 하위가 save 없이 끝나면 대신 save하고 "하위 세션 기록 없음". 2.7.0 문장은 금지문과 같은 턴 save를 두 경우에 함께 적어 별도 세션 쪽과 모순이었다. 코어 불변.

## 2.7.0 — 2026-10-12
Delegation rule (rules.md, `SAVE_HELP`): when a subagent or a separate session does the work, the session that was given the work saves in the same turn, tells the delegate not to run Worklog commands, starts the summary with `[위임: …]` (never in decision or constraint text), records the delegate's files as artifacts with checks and its proposals as `"source": "model"`. Separate sessions are opened with hooks running and a first prompt of `"<work id> 이어서. 하위 작업: <name>"`; the same goal keeps the same work id; the opening session skips instead of saving while the sub-session runs, then reads with `show` and saves what it adopts. Core unchanged.
위임 규칙(rules.md, `SAVE_HELP`): 서브에이전트나 별도 세션이 일을 하면 작업을 지정받은 세션이 같은 턴에 save하고, 위임 프롬프트에 Worklog 명령 금지를 넣고, summary 첫머리에 `[위임: …]`(결정·제약 글자에는 금지), 만든 파일은 artifacts+check, 제안은 `"source": "model"`. 별도 세션은 Hook이 도는 방식으로 열고 첫 프롬프트를 `"<작업 id> 이어서. 하위 작업: <이름>"`으로 시작한다. 같은 목표는 같은 작업 id. 하위 세션이 도는 동안 여는 세션은 skip, 끝나면 `show` 뒤 채택 여부 save. 코어 불변.

## 2.6.0 — 2026-10-12
`warning_core` now compares only the major and minor numbers: by the numbering rule a patch-only difference changes nothing the model can notice, so a 2.6.1 ledger no longer warns a 2.6.0 core. A unit test checks that every CHANGELOG heading is exactly one step above the previous one.
`warning_core`가 주·부 번호만 비교한다. 번호 규칙상 끝 번호만 다른 코어는 모델이 알아챌 변경이 없으므로, 2.6.1이 쓴 기록을 2.6.0이 읽어도 경고하지 않는다. CHANGELOG의 모든 제목이 바로 앞 제목보다 정확히 한 자리만 큰지 단위 테스트가 확인한다.

## 2.5.0 — 2026-10-12
Update notifications only: the `auto` mode is gone. `update.py background` (started detached once a day by SessionStart) now only fetches tags and writes the cache; nothing changes files on its own. The rules copy is no longer reinstalled at session start (a stale copy keeps the 2.2.0 warning line with the install command). Modes: `notify` (default for a git clone) | `off`. Applying is always by hand: `wl.py update` (fast-forward to the newest tag of the same major, refuses a dirty tree, reverts on version mismatch, reinstalls the current project), `update rollback`, `update check`. A clone that already runs 2.4.0 in auto mode applies 2.5.0 once by itself and is notify-only from then on.
알림만 남긴다: `auto` 모드 삭제. SessionStart가 하루 한 번 분리 실행하는 `update.py background`는 tag 가져오기와 캐시 기록만 하고, 어떤 파일도 스스로 바꾸지 않는다. 세션 시작 때 규칙 사본 재설치도 없앴다(오래된 사본은 2.2.0의 사본 경고 줄이 설치 명령과 함께 알린다). 모드: `notify`(git clone 기본) | `off`. 적용은 항상 수동: `wl.py update`(같은 주 번호의 최신 tag로 fast-forward, 커밋 안 된 변경이 있으면 거부, 버전 불일치면 복귀, 현재 프로젝트 재설치), `update rollback`, `update check`. 2.4.0을 auto로 쓰던 clone은 2.5.0을 한 번 스스로 적용한 뒤부터 알림만 받는다.

## 2.4.0 — 2026-10-12
Self-update for git clones: `tools/update.py` fetches tags from origin and fast-forwards to the newest tag of the current major version (a newer major is announced, never applied). Mode in `~/.worklog/config.json` (`"update": "auto"|"notify"|"off"`; a clone defaults to auto, a plain copy to off). The SessionStart hook never touches the network: once a day it starts `update.py background` detached, and it only reads the cache `~/.worklog/update.json` to add one line (update applied / available / failed / newer major). In auto mode a stale rules copy is reinstalled at SessionStart (local, backs up the old files). `wl.py update [check|rollback] [--mode M]` runs it by hand and reinstalls the current project. `WL_HOME` overrides the state folder (tests).
git clone 사용자용 자가 갱신: `tools/update.py`가 origin의 tag를 받아 현재 주 번호의 최신 tag로 fast-forward 한다(더 높은 주 번호는 알리기만 하고 적용하지 않는다). 방식은 `~/.worklog/config.json`의 `"update"`(auto·notify·off; clone 기본 auto, 복사본 기본 off). SessionStart Hook은 네트워크를 쓰지 않는다: 하루 한 번 `update.py background`를 분리 실행만 하고, 캐시 `~/.worklog/update.json`만 읽어 한 줄(적용됨·있음·실패·새 주 버전)을 붙인다. auto에서는 오래된 규칙 사본을 SessionStart에서 다시 설치한다(로컬, 백업 생성). `wl.py update [check|rollback] [--mode M]`은 수동 실행이며 현재 프로젝트를 재설치한다. `WL_HOME`으로 상태 폴더를 바꿀 수 있다(테스트용).

## 2.3.0 — 2026-10-12
Every new event records the core that wrote it (`"core": "2.3.0"`). When a ledger holds an event written by a newer core, show/use text, save results and verify results carry `warning_core` (never refuses; events without `core` never warn). Prepares older copies to notice a newer one before external users exist. No reinstall needed.
새 사건마다 쓴 코어 번호(`"core": "2.3.0"`)를 기록한다. 더 새 코어가 쓴 사건이 있으면 show·use 텍스트, save·verify 결과에 `warning_core`를 붙인다(거부 없음, `core` 없는 옛 사건은 경고 없음). 외부 사용자가 생기기 전에 옛 사본이 새 사본을 알아차리게 하는 준비. 재설치 불필요.

## 2.2.0 — 2026-10-12
Installer writes `.worklog/install.json` (per tool: version, sha256 of the `adapters/rules.md` it installed from); the core compares it with its own rules file and adds `warning_install` to save/skip/verify results, the `use` text and the SessionStart injection when they differ (never refuses; missing or broken manifest = no warning). Literal `[사용자]`/`[모델]` tags at either end of a decision or constraint text are dropped at save (the core adds the tag itself).
설치기가 `.worklog/install.json`(도구별 version·설치 원본 `adapters/rules.md`의 sha256)을 쓰고, 코어가 자기 규칙 파일과 대조해 다르면 save·skip·verify 결과, use 텍스트, SessionStart 주입에 `warning_install`을 붙인다(거부 없음, 파일 없음·깨짐은 경고 없음). 결정·제약 글자 앞뒤의 `[사용자]`/`[모델]`은 저장 때 지운다(태그는 코어가 붙인다).

## 2.1.0 — 2026-10-10
Per-decision `source: "model"` for model proposals saved in a user event; constraint sentences stay out of artifact bodies even paraphrased; turn-limited instructions are not constraints; `self_quoted` on checks that quote the rule text; `hooks_seen` self-diagnosis; `[사용자]`/`[모델]` source tags; Python 3.9 support.
결정별 `source: "model"`(사용자 사건 안의 모델 제안), 제약 문장 본문 전사 금지, 턴 한정 지시 제외, `self_quoted`, `hooks_seen`, 출처 태그, Python 3.9 지원.
