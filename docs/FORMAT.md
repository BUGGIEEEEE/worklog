# Worklog 기록 형식 2 (`worklog/2`)

> **English summary.** `worklog/2` is the on-disk format of a project's `.worklog/` folder. One project holds several **works** (separate tasks). `index.json` lists them; each work has its own folder `works/<id>/` with an append-only ledger `events.jsonl` and two projections, `state.json` and `state.md`. A work ID is an ASCII slug made from its title (`habit-plan`; `work`, `work-2`… when nothing ASCII remains). Event lines are unchanged from `worklog/1`: one JSON event per line, numbered `seq`/`id` from 1 per work, each line chained to the previous one by `prev` = sha256 of the previous line's bytes. A change to an earlier line that later events follow is detected on read; the last event has no independent reference point, so a change to it is not detected. This is not a defense against deliberate tampering. Each session has a *current work*, set only when the user names one (`use <id> --quote …` or `new-work "<title>" --quote …`); without one, `save` is refused and the model asks the user. The SessionStart injection lists the works and, if the session has a current work, its full state — also after compaction. The goal is set once; later changes are decisions that `replace` older ones (`D1..`), and constraints (`C1..`) persist until the user removes them. A save that lists artifacts must include a `check` entry for every active decision and constraint: a verbatim quote (4+ characters) from the artifact body, or `미반영: <reason>` ("not reflected"). Saves are serialized with `flock` and rejected if the session has not read the latest record of that work. A `worklog/1` folder is migrated with `tools/migrate_v1_to_v2.py`; the ledger bytes move unchanged into `works/<id>/`. Changing the format means re-migrating existing ledgers. Since 2026-10-09: decisions and constraints carry a `source` (`user` for REQUEST/APPROVAL/D_USER events, `model` otherwise); a model constraint can be removed with a reason alone, a user constraint only with the user's words. A `check` quote that merely repeats the rule's own text is accepted but reported as `self_quoted` (it is not evidence); non-text artifacts (images, archives) are hashed but not searched for quotes. Each hook records its run in the session file (`hooks_seen`), and save/skip/verify report whether the hooks are active. The SessionStart list also names the most recent COMPLETED works, and `state.md` summarizes artifacts by folder once there are more than 15.

확정일 2026-10-06. 구현: `core/wl.py`. 이 문서와 구현이 다르면 구현을 고치지 말고 먼저 보고한다.

> **형식 변경 = 재이전.** 필드 이름·사건 종류·ID 규칙·해시 연결·저장 구조를 바꾸면 기존 기록을 새 형식으로 다시 이전한다. 이전 도구와 검증도 함께 고친다. 기존 원장의 해석이 그대로인 선택 필드 추가만 같은 형식 번호를 유지한다.

## 저장 구조 (`<프로젝트>/.worklog/`)

