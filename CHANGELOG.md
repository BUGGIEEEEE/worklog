# Changelog

Tags are set by the author only; an external PR gets a tag only after the author merges and reviews it.
Numbering x.y.z — decided by *what changed*, never by what the user has to do afterwards:
- **x (major)**: the ledger structure changes (`FORMAT`, e.g. `worklog/2` → `worklog/3`). Ships with a migration script. `update` never crosses this line by itself.
- **y (minor)**: behaviour changes — core, installer or `update.py` code, a new command, field, warning or injection line, and any change to the model-facing rules (`adapters/rules.md`, `SAVE_HELP`), because rule wording changes what the model does.
- **z (patch)**: same behaviour, different text — typos, message wording, comments, tests, docs inside a code file. Rule wording is never a patch.
- Docs only (README, docs/, this file): no new number, no tag.
Every number has a `## x.y.z — date` entry here; `python3 -B core/wl.py version` prints the installed number and a unit test keeps it equal to the first heading.

tag는 작성자만 붙인다. 번호 x.y.z는 *무엇이 바뀌었나*로 정한다(사용자가 할 일로 정하지 않는다):
- **x(주)**: 원장 구조 변경(`FORMAT`, 예: `worklog/2` → `worklog/3`). 마이그레이션 스크립트 동반. `update`는 이 경계를 스스로 넘지 않는다.
- **y(부)**: 동작 변경 — 코어·설치기·`update.py` 코드, 새 명령·필드·경고·주입 줄, 그리고 모델이 읽는 규칙(`adapters/rules.md`, `SAVE_HELP`)의 문구 변경(문구가 모델 동작을 바꾸므로).
- **z(끝)**: 동작은 같고 글자만 — 오타, 메시지 문구, 주석, 테스트, 코드 파일 안의 설명. 규칙 문구는 z가 아니다.
- 문서만(README, docs/, 이 파일): 번호·tag 없음.
모든 번호는 여기에 `## x.y.z — 날짜` 항목을 가진다. `python3 -B core/wl.py version`으로 설치된 번호를 확인하고, 단위 테스트가 첫 제목과 같은지 지킨다.

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
