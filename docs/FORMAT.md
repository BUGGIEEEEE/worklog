# Worklog 기록 형식 2 (`worklog/2`)

> **English summary.** `worklog/2` is the on-disk format of a project's `.worklog/` folder. One project holds several **works** (separate tasks). `index.json` lists them; each work has its own folder `works/<id>/` with an append-only ledger `events.jsonl` and two projections, `state.json` and `state.md`. A work ID is an ASCII slug made from its title (`habit-plan`; `work`, `work-2`… when nothing ASCII remains). Event lines are unchanged from `worklog/1`: one JSON event per line, numbered `seq`/`id` from 1 per work, each line chained to the previous one by `prev` = sha256 of the previous line's bytes. A change to an earlier line that later events follow is detected on read; the last event has no independent reference point, so a change to it is not detected. This is not a defense against deliberate tampering. Each session has a *current work*, set by `use <id> --quote …` or `new-work "<title>" --quote …`: the user names it, or (2.25.0, `auto` on) the model creates a new work from the first request in a folder with no works; an existing work is never picked for the user. Without one, `save` is refused and the model asks the user. The SessionStart injection lists the works and, if the session has a current work, its full state — also after compaction. The goal is set once; later changes are decisions that `replace` older ones (`D1..`), and constraints (`C1..`) persist until the user removes them. A save that lists artifacts must include a `check` entry for every active decision and constraint: a verbatim quote (4+ characters) from the artifact body, or `미반영: <reason>` ("not reflected"). Saves are serialized with `flock` and rejected if the session has not read the latest record of that work. A `worklog/1` folder is migrated with `tools/migrate_v1_to_v2.py`; the ledger bytes move unchanged into `works/<id>/`. Changing the format means re-migrating existing ledgers. Since 2026-10-09: decisions and constraints carry a `source` (`user` for REQUEST/APPROVAL/D_USER events, `model` otherwise); a model constraint can be removed with a reason alone, a user constraint only with the user's words. A `check` quote that merely repeats the rule's own text is accepted but reported as `self_quoted` (it is not evidence); non-text artifacts (images, archives) are hashed but not searched for quotes. Each hook records its run in the session file (`hooks_seen`), and save/skip/verify report whether the hooks are active. The SessionStart list also names the most recent COMPLETED works, and `state.md` summarizes artifacts by folder once there are more than 15. Since 2.25.0: an explicit `--root` is used as given by commands and hooks alike; without it, commands and hooks use a *candidate root* (cwd if connected; inside git the nearest folder with `.worklog/index.json` up to the git top level, else the git top level; outside git, cwd), the NOT_CONNECTED line carries `root=`, `auto=` and `git=`, and with `"auto": "on"` (the default of `~/.worklog/config.json`) the model connects a folder on its first request worth recording, except the home folder: `~/.worklog` (WL_HOME) counts as connected only when it holds `index.json`, and is never connected automatically. A work is still never picked for the user. `reassign` refiles misfiled events as a pair of linked CORRECTION events (the format number stays: `changes` gains `decisions_remove`, written only by `reassign`) and refuses events already refiled to another work, `rename` changes a title only. Since 2.26.0 `reassign` writes the right work first, points the wrong work's mark at the id really written, keeps a user source over the same model text, and a re-run does only the missing steps; save takes `artifacts_moved`. Since 2.27.0 save takes `artifacts_gone` (user-confirmed deletions, shown by `verify` as `gone`), a missing artifact is reported once per session and work (`missing_noted`), `reassign --new "<title>"` creates the right work first, and a call without `--tool` is refused when two tool session variables are set (show·works·verify without `--work`·off included, except show in an unconnected folder and off in a folder already off, which do not read the session; off in an unconnected folder fails with the not-connected error first; `on` only removes the off marker and is not refused for two session variables, though an unconnected folder still gets the not-connected error).

확정일 2026-10-06. 구현: `core/wl.py`. 이 문서와 구현이 다르면 구현을 고치지 말고 먼저 보고한다.

> **형식 변경 = 재이전.** 필드 이름·사건 종류·ID 규칙·해시 연결·저장 구조를 바꾸면 기존 기록을 새 형식으로 다시 이전한다. 이전 도구와 검증도 함께 고친다. 기존 원장의 해석이 그대로인 선택 필드 추가만 같은 형식 번호를 유지한다.

> **원장 해석 정책(2.26.0 명시).** `changes.decisions_remove`와 제약 객체 `{text, source}`는 2.25.0에 추가된 **선택 필드**이며 기존 원장의 해석은 그대로다(형식 번호 `worklog/2` 유지). 2.26.0의 `changes.artifacts_moved`도 같은 성격의 선택 필드다. `reassign`을 쓴 원장은 2.25.0 이상 코어로만 읽는다. 옛 코어는 `warning_core` 경고만 내고 투영을 잘못 만들 수 있다. git으로 `.worklog/`를 공유하는 프로젝트는 모든 기기의 코어를 같은 날 갱신한다. 되돌리기(rollback)는 2.25.0 이상으로만 한다(`artifacts_moved`를 쓴 원장은 2.26.0 이상). 2.27.0의 `changes.artifacts_gone`도 같은 성격의 선택 필드다. 그것을 쓴 원장은 2.27.0 이상 코어로 읽는다(옛 코어는 `warning_core`를 내고 지운 산출물을 목록에 남긴 투영을 만들며 그 파일을 누락으로 보고한다). 되돌리기도 2.27.0 이상으로 한다.

## 저장 구조 (`<프로젝트>/.worklog/`)

```text
.worklog/
  index.json
  project.md                         # 선택, 사용자 확정 뒤 기록(아래 '프로젝트 공통' 절)
  works/<id>/
    events.jsonl
    state.json
    state.md
  sessions/<tool>_<session>.json
  .lock
  off                                # 있으면 Worklog 꺼짐
```

| 파일 | 역할 | 쓰는 주체 |
|---|---|---|
| `index.json` | `{"format":"worklog/2","works":{"<id>":{"title":…, "status":…, "created_at":…, "updated_at":…, "last_seq":…}}}` | 코어, `.lock` flock 안에서만 갱신 |
| `project.md` | 작업을 넘어 이 프로젝트에 적용되는 안내·결정·제약, 원장 아님 | 사용자, 또는 사용자가 "넣어"라고 확정한 뒤의 모델·확장 모듈. 코어는 읽어 주입만 하고 만들지도 쓰지도 않음 |
| `works/<id>/events.jsonl` | 해당 작업의 추가 전용 원장, 한 줄 = 사건 | 코어 save·archive·reopen |
| `works/<id>/state.json` | 해당 원장에서 재계산하는 기계용 현황 | 코어 |
| `works/<id>/state.md` | 같은 현황의 사람·주입용 본문 | 코어 |
| `works/<id>/writer.json` | 마지막 작성자 정보 `{tool, session_id, seq}`, 원장·선택·독점권의 근거 아님 | 코어 |
| `sessions/<tool>_<session>.json` | `{current_work, last_seen: {"<id>": seq}, hooks_seen: {"SessionStart"\|"UserPromptSubmit"\|"Stop": 시각}, turn, saved_turn, skipped_turn, selected_turn, blocked_turn, in_turn, agy_pre, agy_stop, hook_keys, new_work_turn, new_work_id, new_work_from, reassigned, missing_noted}`. `hook_keys`(2.25.0)는 claude·codex Hook의 마지막 키 `{"SessionStart": "<source>@<시각>", "UserPromptSubmit": "<turn_id 또는 prompt_id>", "Stop": "<턴>/<stop_hook_active 0·1>@<시각>"}`로, 두 번 등록된 Hook의 두 번째 호출을 무동작으로 만든다(아래 'Hook 중복'). `new_work_turn`(2.25.0)은 이 세션이 마지막으로 new-work(2.27.0부터 `reassign --new` 포함)를 실행한 턴, `new_work_id`(2.26.0)는 그때 만들던 작업 id다. `new_work_from`(2.27.0)은 `reassign --new`가 함께 쓰는 `"<잘못된 id>:<사건 id,…>"`이다(new-work는 null). 셋은 index.json보다 먼저 쓰는 재시도 표식이다(아래 '작업 선택 규칙'과 '새 작업으로 옮기기'. 값이 이상하면 없는 것으로 읽고 세션 파일 손상으로 보지 않는다. 옛 코어는 `new_work_from`을 세션 파일을 다시 쓸 때 빼므로 그 뒤의 재실행은 슬러그 충돌로 거부된다). `reassigned`(2.26.0)는 이 세션이 끝낸 reassign의 세션 단계 표식 `"<맞는 id>:<refiled 사건 id>@<그때 turn>"` 목록(최근 20개)이다(아래 '단계와 복구'. 값이 이상하면 빈 목록으로 읽는다). `missing_noted`(2.27.0)는 이 세션에 이미 보인 산출물 누락 `"<작업 id>:path(Eid)"` 목록이다. show·use·주입의 `[Worklog 산출물 없음]`과 save·skip의 `artifacts_missing`은 여기 없는 것만 보이고 보인 뒤 더한다(같은 세션에는 한 번. 작업 id가 있어 다른 작업의 같은 `path(Eid)`는 따로 센다. 파일이 돌아왔다가 다시 없어져도 다시 보이지 않는다. 값이 이상하면 빈 목록으로 읽는다. 작업 id 없는 항목은 아무것과도 맞지 않아 그 누락이 한 번 더 보인다. 이 키를 모르는 옛 코어는 읽을 때 무시하고 세션 파일을 다시 쓸 때 뺀다). `hook_keys.SessionStartTurn`(2.26.0)은 마지막 SessionStart 때의 `<turn>|<UserPromptSubmit 시각>|<Stop 시각>`이다. `agy_pre`·`agy_stop`(2.24.2)은 agy가 마지막으로 보낸 PreInvocation(`invocationNum/initialNumSteps`)·Stop(`executionNum`)으로, 같은 이벤트가 두 번 등록된 훅으로 다시 오면 무동작이다. `in_turn`(2.24.1)은 이 턴의 모델 호출이 시작됐다는 표시로, agy는 Stop 뒤 첫 PreInvocation만 턴으로 세고(도구 호출마다 오는 나머지는 무시) Stop이 내린다. `blocked_turn`(2.24.0)은 Stop이 한 번 막은 턴으로, 같은 턴의 두 번째 Stop은 도구가 `stop_hook_active`를 보내지 않아도 통과한다. show·use·주입은 `last_seen` 이후의 사건을 "못 본 사건"으로 보여 준 뒤 이 값을 갱신한다(2.23.0) | 코어, 원장·해시 연결 대상 아님 |
| `.lock` | 프로젝트 내 동시 변경을 flock으로 직렬화 | 코어 |
| `off` | `{at, reason, by, quote}` JSON(reason·by는 없으면 null). 있으면 이 프로젝트 전체의 Worklog가 꺼짐, 원장 아님 | 코어 off·on, `.lock` 안에서 생성·삭제 |

