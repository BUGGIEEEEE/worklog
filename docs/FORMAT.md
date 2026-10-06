# Worklog 기록 형식 1 (`worklog/1`)

> **English summary.** `worklog/1` is the on-disk format of a project's `.worklog/` folder. `events.jsonl` is an append-only ledger: one JSON event per line, numbered `seq`/`id` from 1, each line chained to the previous one by `prev` = sha256 of the previous line's bytes. A change to an earlier line that later events follow is detected on read; the last event has no independent reference point, so a change to it is not detected. This is not a defense against deliberate tampering. Each event has one of 15 types, a summary, an optional user `quote` (required for user-originated events, setting the goal, and removing constraints) and a `changes` object. `state.json` and `state.md` are projections recomputed from the whole ledger on every save and must not be edited by hand; `show` rebuilds them if they drift. The goal is set once; later changes are decisions that `replace` older ones (`D1..`), and constraints (`C1..`) persist until the user removes them. A save that lists artifacts must include a `check` entry for every active decision and constraint: a verbatim quote (4+ characters) from the artifact body, or `미반영: <reason>` ("not reflected"). Saves are serialized with `flock` and rejected if the session has not read the latest record. Changing the format means re-migrating existing ledgers.

확정일 2026-10-06. 구현: `core/wl.py`. 이 문서와 구현이 다르면 구현을 고치지 말고 먼저 보고한다.

> **형식 변경 = 재이전.** 이 형식(필드 이름·사건 종류·ID 규칙·해시 연결)을 바꾸면 이미 옮긴 기록을 새 형식으로 **다시 이전**해야 한다. 이전 도구·검증도 함께 고친다. 선택 필드 추가처럼 기존 원장의 해석이 그대로인 변경만 같은 형식 번호를 유지한다.

## 파일 (`<프로젝트>/.worklog/`)

| 파일 | 역할 | 쓰는 주체 |
|---|---|---|
| `events.jsonl` | 추가 전용 원장. 한 줄 = 한 사건 | `wl.py save`만 |
| `state.json` | 현재 상태(기계용). 원장에서 매번 다시 계산 | `wl.py` |
| `state.md` | 같은 현재 상태(사람·주입용) | `wl.py` |
| `writer.json` | 마지막 작성자 `{tool, session_id, seq}` (정보용) | `wl.py` |
| `.lock` | 동시 저장 방지(flock) | `wl.py` |
| `sessions/<tool>_<session_id>.json` | 세션 보조 파일 `{last_seen_seq, turn, saved_turn, skipped_turn}`. 원장 아님, 해시 연결·verify 대상 아님 | `wl.py` |

현재 상태 두 파일은 원장의 투영이다. 직접 고치지 않는다. 서로 다르면 원장이 기준이며 `show`가 다시 만든다.

## 사건 (events.jsonl 한 줄)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `v` | ✓ | 형식 1 |
| `seq`, `id` | ✓ | 1부터 연속. `id = E%04d` |
| `prev` | ✓ | 직전 줄 바이트의 sha256(첫 줄 null). 끊기면 읽기 거부. 뒤에 사건이 이어진 과거 줄의 변경은 읽기 때 감지된다. 마지막 사건은 독립적 기준점이 없어 감지 대상이 아니다. 악의적 변조 방지 장치가 아니다 |
| `type` | ✓ | 아래 15종 |
| `at` | ✓ | 기록 시각(UTC) |
| `occurred_at` | | 실제 발생 시각이 기록 시각과 다를 때(이전 사건 등) |
| `tool`, `session_id` | ✓ | 기록한 도구(`codex`/`claude`/`pi`)와 그 세션 ID |
| `summary` | ✓ | 한두 문장 |
| `quote` | 조건부 | 사용자 원문 일부. REQUEST·APPROVAL·D_USER, 목표 설정, 제약 해제, 작성권 인수에 필수 |
| `changes` | ✓ | 상태 변경: `goal`·`decisions`·`constraints`·`constraints_remove`·`waiting`·`next_action`·`status`·`artifacts` |
| `refs` | | 선택 참조. `[{"kind": "block", "id": "B03"}]`. **의미는 미확정**(블록·계획 ID 등 연결용) |
| `source` | | 이전된 사건의 출처: `path`·`line`·`sha256`·원래 종류 |
| `check` | 산출물 시 | 유효 결정·제약마다 산출물 **본문**의 인용(공백 정규화 후 실제로 있어야 함) 또는 `미반영: <이유>`. 미반영 ID는 저장 결과의 `unreflected`에 표시 |
| `writer_acquired` | | 작성권 인수 기록 |