```text
.worklog/
  index.json
  project.md                         # 선택, 사용자 편집
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
| `project.md` | 프로젝트 공통 목표·제약, 원장 아님 | 사용자만 편집, 설치기·코어는 생성하지 않음 |
| `works/<id>/events.jsonl` | 해당 작업의 추가 전용 원장, 한 줄 = 사건 | 코어 save·archive·reopen |
| `works/<id>/state.json` | 해당 원장에서 재계산하는 기계용 현황 | 코어 |
| `works/<id>/state.md` | 같은 현황의 사람·주입용 본문 | 코어 |
| `works/<id>/writer.json` | 마지막 작성자 정보 `{tool, session_id, seq}`, 원장·선택·독점권의 근거 아님 | 코어 |
| `sessions/<tool>_<session>.json` | `{current_work, last_seen: {"<id>": seq}, hooks_seen: {"SessionStart"\|"UserPromptSubmit"\|"Stop": 시각}, turn, saved_turn, skipped_turn, selected_turn}` | 코어, 원장·해시 연결 대상 아님 |
| `.lock` | 프로젝트 내 동시 변경을 flock으로 직렬화 | 코어 |
| `off` | `{at, reason, by, quote}` JSON(reason·by는 없으면 null). 있으면 이 프로젝트 전체의 Worklog가 꺼짐, 원장 아님 | 코어 off·on, `.lock` 안에서 생성·삭제 |

작업 ID는 제목에서 만든 ASCII 슬러그(소문자·숫자·`-`, 40자 이내)다. 비ASCII만 남거나 숫자만 남으면("던전디펜스 1화" → `1`은 쓰지 않음) `work`이며 중복은 `-2`, `-3`으로 구분한다. 제목 앞의 `새 작업:`은 제거한다. 한글 원제목은 index의 title에 보관한다. 사건 ID와 결정·제약 ID는 작업별이다.

연결 신호는 `.worklog/` 디렉터리 존재다. 설치 직후에는 비어 있다. `new-work`는 index 항목과 빈 작업 폴더를 만들고 원장은 첫 save로 만든다. 현황 두 파일을 직접 고치지 않는다. 불일치하면 원장이 기준이며 `show`로 복구한다. 형식 1의 루트 원장과 `writer.json`을 형식 2 저장 계약으로 사용하지 않는다.

## 사건 (events.jsonl 한 줄)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `v` | ✓ | 사건 형식 1(`v: 1` 유지). 상태·저장 구조는 worklog/2 |
| `seq`, `id` | ✓ | 작업마다 1부터 연속. `id = E%04d` |
| `prev` | ✓ | 직전 줄 바이트의 sha256(첫 줄 null). 끊기면 읽기 거부. 뒤에 사건이 이어진 과거 줄의 변경은 읽기 때 감지된다. 마지막 사건은 독립적 기준점이 없어 감지 대상이 아니다. 악의적 변조 방지 장치가 아니다 |
| `type` | ✓ | 아래 15종 |
| `at` | ✓ | 기록 시각(UTC) |
| `occurred_at` | | 실제 발생 시각이 기록 시각과 다를 때(이전 사건 등) |
| `tool`, `session_id` | ✓ | 기록한 도구(`codex`/`claude`/`pi`)와 그 세션 ID |
| `summary` | ✓ | 한두 문장 |
| `quote` | 조건부 | 사용자 원문 일부. REQUEST·APPROVAL·D_USER, 목표 설정, 제약 해제, 작성권 인수에 필수 |
| `changes` | ✓ | 상태 변경: `goal`·`decisions`·`constraints`·`constraints_remove`·`waiting`·`next_action`·`status`·`artifacts` |
| `refs` | | 호환용. 의미가 정해지지 않아 지침·도움말에서 뺐다. 받으면 그대로 저장하고 해석하지 않는다 |
| `source` | | 이전된 사건의 출처: `path`·`line`·`sha256`·원래 종류 |
| `check` | 텍스트 산출물 시 | 유효 결정·제약마다 산출물 **본문**의 인용(공백 정규화 후 실제로 있어야 함) 또는 `미반영: <이유>`. 미반영 ID는 저장 결과의 `unreflected`에 표시. 산출물이 모두 비텍스트(UTF-8이 아니거나 NUL 포함)면 check는 선택이고 미반영만 받는다 |
| `self_quoted` | | 인용이 규칙 문장과 같았던 ID 목록. 저장은 되지만 반영의 증거가 아니다. 저장 결과에도 같은 이름으로 표시 |
| `writer_acquired` | | 작성권 인수 기록 |

**사건 종류 15종:** REQUEST, APPROVAL, D_USER, D_AGENT, ASSUMPTION, RESULT, VERIFICATION, BLOCKER, CORRECTION, CHECKPOINT, HANDOFF, CHANGE, Q, WRITER_ACQUIRED, WRITER_RELEASED.
- 사용자 출처(원문 필수): REQUEST, APPROVAL, D_USER.
- 제약 해제 가능: D_USER, APPROVAL, CORRECTION.
- 이 목록에 없는 기존 종류는 이전할 때 15종 중 하나로 대응하고, 원래 이름은 `source`에 남긴다.
- **이전 사건:** `tool: "import"`, `session_id`는 이전 실행 ID, `quote`는 null이며 대신 `source`(원본 경로·줄·줄 sha256·원래 종류·원래 ID·원래 기록 시각, 있으면 원래 세션·권위)가 근거다. 원본에 없는 값은 비워 두고 추정하지 않는다. 이전 사건은 상태를 바꾸지 않고, 사용자 확인을 거친 현재 상태 사건 1건만 상태를 정한다. 외부 기록을 가져오는 이전 도구는 이 배포본에 포함하지 않는다(형식 1 → 2 이전 도구만 포함).
- 작업 경계를 나타내는 별도 사건 종류는 없다. 작업마다 독립 원장과 사건 ID·해시 연결을 유지한다.

## 현재 상태 (state.json / state.md)

`format: "worklog/2"`, `seq`, `goal`(최초 목표, 한 번만. 첫 save에 없으면 작업 제목), `status`(ACTIVE/PAUSED/BLOCKED/COMPLETED/CANCELLED), `decisions`[유효만: id·text·event·source·replaces], `constraints`[유효만: id·text·event·source], `waiting`, `next_action`, `artifacts`[path·sha256·event], `superseded`, `removed_constraints`, `updated_at`, `updated_by`{tool, session_id}.

- **우선순위:** 최초 목표의 값이 바뀌면 유효 결정이 우선한다. `replaces`로 기록된 변경은 충돌이 아니다. `state.md`는 goal 아래에 최신 결정을 "현재 범위"로 보여 준다.
- **출처(`source`):** 결정·제약을 넣은 사건이 REQUEST·APPROVAL·D_USER면 `user`, 그 밖이면 `model`. `state.md`에 `[사용자]`/`[모델]`로 표시한다. 제약 추가는 어떤 사건 종류든 할 수 있다.
- **제약**은 같은 문장의 재입력이 저장할 때 무시된다. 해제는 출처별이다: `user` 제약은 사용자 출처 종류(D_USER·APPROVAL·CORRECTION)와 quote가 필요하고, `model` 제약은 어떤 종류든 사유만으로 해제할 수 있다. "다음 요청까지 보류"처럼 요청이 오면 끝나는 것과 확인되지 않은 가정(`확인 필요: …`)은 `waiting`에 둔다. 작업량·목표 범위는 제약이 아니라 결정이다.
- ID: 결정 `D1..`, 제약 `C1..`. 원장 순서로 다시 계산해도 같은 값이 나온다.
- `state.md`의 산출물은 15개까지 경로·해시를 나열하고, 그보다 많으면 폴더별 개수와 최근 사건만 보여 준다. 전체 목록은 `state.json`에 있다.
- `state.md` 제목에는 작업 id·제목이 들어간다. 각 작업의 상태를 독립적으로 계산한다. `project.md`는 원장이나 투영이 아니다.

## 저장과 보호

save 순서: 잠금 → 선택 작업 원장 읽기·해시 연결 확인 → 작업별 신선도 확인 → 입력 검사(check 인용 대조 포함) → 사건 추가(fsync) → 다시 읽어 비교 → 현황 재계산 → 투영 원자적 교체 → 대조 → index·세션 갱신.

세션 독점은 없다. 세션이 마지막으로 본(use·show·hook·save) `last_seen[id]`보다 원장이 앞서면 "기록이 바뀌었습니다"로 거부한다. `show` 후 다시 저장한다. 이미 사건이 있는 작업을 읽지 않은 세션도 먼저 읽어야 한다. `use`는 선택 작업의 현재 상태를 출력하고 last_seen을 갱신하므로 별도 show 없이 바로 저장할 수 있다. `new-work`는 작업 id를 JSON으로 반환한다. 작성권 인수는 사용자 명시 승인일 때만 `takeover`와 quote로 기록한다. 사건 추가 뒤 투영 쓰기가 실패하면 원장이 기준이고 show로 복구한다.

텍스트 산출물이 있는 save는 유효 결정·제약마다 check를 넣는다. 규칙이 지켜졌음을 보여 주는 본문 구절을 4자 이상 따옴표로 인용하거나 `미반영: <이유>`를 적는다. 공백 정규화 후 본문에 없는 인용은 거부한다. 미반영은 저장 결과의 `unreflected`에 표시하며, 작업 방식 제약이나 그림·압축 파일처럼 인용할 수 없는 것은 미반영이 정상이다. 인용이 규칙 문장과 같으면 저장은 되지만 `self_quoted`에 표시한다. 규칙 문장을 본문에 써 넣어 통과시키는 것은 반영의 증거가 아니다. 산출물이 모두 비텍스트면 인용 대조 없이 해시만 남기고, check는 선택이며 미반영만 받는다.

save·skip·new-work 결과에는 `hooks`(이 세션에서 SessionStart·UserPromptSubmit·Stop Hook이 돌았는지)가 붙고, UserPromptSubmit 기록이 없으면 `warning`(Hook 미작동 의심)이 붙는다. use는 같은 경우 본문 앞에 `[Worklog Hook 경고]` 줄을 더한다. Pi는 Hook이 없어 표시하지 않는다. `new-work` 결과의 `notice`는 다른 작업의 유효 제약이 새 작업에 적용되지 않음을 알린다.

## 작업 선택 규칙

| 상황 | 동작 |
|---|---|
| 턴 시작 | `[Worklog worklog/2 SessionStart` 주입이 보이면 사용, 없으면 show |
| 현재 작업이 없고 기존 작업 지정 | `use <id> --quote "<사용자 원문>"` |
| 새 작업 지정 | `new-work "<제목>" --quote "<사용자 원문>"` |
| 현재 작업도 지정도 없음 | 목록을 제시하고 "어느 작업으로 진행할까요? [목록] 새 작업이면 제목을 알려 주세요."를 한 번 묻고 skip |
| 작업 하나뿐이고 "이어서" | 그 작업을 use, quote는 사용자 말 |
| 현재 작업 있음 | 같은 작업을 이어감, 사용자가 다시 지정할 때만 전환 |
| 잘못 기록함 | 양쪽 작업에 CORRECTION, 잘못 들어간 사건 ID와 작업 표시, 사건 이동 없음 |

모델은 작업을 임의로 고르거나 만들지 않는다. use·new-work는 빈 quote를 거부한다. 원문이 실제 사용자 발언인지까지 기계가 검증하지는 못한다. current_work는 세션에 저장하므로 압축 뒤 유지되지만 새 세션에는 다시 지정이 필요하다.

save 입력의 `work`는 명시 작업 ID다. 있으면 비어 있지 않은 문자열이어야 한다. 생략하면 current_work를 사용한다. 둘 다 없으면 다음 문구로 거부한다: `현재 작업이 없습니다. 사용자가 지정한 작업으로 use <id> --quote 또는 new-work "제목" --quote 후 저장하세요. 작업 목록: …`. 사용자에게 지정을 요청하며 지정 없는 턴은 skip으로 끝낸다.

## 명령표

`python3 -B core/wl.py <명령> --root <프로젝트> --tool <claude|codex|pi>`를 사용한다. root 생략 시 cwd다. Hook은 stdin 이벤트의 cwd·session_id를 사용한다. 명령 세션은 도구별 환경변수(CODEX_THREAD_ID·CLAUDE_CODE_SESSION_ID·PI_SESSION_ID)로 구분한다. `WL_TOOL`·`WL_SESSION_ID`는 시험에서 세션을 직접 지정할 때 쓴다.

| 명령 | 역할 |
|---|---|
| `works` | 전체 작업 목록 JSON, 상태별 정렬 |
| `use <id> --quote "<원문>"` | current_work·selected_turn 지정, show와 같은 상태를 본문으로 출력·last_seen 갱신, 없는 id·빈 quote 거부 |
| `new-work "<제목>" --quote "<원문>"` | 작업 생성 후 선택, 결과에 id 반환 |
| `show [--work <id>]` | 현재 또는 지정 작업 현황 출력·투영 복구·last_seen 갱신, 현재 작업 없으면 목록·exit 0 |
| `save` | stdin JSON으로 현재 또는 입력 work 작업에 사건 추가, index 갱신·saved_turn 기록 |
| `skip "<이유>"` | 원장에 쓰지 않고 skipped_turn 기록 |
| `verify [--work <id> \| --all]` | 잠금 안에서 투영 검증, --all은 전체와 index↔폴더 일관성 검증·writer 손상 등의 warnings 출력 |
| `archive <id>` / `reopen <id>` | CHECKPOINT("작업 보관/재개", COMPLETED/ACTIVE) 추가와 index 상태 갱신, quote 불필요 |
| `off --quote "<원문>" [--reason "<이유>"]` | `.worklog/off` 생성, 원장에 쓰지 않음. 사용자 원문 필수·이유 선택. 이미 꺼져 있으면 표식 유지·"이미 꺼짐"(시각·이유) |
| `on` | `.worklog/off` 삭제·꺼져 있던 기간 출력. 이미 켜져 있으면 "이미 켜짐"(오류 아님). off·on 모두 `.worklog/` 없거나 표식이 링크면 거부 |
| `hook` | SessionStart 주입, 현재 작업의 last_seen 갱신 |
| `turn-start` | UserPromptSubmit, turn 증가 |
| `stop-hook` | 이번 턴 save·skip·선택 확인 |
| `help` | save 입력 형식·작업 선택 명령 예시 |

## Hook과 주입 형식

세 Hook은 stdin의 cwd·세션 ID를 받는다. `.worklog/`가 없으면 빈 출력·exit 0이다. 디렉터리가 비어 있어도 연결된다. `hook` 출력 계약은 `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}`다.

```text
[Worklog worklog/2 SessionStart | <PROVIDED|NO_CURRENT_WORK|EMPTY|UNAVAILABLE|OFF> | root=…]
이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.
## 프로젝트 공통 (project.md)
… 선택 파일이 있을 때만, 최대 4,000자 …
## 작업 목록 (ACTIVE·PAUSED, 최근 갱신순 최대 10개 / 전체 N개)
- <id> · <제목> · <status> · <updated_at> · 다음: <next_action 60자>
- 그 외 COMPLETED N개: <id> · <제목> (<날짜>), … (최근 갱신 3개까지. 끝난 작업도 "<id> 이어서"로 바로 잇는다)
## 현재 작업: <id> · <제목>
… 이 세션 현재 작업의 state.md 전체 …
```

현재 작업이 없으면 마지막 부분은 아래와 같다. EMPTY는 index가 없거나 작업 0개, NO_CURRENT_WORK는 작업이 있지만 현재 선택 없음, PROVIDED는 현재 작업 상태 제공이다. UNAVAILABLE은 원장·index 읽기 실패나 형식 1 루트 원장 잔존으로 주입을 만들 수 없는 상태다. OFF는 `.worklog/off`가 있는 상태로, 다른 내용 없이 한 줄 `[Worklog worklog/2 SessionStart | OFF | root=…] Worklog가 꺼져 있다(이유: …, 시각: …). 사용자가 켜 달라고 하기 전까지 Worklog 절차를 적용하지 않는다.`만 주입하고 세션 파일을 만들거나 갱신하지 않는다. 꺼진 동안 turn-start·stop-hook은 아무것도 하지 않는다(차단 없음). save·skip·use·new-work·show·works는 평소대로 동작하며 JSON 결과 최상위에 `"off": true`, show·use 본문 앞에 `[Worklog OFF]` 줄을 더한다.

```text
## 현재 작업 없음
사용자에게 작업을 지정받을 때까지 저장하지 않는다. 지정이 없으면 한 번 묻고 skip으로 마친다. 작업이 하나뿐이고 "이어서"면 그 작업을 use한다.
```

세 Hook은 돌 때마다 세션 파일의 `hooks_seen`에 시각을 남긴다(꺼져 있을 때는 남기지 않는다). save·skip·verify가 이것으로 Hook 작동 여부를 보고하므로, 신뢰되지 않았거나 꺼진 Hook은 첫 턴의 결과에서 드러난다. stop-hook은 saved_turn·skipped_turn·selected_turn 중 하나가 turn과 같으면 통과한다. 셋 다 없으면 `{"decision":"block","reason":…}`로 종료를 막는다. stop_hook_active가 참이면 무한 반복 방지를 위해 통과한다. 선택만 해도 Hook은 통과할 수 있으나 지침의 턴 끝 save·읽기 전용 skip 규칙은 유지한다. Pi는 Hook이 없어 지침만 적용하며 강제되지 않는다. Codex Hook 정의가 바뀌면 사용자가 다시 신뢰해야 한다.

## 이전: 형식 1 → 2

형식 1 루트 원장이 남아 있으면 코어 명령은 exit 2와 `형식 1 기록(.worklog/events.jsonl)이 있습니다. tools/migrate_v1_to_v2.py로 먼저 이전하세요.`로 거부한다. hook은 UNAVAILABLE과 이전 안내를 주입한다.

1. `python3 -B tools/migrate_v1_to_v2.py --project <root> --work-id <id> [--title "<제목>"]`로 dry-run한다. 기본 동작은 파일을 쓰지 않는다.
2. 검토 후 같은 명령에 `--apply`를 붙인다. 필수 파일은 `.worklog/events.jsonl`이며 state.json·state.md·writer.json은 있으면 이동한다. works/ 또는 index.json이 있으면 "이미 형식 2"로 거부한다. 이동 대상은 일반 파일이어야 하며 링크·디렉터리면 첫 변경 전에 거부한다. .worklog는 실제 디렉터리여야 하며 sessions가 있으면 실제 디렉터리여야 한다. 같은 조건을 .lock 잠금 안에서 다시 검사하므로 동시 실행의 두 번째 호출도 "이미 형식 2"로 거부한다.
3. 원장 바이트를 변경하지 않고 works/<id>/로 이동한다. 작업별 seq·id·prev 연결은 그대로 유지하며, 연결이 끊긴 원장은 거부한다.
4. index를 만들고 현황을 재계산한다(state.json.format = worklog/2). title 생략 시 작업 id를 제목으로 쓰며, index status는 원장 fold 결과다. 기존 sessions/ 안의 일반 *.json만 버린다. 링크 등은 남기고 `sessions_skipped`에 표시한다. 이전 세션의 턴 카운터는 재사용하지 않는다.
5. 전후 원장의 줄별 해시와 파일 SHA-256을 함께 대조한다(`line_hashes_match`·`hashes_match`). 재실행은 "이미 형식 2"로 거부한다. 도구는 .worklog 밖에 쓰지 않는다.

형식 1 루트 기록을 읽는 코어는 유지하지 않는다.

## 의도적 생략과 한계

- 작업 분할·병합 전용 사건은 없다. 새 작업·CHECKPOINT 메모로 연결한다. 새 작업은 다른 작업의 제약을 이어받지 않으며 `new-work`가 그 사실을 `notice`로 알린다.
- 프로젝트 전체 시간순 원장은 없다. 작업별 해시 체인이며 index.updated_at로 최근 작업을 찾는다.
- 세션↔작업 인계 사건은 없다. 선택은 세션 파일에만 남는다.
- 꺼진 기간(`.worklog/off`)은 원장에 남지 않는다. 켠 뒤 그동안 바뀐 것이 있으면 다음 save에 적는다. 세션·작업 단위 off는 없다.
- 목록은 ACTIVE·PAUSED 최대 10개에 최근 COMPLETED 3개 한 줄이다. 전체 목록은 works로 확인한다.
- Stop Hook은 save·skip의 존재만 확인하고 내용은 보지 않는다. quote가 실제 사용자 발언인지도 도구가 확인하지 못한다. 기록은 모델의 지침 준수에 기대며, Hook과 저장 결과의 표시(self_quoted·warning)는 그것이 어긋났을 때 드러나게 하는 장치다.
- 모델의 질문·선택 준수와 압축 뒤 실제 복원은 별도 대화형 시험이 필요하다. 주입만으로 실제 복원을 입증하지 않는다. 시험 결과와 측정 한계는 `docs/VERIFICATION.md`에 있다.