작업 ID는 제목에서 만든 ASCII 슬러그(소문자·숫자·`-`, 40자 이내)다. 비ASCII만 남거나 숫자만 남으면("던전디펜스 1화" → `1`은 쓰지 않음) `work`이며 중복은 `-2`, `-3`으로 구분한다. 제목 앞의 `새 작업:`은 제거한다. 한글 원제목은 index의 title에 보관한다. 사건 ID와 결정·제약 ID는 작업별이다.

연결 신호는 `.worklog/` 디렉터리 존재다. 설치 직후에는 비어 있다. 단 `WL_HOME`(기본 `~/.worklog`, 설정·등록·매니페스트를 두는 곳)은 `index.json`이 있을 때만 연결로 본다(2.25.0: 홈 폴더 자체가 프로젝트인 경우만). 모든 명령과 세 Hook이 같은 판정을 쓰므로, index가 없는 `WL_HOME`에서는 Hook이 세션 파일·`.lock`을 만들지 않는다. 기록 위치가 홈 폴더(저장소가 `WL_HOME`)이면 `auto`가 `on`이어도 자동 연결하지 않는다. NOT_CONNECTED 줄의 `auto=` 필드는 설정값 그대로이고, 본문은 `auto=off` 안내에 "홈 폴더는 자동 연결하지 않는다."를 붙인다. 사용자가 홈에서 명시적으로 `new-work`를 실행하면 홈이 프로젝트가 되지만, 이때도 `WL_HOME/install.json`(사용자 수준 매니페스트)에 연결 항목을 쓰지 않는다.

**루트 후보(2.25.0).** `--root`가 없으면 명령은 프로세스 cwd에서, Hook은 이벤트의 cwd에서 기록 위치를 정한다. ① cwd가 연결돼 있으면 cwd. ② cwd가 git 작업 트리 안이면(위로 올라가며 `.git` 디렉터리나 파일이 있는 가장 가까운 폴더 = git 최상위) cwd에서 git 최상위까지 올라가며 `.worklog/index.json`이 있는 가장 가까운 폴더(`WL_HOME`은 고르지 않는다), 없으면 git 최상위. 하위 폴더에 새 기록을 만들지 않는다. 중첩 프로젝트는 가장 가까운 기록이 이기고, worktree는 `.git` 파일이 있는 폴더가 최상위다(worktree 경고 유지). ③ git이 아니면 cwd(상위 탐색 없음. `~`나 임시 폴더 위의 기록에 합류하지 않는다). git 최상위 위에 다른 기록이 있으면 합류하지 않고 NOT_CONNECTED 줄에 한 구절로 알린다(합류하려면 사용자가 `--root`로 정한다). `--root`가 있으면 명령과 Hook 모두 그 폴더를 그대로 쓴다(Hook도 이벤트 cwd보다 우선한다. 설치기가 만드는 Hook 명령에는 `--root`가 없다).

**갱신 캐시 `WL_HOME/update.json`과 모듈 등록 `WL_HOME/modules.json`(2.28.0).** `tools/update.py`가 쓰는 캐시는 `{checked_at, mode, current, latest, latest_major, error, applied, previous}`이고, 확장 모듈이 등록돼 있으면 `modules: {"<이름>": {current, latest, error}}`가 더해진다. `modules.json`은 모듈 설치기가 쓰고 코어는 읽기만 한다: `{"<모듈 이름>": {"version": "<semver>", "source": "https://github.com/BUGGIEEEEE/<모듈 이름>", "installed_at": "<ISO>"}}`. 아는 이름은 `worklog-mods`·`worklog-jev`·`worklog-global`·`worklog-scan`이고, 파일이 없거나 깨졌거나 항목이 맞지 않으면 무시한다. `update.py check`·`background`(하루 1회)는 모듈마다 `git ls-remote --tags <source>`(https 주소만)로 최신 semver 태그를 찾는다. 조회 실패는 그 모듈의 `error`에 적고 다른 모듈을 계속한다. SessionStart는 캐시의 `latest`가 지금 `modules.json`의 `version`보다 높은 모듈마다 코어 안내 뒤에 한 줄을 더한다. `update`(apply)는 모듈을 바꾸지 않는다.

**사용자 설정 `WL_HOME/config.json`.** `{"update": "notify"|"off", "auto": "on"|"off"}`. `auto`(2.25.0)는 연결되지 않은 폴더의 동작이다: `on`(키가 없을 때도)이면 모델이 첫 기록 대상 요청에서 `new-work … --root <후보>`로 연결하고, `off`면 2.24 동작(사용자가 `새 작업:`이라 할 때만). 프로젝트의 `.worklog/off`가 항상 우선한다. 설치기 `--user`는 `auto` 키가 없을 때만 `"auto": "on"`을 더하고 다른 키는 유지한다. `new-work`는 index 항목과 빈 작업 폴더를 만들고 원장은 첫 save로 만든다. 현황 두 파일을 직접 고치지 않는다. 불일치하면 원장이 기준이며 `show`로 복구한다. 형식 1의 루트 원장과 `writer.json`을 형식 2 저장 계약으로 사용하지 않는다.