**사건 종류 15종:** REQUEST, APPROVAL, D_USER, D_AGENT, ASSUMPTION, RESULT, VERIFICATION, BLOCKER, CORRECTION, CHECKPOINT, HANDOFF, CHANGE, Q, WRITER_ACQUIRED, WRITER_RELEASED.
- 사용자 출처(원문 필수): REQUEST, APPROVAL, D_USER.
- 제약 해제 가능: D_USER, APPROVAL, CORRECTION.
- 이 목록에 없는 기존 종류는 이전할 때 15종 중 하나로 대응하고, 원래 이름은 `source`에 남긴다.
- **이전 사건:** `tool: "import"`, `session_id`는 이전 실행 ID, `quote`는 null이며 대신 `source`(원본 경로·줄·줄 sha256·원래 종류·원래 ID·원래 기록 시각, 있으면 원래 세션·권위)가 근거다. 원본에 없는 값은 비워 두고 추정하지 않는다. 이전 사건은 상태를 바꾸지 않고, 사용자 확인을 거친 현재 상태 사건 1건만 상태를 정한다. 이전 도구는 이 배포본에 포함하지 않음.
- 0.3.0의 WORK_* 종류는 쓰지 않는다. 한 `.worklog`가 한 작업 흐름이며, 여러 작업은 `refs`로 구분한다.

## 현재 상태 (state.json / state.md)

`format`, `seq`, `goal`(최초 목표 원문, 한 번만), `status`(ACTIVE/PAUSED/BLOCKED/COMPLETED/CANCELLED), `decisions`[유효만: id·text·event·replaces], `constraints`[유효만: id·text·event], `waiting`, `next_action`, `artifacts`[path·sha256·event], `superseded`, `removed_constraints`, `updated_at`, `updated_by`{tool, session_id}.

- **우선순위:** 최초 목표의 값이 바뀌면 유효 결정이 우선한다. `replaces`로 기록된 변경은 충돌이 아니다.
- **제약**은 사용자가 바꾸기 전까지 유지된다. 같은 문장의 재입력은 저장할 때 무시되고, 해제는 사용자 출처 종류에서만 할 수 있다. "다음 요청까지 보류"처럼 요청이 오면 끝나는 것은 `waiting`에 둔다.
- ID: 결정 `D1..`, 제약 `C1..`. 원장 순서로 다시 계산해도 같은 값이 나온다.

## 저장 절차 (`save` 한 번)

잠금 → 원장 읽기·연결 확인 → 신선도 확인 → 입력 검사(check 인용 대조 포함) → 사건 추가(fsync) → 다시 읽어 비교 → 원장 전체로 상태 재계산 → state.json/md 원자적 교체 → 대조. 실패하면 0이 아닌 종료 코드와 사유를 낸다. 사건 추가 뒤 상태 파일만 실패한 경우 원장이 기준이며 `show`가 복원한다.

## 저장 보호 — 잠금 + 신선도

세션 독점은 없다. 어느 도구·세션이든 저장할 수 있되, **그 세션이 마지막으로 본(show·hook·save) 이후 기록이 바뀌었으면 거부**하고 `show` 후 다시 저장하게 한다. 세션 파일이 없는데 기록이 있으면 "show 먼저". 동시 저장은 flock으로 직렬화한다. `takeover`(사유)+`quote`(승인 원문)는 사용자가 명시적으로 넘길 때만 쓰며 `writer_acquired`를 사건에 남긴다. 변경 전 규칙(첫 저장 세션 독점)은 새 세션마다 저장을 막는 공백이 있어 교체했다.

## Hook (`wl.py hook` / `turn-start` / `stop-hook`)

stdin 이벤트의 `cwd`·`session_id`를 쓰고 `--tool <claude|codex>`를 받는다. cwd에 `.worklog/` 디렉터리가 없으면 세 Hook 모두 빈 출력·exit 0.
- `hook`(SessionStart: 시작·재개·압축 후): `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <state.md>}}`. 읽기만 하며 세션 파일 `last_seen_seq`를 갱신한다.
- `turn-start`(UserPromptSubmit): 세션 파일 `turn += 1`.
- `stop-hook`(Stop): 이번 턴에 `save`도 `skip`도 없으면 `{"decision": "block", "reason": ...}`로 턴 종료를 막고 저장을 요구한다. `stop_hook_active`가 참이면 통과(무한 반복 방지).
- `skip "<이유>"`: 읽기 전용 턴을 모델이 선언. 원장에 쓰지 않는다.
Hook이 없는 도구(Pi)는 "턴 시작에 `show` 1회, 턴 끝에 `save`" 지침으로 대신하며 **강제되지 않는다**.