## 사건 (events.jsonl 한 줄)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `v` | ✓ | 사건 형식 1(`v: 1` 유지). 상태·저장 구조는 worklog/2 |
| `seq`, `id` | ✓ | 작업마다 1부터 연속. `id = E%04d` |
| `prev` | ✓ | 직전 줄 바이트의 sha256(첫 줄 null). 끊기면 읽기 거부. 뒤에 사건이 이어진 과거 줄의 변경은 읽기 때 감지된다. 마지막 사건은 독립적 기준점이 없어 감지 대상이 아니다. 악의적 변조 방지 장치가 아니다 |
| `type` | ✓ | 아래 15종 |
| `at` | ✓ | 기록 시각(UTC) |
| `occurred_at` | | 실제 발생 시각이 기록 시각과 다를 때(이전 사건 등). 상태 계산 순서에는 쓰지 않는다(2.28.0의 순서는 아래 `refs`의 `occurred_at` 항목만 읽는다) |
| `tool`, `session_id` | ✓ | 기록한 도구(`codex`/`claude`/`pi`)와 그 세션 ID |
| `summary` | ✓ | 한두 문장 |
| `quote` | 조건부 | 사용자 원문 일부. REQUEST·APPROVAL·D_USER, 목표 설정, 제약 해제, 작성권 인수에 필수 |
| `changes` | ✓ | 상태 변경: `goal`·`decisions`·`constraints`·`constraints_remove`·`waiting`·`next_action`·`status`·`artifacts`, 그리고 `reassign`만 쓰는 `decisions_remove`(`{"D2": "사유"}`, 2.25.0). `reassign`이 쓰는 `constraints` 항목은 문자열 대신 `{"text", "source"}`일 수 있다(다른 작업에서 가진 출처를 유지). save 입력은 그대로 문자열만 받는다. `artifacts_moved`(2.26.0): `{"<옛 경로>": {"path": "<새 경로>", "sha256": "<새 파일 해시>"}}`, fold가 이동 전 산출물 목록에 매핑 전체를 한 번에 적용해(키 순서 무관) 옛 경로 항목을 제자리에서 새 경로로 바꾸고 event를 이 사건으로 바꾼다. 옛 경로가 목록에 없거나, 새 경로가 겹치거나, 새 경로가 옮기지 않는 기존 산출물이거나, 이동이 순환하면(맞바꾸기 포함) 거부한다. `artifacts_gone`(2.27.0): `[{"path": "<기록된 경로>", "reason": "<한 구절>"}]`, fold가 `artifacts_moved` 다음에 그 경로들을 산출물 목록에서 뺀다(목록에 없는 경로면 거부) |
| `refs` | | 문자열 값만 가진 객체 목록. save로 받은 것은 그대로 저장하고 해석하지 않는다. 예외(2.28.0): `save --ts <YYYY-MM-DDTHH:MM:SSZ>`가 더하는 `{"occurred_at": "<UTC>"}`는 상태 계산 순서가 읽는다(아래 '현재 상태'). save JSON의 refs에 `occurred_at` 키를 직접 넣으면 거부한다. `reassign`(2.25.0)이 쓰는 것: 잘못된 작업 쪽 `{"kind": "misfiled", "id": "E0003"}`·`{"kind": "refiled_to", "work": "<맞는 id>", "id": "E…"}`, 맞는 작업 쪽 `{"kind": "refiled_from", "work": "<잘못된 id>", "id": "E0003", "quote": "<원래 quote>"}`. 2.26.0 이상의 정상 실행에서 맞는 작업 쪽은 `refiled_from`만 쓴다. `{"kind": "correction", "work": "<잘못된 id>", "id": "E…"}`는 2.25.0이 쓴 쌍과, 2.25.0이 잘못된 작업만 쓰고 멈춘 실행을 2.26.0이 이어 쓸 때만 붙는다. 대상 정정 사건(2.26.0, 아래 '단계와 복구')은 `{"kind": "corrects", "id": "<misfiled 사건 id>"}`·`refiled_to`를 쓴다 |
| `source` | | 이전된 사건의 출처: `path`·`line`·`sha256`·원래 종류 |
| `core` | | 사건을 쓴 코어 번호(2.3.0부터). 주·부 번호가 더 큰 코어가 쓴 사건이 있으면 show·save·verify에 `warning_core`가 붙는다(끝 번호만 다르면 경고 없음, 거부 없음). 없으면 옛 사건으로 보고 경고하지 않는다 |
| `check` | 텍스트 산출물 시 | 유효 결정·제약마다 산출물 **본문**의 인용(공백 정규화 후 실제로 있어야 함) 또는 `미반영: <이유>`. 미반영 ID는 저장 결과의 `unreflected`에 표시. 산출물이 모두 비텍스트(UTF-8이 아니거나 NUL 포함)면 check는 선택이고 미반영만 받는다 |
| `self_quoted` | | 인용이 규칙 문장과 같았던 ID 목록. 저장은 되지만 반영의 증거가 아니다. 저장 결과에도 같은 이름으로 표시 |
| `writer_acquired` | | 작성권 인수 기록 |

**사건 종류 15종:** REQUEST, APPROVAL, D_USER, D_AGENT, ASSUMPTION, RESULT, VERIFICATION, BLOCKER, CORRECTION, CHECKPOINT, HANDOFF, CHANGE, Q, WRITER_ACQUIRED, WRITER_RELEASED.
- 사용자 출처(원문 필수): REQUEST, APPROVAL, D_USER.
- 제약 해제 가능: D_USER, APPROVAL, CORRECTION.
- 이 목록에 없는 기존 종류는 이전할 때 15종 중 하나로 대응하고, 원래 이름은 `source`에 남긴다.
- **이전 사건:** `tool: "import"`, `session_id`는 이전 실행 ID, `quote`는 null이며 대신 `source`(원본 경로·줄·줄 sha256·원래 종류·원래 ID·원래 기록 시각, 있으면 원래 세션·권위)가 근거다. 원본에 없는 값은 비워 두고 추정하지 않는다. 이전 사건은 상태를 바꾸지 않고, 사용자 확인을 거친 현재 상태 사건 1건만 상태를 정한다. 외부 기록을 가져오는 이전 도구는 이 배포본에 포함하지 않는다(형식 1 → 2 이전 도구만 포함).
- 작업 경계를 나타내는 별도 사건 종류는 없다. 작업마다 독립 원장과 사건 ID·해시 연결을 유지한다.
- **잘못 기록한 사건의 정정(2.25.0, `reassign`. 순서·복구는 2.26.0).** 사건은 옮기지 않는다. 한 `.lock` 안에서 다음 순서로 쓴다. ⒜ **맞는 작업 먼저**: CORRECTION(`[refiled ← <잘못된 id>] E0003-E0005`, quote = 사용자 원문)을 더해 그 사건들이 넣고 아직 유효한 결정·제약을 새 `D`·`C` 번호로 넣고, 그 사건들의 산출물은 지금 파일로 해시를 다시 계산해 넣는다. refs는 잘못된 작업의 기존 사건만 가리킨다(`refiled_from`, 원래 quote 포함). 같은 글자가 맞는 작업에 이미 있으면 출처로 판정한다: 같은 출처면 건너뛰고(`already_there`), 들어오는 것이 `user`이고 있는 것이 `model`이면 있는 항목을 `decisions_remove`·`constraints_remove`로 빼고 `user`로 다시 넣으며(`upgraded`), 들어오는 것이 `model`이고 있는 것이 `user`면 건너뛴다. 옮기는 사건들 안에 같은 글자가 둘 이상 있으면(예: 모델 결정을 사용자가 같은 글자로 대체) 먼저 글자별로 하나로 합치고 출처는 순서와 상관없이 `user`가 이긴다. 맞는 작업의 기존 항목은 `decisions_remove`·`constraints_remove`로 빼고, 이번에 넣는 항목끼리는 넣기 전에 합친다. ⒝ 잘못된 작업에 CORRECTION(`[misfiled → <맞는 id>] E0003-E0005`)을 더해 같은 결정·제약을 `decisions_remove`·`constraints_remove`로 뺀다. `refiled_to`의 id는 ⒜가 실제로 기록된 id다(미리 계산하지 않는다). ⒞ 세션의 현재 작업을 맞는 작업으로 바꾸고 ⒜를 읽은 것으로 치며, 세션의 `reassigned`에 표식을 남긴다. 목표·대기·다음 행동·산출물 목록은 잘못된 작업에서 빼지 않는다.
  - **단계와 복구.** 단계는 `refiled`(⒜ 사건) → `refiled_state`(맞는 작업의 state.json·state.md·index 항목이 원장과 일치) → `misfiled`(⒝ 사건) → `misfiled_state` → `session`이다. `session`은 이 세션의 `current_work`가 맞는 작업이고 ⒜를 읽은 경우에 끝난 것이다. `show --work <맞는 id>`로 읽기만 한 것은 끝난 것이 아니다. 이 세션이 세션 단계를 끝낸 표식(`reassigned`)이 있고 그 뒤 턴에(`selected_turn` ≥ 표식의 turn) 사용자가 다른 작업을 고른 경우도 끝난 것으로 보고, 재실행은 "이미 옮겼습니다"로 거부하며 `current_work`를 되돌리지 않는다. 표식이 없으면(세션 갱신 실패) 재실행이 `current_work`를 맞는 작업으로 바꾼다. 두 쓰기와 세션 갱신 어디서 실패해도 결과는 `{"ok": false, "partial": true, "done": [끝난 단계], "refiled", "misfiled", "error", "next", "message"}`·exit 2다. 같은 명령을 다시 실행하면 먼저 끝난 단계를 디스크에서 찾는다: 맞는 작업에서 `refiled_from` refs가 고른 사건 집합과 같은 CORRECTION, 잘못된 작업에서 `misfiled` refs가 같고 `refiled_to`가 맞는 작업인 CORRECTION, 두 작업의 투영·index, 세션의 `last_seen`. 빠진 단계만 하고(투영·index는 원장에서 다시 만든다) 결과에 앞서 끝나 있던 단계를 `resumed`로 보인다. 대상 작업을 먼저 쓰므로 원래 작업 쓰기 전에 실패하면 재시도까지 두 작업에 같은 결정·제약이 보인다. 결과의 partial과 done으로 알 수 있고 같은 명령 재실행으로 닫힌다. 모두 끝났으면 "이미 옮겼습니다"로 거부한다. 되돌리기는 없다(원장은 추가 전용). 2.25.0이 쓴 쌍(잘못된 작업 먼저, 맞는 작업의 `correction` ref)도 같은 refs로 찾는다. 2.25.0이 잘못된 작업만 쓰고 멈췄으면 그 `refiled_to`의 id는 미리 계산한 번호라서, 2.26.0이 맞는 작업을 쓴 실제 id와 다를 수 있다. 그때는 잘못된 작업에 CORRECTION `[misfiled → <맞는 id>] 대상 정정 <misfiled id>`를 하나 더 남긴다(refs `corrects`·올바른 `refiled_to`, 상태 변경 없음, 기존 원장 줄은 그대로). 결과에 `"corrected_ref": true`와 `ref_correction`(그 사건 id)이 붙고, 이후 단계 판정은 가장 최근 대상 정정 사건의 `refiled_to`를 쓴다. 이중 이관 검사에서 다른 작업의 원장을 읽을 수 없으면 건너뛰지 않고 그 작업 id와 원인을 들어 거부한다(아무것도 쓰지 않는다).
  - **새 작업으로 옮기기(2.27.0, `reassign <잘못된 id> --new "<제목>" --events … --quote`).** 맞는 작업이 아직 없을 때 `<맞는 id>` 대신 쓴다(둘을 함께 주면 거부). 같은 `.lock` 안에서 사건 범위와 이중 이관을 먼저 검사한 뒤 `new-work`와 같은 규칙으로 작업을 만들고(제목 앞 `새 작업:` 제거, id 슬러그, 한글만·숫자만이면 `work`·`work-2`, 세션의 `new_work_turn`·`new_work_id`·`new_work_from` 표식을 index보다 먼저 씀, 같은 턴의 두 번째 새 작업은 `--force` 없이 거부. new-work와 reassign --new가 같은 표식을 쓴다), 그 작업을 맞는 작업으로 위 ⒜⒝⒞를 그대로 한다. 새 작업에는 사건을 따로 쓰지 않고 ⒜의 `changes.goal`이 제목이다(첫 save가 제목을 목표로 쓰는 것과 같다). 슬러그가 잘못된 작업 id와 같으면 `--new 제목으로 만들 작업 id가 잘못된 작업의 id(<id>)와 같습니다. 다른 제목을 쓰세요.`로 거부한다. 슬러그가 그 밖의 이미 있는 작업 id면(한글만·숫자만 제목의 `work`는 제외) 거부하고 `reassign <잘못된 id> <그 id>`를 안내한다. 결과에 `created`(이번 실행이 만든 id)와, 다른 작업에 유효 제약이 있으면 new-work와 같은 `notice`가 붙는다. 작업을 만드는 중이나 만든 뒤 실패해도 partial 결과(`done`, 작업이 index에 있으면 `created`)로 알린다. index에 쓰기 전에 멈췄으면 `done`은 `[]`이고 `created`가 없다. 같은 세션이 같은 명령을 다시 실행하면 이 세션의 표식(`new_work_id`가 그 작업, `new_work_from`이 같은 잘못된 작업·같은 사건)이 가리키고 제목이 같으며 원장이 비었거나 이 세션이 쓴 이 이관의 refiled CORRECTION만 있는 작업으로 이어 간다(`<id>-2`를 만들지 않는다). 표식으로 확인할 수 없는 작업(다른 세션이 만든 빈 작업 포함)은 이어 가지 않고 슬러그 충돌로 거부하며, 같은 턴 거부도 그대로 적용한다.
  - **이중 이관 거부.** 고른 사건 중 하나라도 이미 다른 작업으로 옮겼으면 "이미 <id>로 옮긴 사건입니다"로 거부하고 아무것도 쓰지 않는다. 판정은 모든 작업의 원장에서 `refiled_from {work: <잘못된 id>, id}`를 찾고(⒝ 전에 멈춘 실행도 막는다), 잘못된 작업의 CORRECTION에 그 사건의 `misfiled`와 다른 작업의 `refiled_to`가 있는지도 본다.
- **제목 변경(2.25.0, `rename`).** index의 `title`만 바꾸고(id 그대로) 그 작업에 CHANGE 사건 한 줄(`제목 변경: <옛> → <새>`, quote 필수, changes 없음)을 더한다. 앞의 원장 줄은 그대로이며 `state.md` 제목 줄이 새 제목으로 다시 만들어진다.

## 현재 상태 (state.json / state.md)

`format: "worklog/2"`, `seq`, `goal`(최초 목표, 한 번만. 첫 save에 없으면 작업 제목), `status`(ACTIVE/PAUSED/BLOCKED/COMPLETED/CANCELLED), `decisions`[유효만: id·text·event·source·replaces], `constraints`[유효만: id·text·event·source], `waiting`, `next_action`, `artifacts`[path·sha256·event], `superseded`, `removed_constraints`, `updated_at`, `updated_by`{tool, session_id}.

- **우선순위:** 최초 목표의 값이 바뀌면 유효 결정이 우선한다. `replaces`로 기록된 변경은 충돌이 아니다. `state.md`는 goal 아래에 최신 결정을 "현재 범위"로 보여 준다.
- **출처(`source`):** 결정·제약을 넣은 사건이 REQUEST·APPROVAL·D_USER면 `user`, 그 밖이면 `model`. `state.md`에 `[사용자]`/`[모델]`로 표시한다. 제약 추가는 어떤 사건 종류든 할 수 있다.
- **제약**은 같은 문장의 재입력이 저장할 때 무시된다. 해제는 출처별이다: `user` 제약은 사용자 출처 종류(D_USER·APPROVAL·CORRECTION)와 quote가 필요하고, `model` 제약은 어떤 종류든 사유만으로 해제할 수 있다. "다음 요청까지 보류"처럼 요청이 오면 끝나는 것과 확인되지 않은 가정(`확인 필요: …`)은 `waiting`에 둔다. 작업량·목표 범위는 제약이 아니라 결정이다.
- ID: 결정 `D1..`, 제약 `C1..`. 원장 순서로 다시 계산해도 같은 값이 나온다.
- **적용 순서(2.28.0).** 상태는 사건이 일어난 순서로 계산한다. 정렬 키는 `(refs의 occurred_at 또는 지금까지의 가장 늦은 at, seq)`이다. `occurred_at`이 없는 사건은 앞서 추가된 사건보다 앞으로 가지 않으므로, 시계가 되돌아갔거나 `at`을 손으로 고친 원장도 추가 순서를 지킨다. `occurred_at`이 있는 사건만 그 시각 자리로 끼어든다. `at`이 UTC 형식이 아닌 사건은 앞 사건 자리에 남는다. 사건 id·`seq`·`prev` 사슬·`verify`의 사슬 검사는 추가 순서 그대로다. `D`·`C` 번호도 추가 순서로 매기므로 가져온 사건이 앞에 끼어들어도 다른 번호와 `replaces` 대상이 바뀌지 않는다. `seq`·`updated_at`·`updated_by`는 마지막으로 추가된 사건의 값이다. `occurred_at`이 없는 원장은 추가 순서 그대로 계산되므로 상태가 2.27.0과 바이트 단위로 같다. `save --ts`로 넣은 사건이 그 시각 자리에서 `replaces`·제약 해제를 맞지 않게 만들면 추가 전에 거부한다. 못 본 사건 목록(show·use·SessionStart)도 같은 순서이고 가져온 사건에는 `(가져옴 <occurred_at>)` 표식이 붙는다.
- `state.md`의 산출물은 15개까지 경로·해시를 나열하고, 그보다 많으면 폴더별 개수와 최근 사건만 보여 준다. 전체 목록은 `state.json`에 있다.
- `state.md` 제목에는 작업 id·제목이 들어간다. 각 작업의 상태를 독립적으로 계산한다. `project.md`는 원장이나 투영이 아니다.
- `state.md`의 `## 안내 — 먼저 볼 것(Map: 결정)` 절(2.23.0): 텍스트가 `Map:`으로 시작하는 유효 결정(앞 공백 무시, 제약은 제외)을 `## 유효 결정` 앞에 따로 보인다. 그 결정은 목록에도 그대로 남고, `현재 범위(최신 결정)` 줄은 Map이 아닌 마지막 결정으로 계산한다(Map만 있으면 줄 생략). Map 결정이 없으면 절도 없다. `state.json`은 바뀌지 않는다.

## 저장과 보호

save 순서: 잠금 → 선택 작업 원장 읽기·해시 연결 확인 → 작업별 신선도 확인 → 입력 검사(check 인용 대조 포함) → 사건 추가(fsync) → 다시 읽어 비교 → 현황 재계산 → 투영 원자적 교체 → 대조 → index·세션 갱신.

세션 독점은 없다. 세션이 마지막으로 본(use·show·hook·save) `last_seen[id]`보다 원장이 앞서면 "기록이 바뀌었습니다"로 거부한다. `show` 후 다시 저장한다. 이미 사건이 있는 작업을 읽지 않은 세션도 먼저 읽어야 한다. `use`는 선택 작업의 현재 상태를 출력하고 last_seen을 갱신하므로 별도 show 없이 바로 저장할 수 있다. `new-work`는 작업 id를 JSON으로 반환한다. 작성권 인수는 사용자 명시 승인일 때만 `takeover`와 quote로 기록한다. 사건 추가 뒤 투영 쓰기가 실패하면 원장이 기준이고 show로 복구한다.

텍스트 산출물이 있는 save는 유효 결정·제약마다 check를 넣는다. 규칙이 지켜졌음을 보여 주는 본문 구절을 4자 이상 따옴표로 인용하거나 `미반영: <이유>`를 적는다. 공백 정규화 후 본문에 없는 인용은 거부한다. 미반영은 저장 결과의 `unreflected`에 표시하며, 작업 방식 제약이나 그림·압축 파일처럼 인용할 수 없는 것은 미반영이 정상이다. 인용이 규칙 문장과 같으면 저장은 되지만 `self_quoted`에 표시한다. 규칙 문장을 본문에 써 넣어 통과시키는 것은 반영의 증거가 아니다. 산출물이 모두 비텍스트면 인용 대조 없이 해시만 남기고, check는 선택이며 미반영만 받는다.

산출물 파일을 옮겼으면 save 입력에 `artifacts_moved: {"<옛 경로>": "<새 경로>"}`를 넣는다(2.26.0). 옛 경로는 이 작업의 산출물 목록에 있어야 하고 새 경로 파일이 있어야 하며, 아니면 거부한다. 여러 항목은 이동 전 목록에 한 번에 적용하므로 키 순서와 상관없다(`{"a.md": "b.md", "b.md": "c.md"}`는 a의 항목이 b.md, b의 항목이 c.md가 된다). 새 경로가 겹치거나, 옮기지 않는 기존 산출물과 같거나, 이동이 순환하면(맞바꾸기 포함) 기록 전에 거부한다. 맞바꾸기는 두 save로 나눈다. 새 파일의 해시를 사건 `changes.artifacts_moved`에 남기고 목록의 그 항목을 새 경로로 바꾸므로, 옛 경로의 `artifacts_missing`·`[Worklog 산출물 없음]` 보고가 사라진다. 이동은 새 산출물이 아니므로 check를 요구하지 않는다.

산출물 파일을 영구히 지웠다고 사용자가 확인했으면 save 입력에 `artifacts_gone: [{"path": "<기록된 경로>", "reason": "<한 구절>"}]`를 넣는다(2.27.0). path는 이 작업의 산출물 목록에 있어야 하고 reason은 비어 있지 않아야 한다. 같은 파일이 두 번 있거나 같은 save의 `artifacts`·`artifacts_moved`(옛·새 경로)에도 있으면 거부한다. 경로는 프로젝트 기준 실제 경로로 대조하므로 `b.md`·`./b.md`·절대경로는 같은 파일이다. 사건에는 목록에 기록된 표기 그대로 남는다(`./b.md`로 지워도 기록이 `b.md`면 `b.md`). 파일이 아직 디스크에 있어도 거부하지 않는다(사용자 확인이 근거다). 사건 `changes.artifacts_gone`에 남고 목록에서 빠지므로 `artifacts_missing`·`[Worklog 산출물 없음]`과 `verify`의 `missing`에서 빠지고, `verify`의 `artifacts.gone`에 `"path(Eid)"`(Eid는 삭제를 기록한 사건)로 따로 보인다. 그 뒤 같은 파일을 다시 기록하면(`./`·절대경로 표기 포함) gone에서 빠진다. state.json·state.md에는 새 키나 절이 없다. 이동은 `artifacts_moved`, 브랜치 전환·되감기처럼 돌아올 파일은 적지 않는다.

산출물 누락 표시(`[Worklog 산출물 없음]`·`artifacts_missing`)는 같은 세션에 같은 작업의 같은 `path(Eid)`를 한 번만 보인다(2.27.0, 세션 파일 `missing_noted`). `verify`는 매번 전체를 대조한다.

save·skip·new-work 결과에는 `hooks`(이 세션에서 SessionStart·UserPromptSubmit·Stop Hook이 돌았는지)가 붙고, 세 Hook 기록이 하나도 없으면 `warning`(Hook 미작동 의심)이 붙는다(2.16.0; UserPromptSubmit만 없는 것은 `!` 셸 입력·다른 세션의 알림으로 시작한 턴에서 정상이라 경고하지 않는다). 폴더를 연결한 턴(`hooks_seen`에 new-work가 남긴 `connect`뿐, 2.26.0)에는 Hook이 아직 세션 파일에 기록할 수 없었으므로 세 값이 `false`가 아니라 `null`(알 수 없음)이고, save·skip·verify 결과에 `notice` "첫 연결 턴: Hook 세션 파일이 없어 hooks는 null(다음 턴부터 true/false)."이 붙는다(new-work 결과에는 붙이지 않는다). use는 같은 경우 본문 앞에 `[Worklog Hook 경고]` 줄을 더한다. Pi 확장이 실행되지 않는 세션(프로젝트 설치에서 프로젝트를 신뢰하지 않아 `.pi/extensions/worklog.ts`가 로드되지 않은 경우 등)은 Hook 기록이 없어 표시하지 않는다. 세션 파일의 `turn`은 UserPromptSubmit과, 턴을 끝내 주는 Stop Hook이 각각 1씩 올린다(번호는 건너뛸 수 있고 턴마다 다르기만 하면 된다). `new-work` 결과의 `notice`는 다른 작업의 유효 제약이 새 작업에 적용되지 않음을 알린다.

## 작업 선택 규칙

| 상황 | 동작 |
|---|---|
| 턴 시작 | `[Worklog worklog/2 SessionStart` 주입이 보이면 사용, 없으면 show |
| 현재 작업이 없고 기존 작업 지정 | `use <id> --quote "<사용자 원문>"` |
| 새 작업 지정 | `new-work "<제목>" --quote "<사용자 원문>"` |
| 현재 작업도 지정도 없고 기존 작업이 있음 | 요청을 수행하기 전에 "어느 작업에 기록할까요? [목록] / 새 작업"을 한 번 묻고 skip. 모델은 기존 작업을 고르지 않는다 |
| 기존 작업이 하나도 없음(미연결 폴더 `auto=on`, 빈 목록) | 묻지 않고 첫 기록 대상 요청에서 `new-work`(미연결이면 `--root <후보>`), 그 턴에 save. 제목을 사용자가 주지 않았으면 요청에서 정하고 첫 summary는 `[auto] 제목 자동: <제목>` (2.25.0) |
| 미연결 폴더 `auto=off` | 사용자가 `새 작업: <제목>`이라 할 때만 연결(2.24 동작) |
| 작업 하나뿐이고 "이어서" | 그 작업을 use, quote는 사용자 말 |
| 현재 작업 있음 | 같은 작업을 이어감, 사용자가 다시 지정할 때만 전환 |
| `| FORK` 세션 | 요청을 먼저 수행하고 첫 기록 대상 요청의 답변 끝에 "이 곁가지의 기록을 어느 작업에 남길까요? [본 세션의 현재 작업 / 목록 / 새 작업]"을 한 번 묻고 skip. 지정되면 use(또는 new-work) 뒤 그 턴부터 스스로 save, 지정 전에는 save하지 않는다(2.27.0). 본 세션은 곁가지의 사건을 id로 인용해 채택만 한다 |
| 잘못 골랐고 아직 save 전 | `use <맞는 id> --quote` |
| 잘못 기록함(save 뒤) | `reassign <잘못된 id> <맞는 id> --events E…-E… --quote`, 사건 이동 없음 (2.25.0). 맞는 작업이 아직 없으면 `<맞는 id>` 대신 `--new "<제목>"`(2.27.0) |
| 자동 제목이 틀림 | `rename <id> "<새 제목>" --quote` (2.25.0) |

모델은 기존 작업을 임의로 고르지 않는다. 새 작업을 만드는 것은 사용자 지시가 있거나 기존 작업이 하나도 없을 때뿐이다. 같은 세션이 같은 턴에 두 번째 `new-work`를 하면 거부한다(재시도로 `-2` 작업이 생기는 것을 막는다. 의도했으면 `--force`). 2.26.0부터 턴 0(폴더를 막 연결한 첫 턴, Hook이 턴을 세지 않는 세션)도 검사한다. 그래서 Hook 없이 쓰는 세션(프로젝트 수준 pi 등)은 두 번째 작업부터 `--force`가 필요하다. 재시도 표식 `new_work_turn`·`new_work_id`는 index.json보다 먼저 세션 파일에 쓴다. index 쓰기가 실패한 뒤 재시도하면 그 id가 index에 없으므로 통과하고 같은 id를 다시 만든다. 세션 쓰기(현재 작업 지정)가 실패한 뒤 재시도하면 작업이 이미 있으므로 거부하고 그 id와 `use <id>`를 알려 준다. use·new-work는 빈 quote를 거부한다. 원문이 실제 사용자 발언인지까지 기계가 검증하지는 못한다. current_work는 세션에 저장하므로 압축 뒤 유지되지만 새 세션에는 다시 지정이 필요하다.

save 입력의 `work`는 명시 작업 ID다. 있으면 비어 있지 않은 문자열이어야 한다. 생략하면 current_work를 사용한다. 둘 다 없으면 다음 문구로 거부한다: `현재 작업이 없습니다. 사용자가 지정한 작업으로 use <id> --quote 또는 new-work "제목" --quote 후 저장하세요. 작업 목록: …`. 사용자에게 지정을 요청하며 지정 없는 턴은 skip으로 끝낸다.

## 명령표

`python3 -B core/wl.py <명령> --root <프로젝트> --tool <claude|codex|agy|pi>`를 사용한다. root 생략 시 cwd의 루트 후보다(2.25.0, 위 '루트 후보'). Hook은 stdin 이벤트의 cwd·session_id를 사용한다. 명령 세션은 도구별 환경변수(CODEX_THREAD_ID·CLAUDE_CODE_SESSION_ID·ANTIGRAVITY_CONVERSATION_ID·PI_SESSION_ID)로 구분한다. `WL_TOOL`·`WL_SESSION_ID`는 시험에서 세션을 직접 지정할 때 쓴다. `--tool`도 `WL_TOOL`도 없는데 도구 세션 변수가 둘 이상 있으면(예: Claude Code 안에서 실행한 pi는 부모의 CLAUDE_CODE_SESSION_ID를 물려받는다) 도구를 추정하지 않고 `도구를 확정할 수 없습니다: <변수>(<도구>), …가 함께 있습니다. --tool <codex|claude|agy|pi>를 지정하세요.`로 거부한다(2.27.0). 세션 없이도 도는 show·works·verify(`--work` 없이)·off도 같은 문구로 거부한다. 다만 미연결 폴더의 show(NOT_CONNECTED 안내)와 이미 꺼진 폴더의 off(`already: true`)는 세션을 읽지 않으므로 예외다. 미연결 폴더의 off는 세션 판정보다 미연결 오류가 먼저 난다. `on`은 off 표식만 지우고 세션을 읽지 않으므로 두 변수여도 거부하지 않는다. 도구 세션 변수가 하나도 없으면 지금처럼 세션 없이 돈다. 변수가 하나면 그 도구로 추정한다. save의 신선도 거부(`show 먼저 실행하세요`·`기록이 바뀌었습니다`) 끝에는 이번 호출의 판정 `(이 호출: tool=<도구> session=<id>, <--tool 지정|WL_TOOL|환경변수 <이름>에서 추정>)`이 붙는다(2.27.0). Hook 명령은 설치기가 늘 `--tool`을 넣으므로 영향이 없다.

| 명령 | 역할 |
|---|---|
| `works` | 전체 작업 목록 JSON, 상태별 정렬 |
| `use <id> --quote "<원문>"` | current_work·selected_turn 지정, show와 같은 상태(못 본 사건 절 포함)를 본문으로 출력·last_seen 갱신, 없는 id·빈 quote 거부 |
| `new-work "<제목>" --quote "<원문>" [--root <후보>] [--force]` | 작업 생성 후 선택, 결과에 id 반환. 폴더를 처음 연결하면 `connected`·`connected_changed`·`connected_notes`. 쓸 수 없는 폴더는 `{"ok": false, "error": …}`·exit 2. 같은 턴 두 번째는 턴 0도 거부(`--force`로 해제, 2.26.0) |
| `show [--work <id>] [--json]` | `--json`(2.28.0, 필드 잠정): 텍스트 대신 JSON 한 덩이 `{format, core, work, title, state(state.json 그대로, 첫 save 전 null), unseen: [{id, type, at, summary, occurred_at?}](최근 20건), unseen_omitted, project(project.md 본문 또는 null), notes(텍스트 show의 안내 줄), off?}`. 현재 작업이 없으면 `{format, core, work: null, works: [works 명령과 같은 목록], off?}`, 미연결이면 `works: []`·`connected: false`. 투영 복구·last_seen 갱신은 텍스트와 같다. 텍스트: 현재 또는 지정 작업 현황 출력·투영 복구·last_seen 갱신, 현재 작업 없으면 목록·exit 0. 연결되지 않은 폴더면 `Worklog에 연결되지 않은 폴더입니다(<root>에 .worklog 없음).` 한 줄 뒤에 Hook과 같은 함수로 만든 `[Worklog worklog/2 show | NOT_CONNECTED | root=… | auto=… | git=…] <안내>` 한 줄(2.26.0). use·rename·reassign·on·off의 미연결 거부도 같은 두 줄이다(머리의 이벤트 이름만 명령 이름). 작업이 0개면 `Worklog 작업 없음. ` 뒤에 Hook EMPTY와 같은 안내(`auto=on`이면 묻지 않고 만드는 문장, `auto=off`면 작업을 지정받을 때까지 기다리는 문장). 세션이 알려져 있고 `last_seen` 뒤에 사건이 있으면 본문 끝에 `## 이 세션이 아직 못 본 사건 (seq a~b)` 절(한 줄 `- <id> · <tool>:<세션 앞 8자> · <type> · <summary 80자>`, 최신 20건, 초과분은 `…외 n건` 한 줄)을 붙인다(2.23.0). 0건이면 절이 없다 |
| `save [--ts <YYYY-MM-DDTHH:MM:SSZ>]` | stdin JSON으로 현재 또는 입력 work 작업에 사건 추가, index 갱신·saved_turn 기록. `--ts`(2.28.0, 가져오기 전용, `--session <도구>:<원래 세션 id>`와 함께 쓰는 것이 전제)는 사건이 실제로 일어난 UTC 시각으로 refs에 `{"occurred_at"}`를 더하고 `at`은 저장 시각 그대로 둔다. 다른 형식·지금보다 뒤(미래) 시각은 거부. 결과 `hooks`는 `true`/`false`, 폴더를 연결한 턴에는 `null`(알 수 없음)과 `notice`(2.26.0) |
| `skip "<이유>"` | 원장에 쓰지 않고 skipped_turn 기록 |
| `verify [--work <id> \| --all]` | 잠금 안에서 투영 검증, --all은 전체와 index↔폴더 일관성 검증·writer 손상 등의 warnings 출력. 작업별 `artifacts`는 `{missing, changed, checked}`이고 `artifacts_gone`으로 지운 것이 있으면 `gone`이 붙는다(2.27.0) |
| `reassign <잘못된 id> (<맞는 id> \| --new "<제목>") --events E0003-E0005 --quote "<원문>" [--force]` | 위 '잘못 기록한 사건의 정정'. 결과 `{ok, from, to, events, misfiled, refiled, moved: {decisions, constraints, artifacts}, already_there?, upgraded?, resumed?, created?, current_work, decisions, constraints, notice?}`(맞는 작업의 유효 목록. `created`·`notice`는 `--new`, 2.27.0), 실패 시 `{ok: false, partial: true, done, refiled, misfiled, created?, error, next, message}` |
| `rename <id> "<새 제목>" --quote "<원문>"` | index title만 변경 + CHANGE 사건. 결과 `{ok, work, title, old_title, saved, seq}` |
| `archive <id>` / `reopen <id>` | CHECKPOINT("작업 보관/재개", COMPLETED/ACTIVE) 추가와 index 상태 갱신, quote 불필요. 응답의 `status`는 추가 뒤 fold한 실제 상태다(2.28.0). 요청한 상태와 다르면(시각이 더 늦은 가져온 사건이 덮는 경우) 사건은 남기고 `{"ok": false, "status": <실제>, "requested", "saved", "seq", "error": "상태를 바꾸지 못했습니다: 실제 <status>"}`·exit 2 |
| `off --quote "<원문>" [--reason "<이유>"]` | `.worklog/off` 생성, 원장에 쓰지 않음. 사용자 원문 필수·이유 선택. 이미 꺼져 있으면 표식 유지·"이미 꺼짐"(시각·이유) |
| `on` | `.worklog/off` 삭제·꺼져 있던 기간 출력. 이미 켜져 있으면 "이미 켜짐"(오류 아님). off·on 모두 `.worklog/` 없거나 표식이 링크면 거부 |
| `hook` | SessionStart 주입, 현재 작업의 last_seen 갱신 |
| `turn-start` | UserPromptSubmit, turn 증가 |
| `stop-hook` | 이번 턴 save·skip·선택 확인 |
| `help` | save 입력 형식·작업 선택 명령 예시 |

## Hook과 주입 형식

세 Hook은 stdin의 cwd·세션 ID를 받는다(agy는 `workspacePaths[0]`·`conversationId`, 2.24.0). 기록 위치는 그 cwd의 루트 후보다(2.25.0). 후보에 `.worklog/`가 없으면 SessionStart는 아래 NOT_CONNECTED 한 줄, turn-start·stop-hook은 빈 출력·exit 0이다(agy는 `{}`). 디렉터리가 비어 있어도 연결된다. `hook` 출력 계약은 `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}`다(agy: `{"injectSteps":[{"systemMessage":{"systemMessage":"…"}}]}`; Stop 차단은 agy에서 `{"decision":"continue","reason":…}`, 통과는 `{}`).

미연결(2.25.0, 한 줄, 세션 파일·갱신 검사 없음):

```text
[Worklog worklog/2 SessionStart | NOT_CONNECTED | root=<후보> | auto=<on|off> | git=<yes|no>( | FORK)] <안내>
```

`auto=on`의 안내는 "첫 기록 대상 요청에서 묻지 않고 `new-work "<제목>" --quote "<요청 원문>" --root <후보>`로 연결하고 그 턴에 save한다"이고, `auto=off`의 안내는 2.24의 "사용자가 "새 작업: <제목>"이라 하기 전까지 Worklog 절차를 적용하지 않는다"이다. 후보가 세션 폴더와 다르면 "root는 세션 폴더 <cwd>가 아니라 git 최상위 폴더다(또는 가장 가까운 상위 Worklog 기록 폴더다)", git 최상위 위에 기록이 있으면 "상위 폴더 <경로>의 Worklog 기록은 git 경계 밖이라 쓰지 않는다"가 붙는다. 이벤트의 `source`가 `fork`(Claude `/branch`·`--fork-session`, Codex `/fork`)면 연결된 폴더의 헤더 끝에도 `| FORK`가 붙는다. fork는 자기 세션 ID를 가지므로 세션 파일이 따로이고 현재 작업이 없다(본 세션 파일은 그대로).
- pi `--fork`(2026-10-21 확인): 새 세션 id와 별도 세션 파일을 만들지만 확장의 session_start reason이 `startup`이라 `| FORK`는 붙지 않는다. `NO_CURRENT_WORK`로 시작하므로 모델이 작업을 묻는다.
- agy `/rewind`(2026-10-21 확인): 새 대화(새 세션 id)를 만들어 SessionStart가 다시 오고 현재 작업이 없는 상태로 시작한다. 파일은 복원하지 않으므로 되감기로는 산출물 누락 보고가 생기지 않는다. agy에는 수동 압축 명령이 없다.

연결됨:

```text
[Worklog worklog/2 SessionStart | <PROVIDED|NO_CURRENT_WORK|EMPTY|UNAVAILABLE|OFF> | root=…( | FORK)]
이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.
## 프로젝트 공통 (project.md)
… 선택 파일이 있을 때만, 최대 4,000자 …
## 작업 목록 (ACTIVE·PAUSED, 최근 갱신순 최대 10개 / 전체 N개)
- <id> · <제목> · <status> · <updated_at> · 다음: <next_action 60자>
- 그 외 COMPLETED N개: <id> · <제목> (<날짜>), … (최근 갱신 3개까지. 끝난 작업도 "<id> 이어서"로 바로 잇는다)
## 현재 작업: <id> · <제목>
… 이 세션 현재 작업의 state.md 전체 …
## 이 세션이 아직 못 본 사건 (seq a~b)
… 선택 절: 이 세션의 last_seen 뒤에 사건이 있을 때만, 최신 20건 …
```

현재 작업이 없으면 마지막 부분은 아래와 같다. EMPTY는 index가 없거나 작업 0개, NO_CURRENT_WORK는 작업이 있지만 현재 선택 없음, PROVIDED는 현재 작업 상태 제공이다. UNAVAILABLE은 원장·index 읽기 실패나 형식 1 루트 원장 잔존으로 주입을 만들 수 없는 상태다. OFF는 `.worklog/off`가 있는 상태로, 다른 내용 없이 한 줄 `[Worklog worklog/2 SessionStart | OFF | root=…] Worklog가 꺼져 있다(이유: …, 시각: …). 사용자가 켜 달라고 하기 전까지 Worklog 절차를 적용하지 않는다.`만 주입하고 세션 파일을 만들거나 갱신하지 않는다. 꺼진 동안 turn-start·stop-hook은 아무것도 하지 않는다(차단 없음). save·skip·use·new-work·show·works는 평소대로 동작하며 JSON 결과 최상위에 `"off": true`, show·use 본문 앞에 `[Worklog OFF]` 줄을 더한다.

```text
## 현재 작업 없음
사용자에게 작업을 지정받을 때까지 저장하지 않는다. 지정이 없으면 한 번 묻고 skip으로 마친다. 작업이 하나뿐이고 "이어서"면 그 작업을 use한다.
```

EMPTY(작업 0개)이고 `auto=on`이면 둘째 줄 대신 `기존 작업이 없다. 첫 기록 대상 요청에서 묻지 않고 new-work로 새 작업을 만들고 그 턴에 save한다(제목은 사용자가 주면 그대로, 없으면 요청에서 정한다).`(2.25.0).

**Hook 중복(2.25.0, claude·codex).** 사용자 수준과 프로젝트 수준에 Hook이 둘 다 등록되면 같은 이벤트가 두 번 온다. 같은 세션의 두 번째 호출은 무동작이다. 키: SessionStart = `source` + 시각(같은 source가 5초 안에 다시 오고 그 사이 턴 변화 — `turn`·`hooks_seen`의 UserPromptSubmit·Stop — 가 없으면 중복. 사이에 프롬프트나 Stop이 있었으면 정상 재개로 보고 다시 주입한다, 2.26.0. `source`가 없는 이벤트는 키 없음), UserPromptSubmit = 이벤트의 `turn_id`(Codex, 2026-10-20 실측) 또는 `prompt_id`(그런 필드를 보내는 도구) — 둘 다 없으면 지금처럼 매번 센다, Stop = 앞 Stop이 남긴 턴 번호와 `stop_hook_active` + "앞 Stop이 끝나기 전에 시작한 프로세스"(두 등록은 병렬로 돈다. 차례로 온 다음 Stop은 중복이 아니므로 2.16.0의 `!` 셸 입력 턴 판정이 그대로다). agy는 2.24.2의 `agy_pre`·`agy_stop`을 그대로 쓴다. 미연결 폴더는 세션 파일이 없어 중복을 구분하지 않는다(한 줄 주입이 두 번 갈 수 있다).

세 Hook은 돌 때마다 세션 파일의 `hooks_seen`에 시각을 남긴다(꺼져 있을 때는 남기지 않는다). save·skip·verify가 이것으로 Hook 작동 여부를 보고하므로, 신뢰되지 않았거나 꺼진 Hook은 첫 턴의 결과에서 드러난다. stop-hook은 saved_turn·skipped_turn·selected_turn 중 하나가 turn과 같으면 통과한다. 셋 다 없으면 `{"decision":"block","reason":…}`로 종료를 막는다. stop_hook_active가 참이면 무한 반복 방지를 위해 통과한다. 선택만 해도 Hook은 통과할 수 있으나 지침의 턴 끝 save·읽기 전용 skip 규칙은 유지한다. Pi는 확장(`worklog.ts`)이 Hook 역할을 한다. 확장이 실행되지 않는 세션(프로젝트 설치에서 프로젝트를 신뢰하지 않은 경우 등)은 지침만 적용하며 강제되지 않는다. Codex Hook 정의가 바뀌면 사용자가 다시 신뢰해야 한다.

## 이전: 형식 1 → 2

형식 1 루트 원장이 남아 있으면 코어 명령은 exit 2와 `형식 1 기록(.worklog/events.jsonl)이 있습니다. tools/migrate_v1_to_v2.py로 먼저 이전하세요.`로 거부한다. hook은 UNAVAILABLE과 이전 안내를 주입한다.

1. `python3 -B tools/migrate_v1_to_v2.py --project <root> --work-id <id> [--title "<제목>"]`로 dry-run한다. 기본 동작은 파일을 쓰지 않는다.
2. 검토 후 같은 명령에 `--apply`를 붙인다. 필수 파일은 `.worklog/events.jsonl`이며 state.json·state.md·writer.json은 있으면 이동한다. works/ 또는 index.json이 있으면 "이미 형식 2"로 거부한다. 이동 대상은 일반 파일이어야 하며 링크·디렉터리면 첫 변경 전에 거부한다. .worklog는 실제 디렉터리여야 하며 sessions가 있으면 실제 디렉터리여야 한다. 같은 조건을 .lock 잠금 안에서 다시 검사하므로 동시 실행의 두 번째 호출도 "이미 형식 2"로 거부한다.
3. 원장 바이트를 변경하지 않고 works/<id>/로 이동한다. 작업별 seq·id·prev 연결은 그대로 유지하며, 연결이 끊긴 원장은 거부한다.
4. index를 만들고 현황을 재계산한다(state.json.format = worklog/2). title 생략 시 작업 id를 제목으로 쓰며, index status는 원장 fold 결과다. 기존 sessions/ 안의 일반 *.json만 버린다. 링크 등은 남기고 `sessions_skipped`에 표시한다. 이전 세션의 턴 카운터는 재사용하지 않는다.
5. 전후 원장의 줄별 해시와 파일 SHA-256을 함께 대조한다(`line_hashes_match`·`hashes_match`). 재실행은 "이미 형식 2"로 거부한다. 도구는 .worklog 밖에 쓰지 않는다.

형식 1 루트 기록을 읽는 코어는 유지하지 않는다.

## 프로젝트 공통 (project.md)

`project.md`는 원장도 투영도 아니다. 한 작업의 결정·제약은 그 작업의 `state.md`에 남고, **여러 작업에 걸쳐 이 프로젝트에 적용되는 항목**만 여기에 둔다. 원장이나 `state.md`에서 고른 항목을 사용자가 확정("넣어")한 뒤에 기록한다. 모델은 작업을 COMPLETED로 바꾸는 턴과 사용자가 "앞으로 이 프로젝트에서는 …"이라고 말한 턴에만 넣을 줄을 보여 주고 한 번 권유하며, 확정 전에는 쓰지 않는다(규칙 2.23.0). 코어는 SessionStart마다 앞 4,000자를 주입할 뿐 이 파일을 만들거나 쓰지 않는다.

권장 양식(코어는 강제하지 않는다): 절 제목 없이 유효 항목 줄만 둔다. 한 항목은 한 줄이다.

```text
- [P#] (Map:) 본문 (worklog:<프로젝트>/<작업>#E… · YYYY-MM-DD)
```

- `[P#]`는 줄 ID다. 누가 쓰든 다음 번호를 붙인다. `check` 인용으로 사용 여부를 남길 때 쓴다.
- `Map:`은 선택이다. "무엇을 먼저 보라"는 안내(기준 문서·시작점)에만 붙이고, 규칙·제약에는 붙이지 않는다. 적용 조건은 절을 나누지 않고 본문에 자연어로 쓴다("설계 문서를 고칠 때는 …").
- 괄호 꼬리는 출처 포인터와 확인일이다. 포인터 형식은 `worklog:<프로젝트>/<작업>#E…`이며, `<프로젝트>`는 `~/.worklog/installs.json`에 등록된 그 프로젝트 항목의 이름(등록 경로의 마지막 폴더 이름), `<작업>`은 작업 id, `E…`는 사건 ID다. 같은 형식을 확장 모듈의 전역 파일도 쓴다.
- 항목이 바뀌면 같은 줄을 고치고 꼬리에 새 사건을 덧붙인다 `(…#E0058 → #E0144 · 날짜)`. 삭제는 사용자 확정 때만 한다.
- 본문에 사용자 원문 quote를 옮겨 적지 않는다(출처 포인터가 대신한다). 개인 선호는 이 파일이 아니라 사용자 범위 파일(확장 모듈)에 둔다.
- 주입은 앞 4,000자에서 잘리므로 낡은 항목은 사용자 확정으로 `project-archive.md`(주입되지 않음)로 옮긴다.

```text
- [P1] Map: 설계 기준은 docs/design-spec.md §11을 먼저 본다 (worklog:habit-app/summary-review#E0010 · 2026-10-17)
- [P2] 대상 프로젝트 자료는 읽기 전용으로만 본다 (worklog:habit-app/summary-review#E0144 · 2026-10-17)
- [P3] 블록 상태 표현은 C 혼합형을 쓴다 (worklog:habit-app/summary-review#E0058 → #E0123 · 2026-10-17)
- 회의록은 docs/minutes/에 둔다
```

`.worklog/`는 보통 `.gitignore`에 들어 있으므로 이 파일은 기기 안에서만 유지된다. 공유하려면 `.gitignore`에 `!.worklog/project.md` 한 줄을 둔다.

## 의도적 생략과 한계

- 작업 분할·병합 전용 사건은 없다. 새 작업·CHECKPOINT 메모로 연결한다. 새 작업은 다른 작업의 제약을 이어받지 않으며 `new-work`가 그 사실을 `notice`로 알린다.
- 프로젝트 전체 시간순 원장은 없다. 작업별 해시 체인이며 index.updated_at로 최근 작업을 찾는다.
- 세션↔작업 인계 사건은 없다. 선택은 세션 파일에만 남는다.
- 꺼진 기간(`.worklog/off`)은 원장에 남지 않는다. 켠 뒤 그동안 바뀐 것이 있으면 다음 save에 적는다. 세션·작업 단위 off는 없다.
- 목록은 ACTIVE·PAUSED 최대 10개에 최근 COMPLETED 3개 한 줄이다. 전체 목록은 works로 확인한다.
- Stop Hook은 save·skip의 존재만 확인하고 내용은 보지 않는다. quote가 실제 사용자 발언인지도 도구가 확인하지 못한다. 기록은 모델의 지침 준수에 기대며, Hook과 저장 결과의 표시(self_quoted·warning)는 그것이 어긋났을 때 드러나게 하는 장치다.
- 모델의 질문·선택 준수와 압축 뒤 실제 복원은 별도 대화형 시험이 필요하다. 주입만으로 실제 복원을 입증하지 않는다. 시험 결과와 측정 한계는 `docs/VERIFICATION.md`에 있다.
