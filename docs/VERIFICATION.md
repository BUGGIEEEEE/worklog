# Verification / 검증 결과

> **Criterion change (2026-10-09).** From the next run on, criterion 3b is replaced: *no `self_quoted` entry, and every `미반영` entry has a reason*. The old 3b ("no `미반영` at all") rewarded writing the rule text into the artifact and quoting it back, which `wl.py` now reports as `self_quoted`. The results below were measured under the old criterion.
>
> **기준 변경 (2026-10-09).** 다음 시험부터 3b는 "`self_quoted` 0건, 모든 `미반영`에 이유 있음"으로 바꿉니다. 옛 3b("미반영 0건")는 규칙 문장을 산출물에 써 넣고 그대로 인용하는 행동을 보상했고, 이제 `wl.py`가 그것을 `self_quoted`로 표시합니다. 아래 결과는 옛 기준으로 측정한 것입니다.

## Fork-session rule, `reassign --new`, tool-identity refusal, `artifacts_gone` (2.27.0, 2026-10-23, 11 adopted cells across four tools)

2.27.0 ships five update-list items (U16 tool-identity refusal, U12 once-per-session missing notice + `artifacts_gone`, U11 decision reason, U15 `reassign --new`, U14 fork-session rule) plus the fixes from two independent reviews (GPT astra, seven reports; Claude opus as the second reviewer). Unit tests: 166 on Python 3.14.7 and 3.9.6, exit 0. The M harness (`run_m.py`) now distinguishes *unreadable* commands (command substitution, loops, variable heads, stdin interpreters) from rule violations: such items are `unknown` and need a human look instead of being counted as pass or fail; agy and pi never record commands, so their call counts are always `unknown`. Each adopted cell below was judged by a human against the raw calls and the ledger. Full table: [m-20261023-v2270](verification/m-20261023-v2270.md).

| Run | low model | high model | what is judged |
|---|---|---|---|
| M15 fork session, claude | PASS 11.5 s (sonnet 5.5; judge FAIL: the question sat in the message before `skip`) | PASS 12.4 s (opus 5.5) | parent turn saves; the fork answers, asks once at the end, skips; resumed with `recipe 이어서` it uses and saves once |
| M15 fork session, codex | PASS 20.0 s (luna; second run, the first recorded a BLOCKER instead of the content) | PASS 20.5 s (sol 6.1) | same |
| M17 `reassign --new`, claude | PASS 11.7 s (sonnet) | PASS 19.0 s (opus; judge `unknown`: a `$W` variable head) | T1 saves into recipe; T2 one `reassign recipe --new guide`, `[misfiled → guide]`/`[refiled ← recipe]`, texts moved, guide's goal set, current work guide, `verify --all` ok |
| M17 `reassign --new`, codex | PASS 9.5 s (luna; second run, the first skipped the T1 save) | PASS 14.9 s (sol) | same |
| M17 `reassign --new`, agy | PASS 124+132 s (3.8 flash, temporary HOME; judge FAIL: a decision replaced inside T1 was counted as "not moved") | not run (argon: quota exhausted) | same, commands read from the agy transcript |
| M17 `reassign --new`, pi | PASS 14+10 s (luna via proxy) | PASS 27+14 s (sol 6.1) | same, commands read from the pi session file |

Two harness findings are recorded rather than fixed: the judge reads only the last message when looking for the fork question, and it counts decisions replaced within the first turn as unmoved. A test-isolation defect was found and documented: with `--setting-sources project,local`, `claude -p` still reads CLAUDE.md files from ancestor folders, so a test project under `$HOME` picks up the user-level Worklog block (one cell called the 2.26.1 core); the claude cells were re-run from `/private/tmp`.

2.27.0은 갱신 목록 다섯 항목(U16 도구 판정 거부, U12 누락 안내 세션당 1회 + `artifacts_gone`, U11 결정 이유, U15 `reassign --new`, U14 fork 세션 규칙)과 독립 검증 두 계열(GPT astra 보고 7회, Claude opus 2차)의 수정을 담는다. 단위 테스트 166건, Python 3.14.7·3.9.6 exit 0. M 실행기(`run_m.py`)는 이제 *판독 불가* 명령(명령 치환·반복문·변수 머리·stdin 인터프리터)을 규칙 위반과 구분한다. 그런 항목은 `unknown`으로 두고 사람이 보며, 합격·실패로 세지 않는다. agy·pi는 명령을 기록하지 않아 호출 횟수가 항상 `unknown`이다. 아래 채택 셀은 모두 사람이 원 호출과 원장을 대조해 판정했다. 전체 표: [m-20261023-v2270](verification/m-20261023-v2270.md).

| 회차 | 낮은 모델 | 높은 모델 | 판정 내용 |
|---|---|---|---|
| M15 fork 세션, claude | PASS 11.5초 (sonnet 5.5; 판정기 FAIL: 질문이 `skip` 앞 메시지에 있음) | PASS 12.4초 (opus 5.5) | 부모 턴 save; 곁가지는 답하고 끝에 1회 묻고 skip; `recipe 이어서`로 재개하면 use 뒤 save 1회 |
| M15 fork 세션, codex | PASS 20.0초 (luna; 2회차, 1회차는 내용 대신 BLOCKER 기록) | PASS 20.5초 (sol 6.1) | 같음 |
| M17 `reassign --new`, claude | PASS 11.7초 (sonnet) | PASS 19.0초 (opus; 판정기 `unknown`: `$W` 변수 머리) | T1은 recipe에 save; T2는 `reassign recipe --new guide` 1회, `[misfiled → guide]`/`[refiled ← recipe]`, 텍스트 이동, guide goal 설정, 현재 작업 guide, `verify --all` ok |
| M17 `reassign --new`, codex | PASS 9.5초 (luna; 2회차, 1회차는 T1 save 누락) | PASS 14.9초 (sol) | 같음 |
| M17 `reassign --new`, agy | PASS 124+132초 (3.8 flash, 임시 HOME; 판정기 FAIL: T1 안에서 대체된 결정을 "안 옮김"으로 셈) | 미실행 (argon: quota 소진) | 같음, 명령은 agy 대화 기록에서 확인 |
| M17 `reassign --new`, pi | PASS 14+10초 (luna, 프록시) | PASS 27+14초 (sol 6.1) | 같음, 명령은 pi 세션 파일에서 확인 |

실행기 한계 두 가지는 고치지 않고 기록한다: fork 질문을 마지막 메시지에서만 찾는 점, 첫 턴 안에서 대체된 결정을 안 옮긴 것으로 세는 점. 시험 격리 결함도 찾아 기록했다: `--setting-sources project,local`로도 `claude -p`는 조상 폴더의 CLAUDE.md를 읽으므로 `$HOME` 아래 시험 프로젝트는 사용자 수준 Worklog 블록을 함께 읽는다(한 셀은 2.26.1 코어를 호출). claude 셀은 `/private/tmp`에서 다시 돌렸다.

## Reassign order reversal, source-aware dedupe, hooks null, artifacts_moved (2.26.0, 2026-10-21/22, 6 model runs + 2 re-runs)

2.26.0 closes the findings left by the independent review of 2.25.0 (F03–F09) and adds the decisions taken on them. `reassign` now writes the correct work first and refers to the real event id of the other side, resumes from whatever steps are already on disk (refiled → refiled_state → misfiled → misfiled_state → session) and reports a partial run as JSON with exit 2; a 2.25.0 partial whose predicted id turned out wrong gets one correction event (`corrected_ref`), a ledger that cannot be read makes the double-refile check refuse instead of skipping it, and a batch that carries the same text from a model and a user source keeps the user source. The same-turn second `new-work` is refused at turn 0 too, a SessionStart after a prompt or Stop is injected again even inside the 5-second window, the first connected turn's save reports `hooks` as null with a `notice`, `save` accepts `artifacts_moved {old: new}` (whole mapping at once, cycles refused), `SAVE_HELP` got its dropped guidance back (3,100 → 3,426 bytes), and `show` in an unconnected or empty folder uses the same function as the hook. FORMAT states the optional-field policy (readers 2.25.0+, same-day update when the ledger is shared through git, rollback to 2.25.0 or later, 2.26.0 or later once `artifacts_moved` was used); the format number stays worklog/2. Runs are isolated (temporary `WL_HOME`, `--isolate-claude`, `--codex-home`), one per cell, models at their defaults.

| Run | claude | codex | what is judged |
|---|---|---|---|
| M12 empty git project | PASS 23.3 s | PASS 21.6 s | first request → `new-work` with `[auto]` title, E0001, current work set, no question; save result `hooks` null, no "hook not working" claim |
| M14 `auto=off` | PASS 18.7 s | PASS 8.9 s | no `.worklog/`, no event, the request is still answered |
| M16 reassign recipe → memo | PASS 14.8 s | PASS 12.2 s | one `reassign`, `[misfiled → memo]`/`[refiled ← recipe]`, texts moved, current work memo, `verify --all` ok |
| M16 re-run on the fix commit | PASS 14.7 s | PASS 13.7 s | same criteria after 7004e06 |

M16 claude was first judged FAIL because the judge's regex did not accept `--tool claude` between `wl.py` and `reassign`; the regex was fixed and the run re-judged without re-running the model. An independent GPT review of the branch reproduced the 2.25.0 findings and found four closed (F03, F04, F08, F09), three partial (F05 stale reference after a 2.25.0 partial, F06 session step judged by `last_seen` only, F07 user source lost inside one batch) and two new (N01 `artifacts_moved` order-dependent, N02 unreadable ledger skipped); a Gemini second opinion read the code only and reported everything closed, so it was not adopted. All findings were fixed in one commit (7004e06, 145 → 151 unit tests on Python 3.14.7 and 3.9.6) and M16 was re-run: 2/2 PASS. After reinstalling, `show` in an unconnected folder and the hook print the same NOT_CONNECTED line, a `claude -p` turn without Bash was blocked once by the Stop hook (`blocked_turn` 1) and the next Stop passed, `verify --all` is ok. Real-session checks done before this version: pi `--fork` starts a new session with reason `startup` (no `| FORK` header, NO_CURRENT_WORK), agy `/rewind` starts a new conversation (new session id, SessionStart again, files not restored); SessionStart after an agy compaction was not observed. Details: [`docs/verification/m-20261021-v2260.md`](verification/m-20261021-v2260.md).

2.26.0은 2.25.0 독립 검증이 남긴 F03~F09를 닫고 그에 대한 결정을 넣는다. `reassign`은 맞는 작업을 먼저 쓰고 상대 쪽의 실제 사건 번호를 참조하며, 디스크에 있는 단계(refiled → refiled_state → misfiled → misfiled_state → session)에서 이어 가고 부분 실행을 JSON(exit 2)으로 보고한다. 예측 번호가 틀린 2.25.0 partial은 정정 사건 하나(`corrected_ref`)를 더 남기고, 읽을 수 없는 원장이 있으면 이중 이관 검사가 건너뛰지 않고 거부하며, 같은 문장이 model·user 출처로 함께 들어오면 user 출처를 남긴다. 같은 턴 두 번째 `new-work`는 턴 0에서도 거부, 프롬프트·Stop 뒤 SessionStart는 5초 안이라도 다시 주입, 첫 연결 턴 save 결과의 `hooks`는 null + `notice`, `save`에 `artifacts_moved {옛: 새}`(매핑 전체를 한 번에, 순환 거부), `SAVE_HELP`는 빠졌던 안내를 복원(3,100→3,426바이트), 미연결·빈 폴더의 `show`는 Hook과 같은 함수를 쓴다. FORMAT에 선택 필드 정책(2.25.0 이상 reader, git 공유 원장은 같은 날 갱신, rollback은 2.25.0 이상·`artifacts_moved`를 썼으면 2.26.0 이상)을 적었고 형식 번호는 worklog/2 그대로다. 격리 실행(임시 `WL_HOME`, `--isolate-claude`, `--codex-home`), 셀당 1회, 모델 기본값.

| 회차 | claude | codex | 판정 내용 |
|---|---|---|---|
| M12 빈 git 프로젝트 | PASS 23.3초 | PASS 21.6초 | 첫 요청 → `[auto]` 제목으로 `new-work`, E0001, 현재 작업 설정, 질문 없음. save 결과 `hooks` null, "Hook 미작동" 언급 없음 |
| M14 `auto=off` | PASS 18.7초 | PASS 8.9초 | `.worklog/` 없음, 사건 없음, 요청에는 답함 |
| M16 reassign recipe → memo | PASS 14.8초 | PASS 12.2초 | `reassign` 1회, `[misfiled → memo]`/`[refiled ← recipe]`, 텍스트 이동, 현재 작업 memo, `verify --all` ok |
| M16 수정 커밋 재실행 | PASS 14.7초 | PASS 13.7초 | 7004e06 뒤 같은 기준 |

M16 claude는 판정기 정규식이 `wl.py`와 `reassign` 사이의 `--tool claude`를 받지 않아 처음 FAIL이었고, 정규식을 고친 뒤 모델 재실행 없이 재판정했다. 브랜치의 독립 GPT 검토는 2.25.0 지적을 재현해 닫힘 4(F03·F04·F08·F09)·부분 3(F05 2.25.0 partial 뒤 옛 참조, F06 session 단계를 `last_seen`으로만 판정, F07 한 묶음 안의 user 출처 손실)·새 결함 2(N01 `artifacts_moved` 순서 의존, N02 읽을 수 없는 원장 건너뜀)를 냈고, Gemini 2차는 코드만 읽고 전부 닫힘이라 해 채택하지 않았다. 지적 전부를 한 커밋(7004e06, 단위 테스트 145→151개, Python 3.14.7·3.9.6)으로 고치고 M16을 다시 돌려 2/2 PASS. 재설치 뒤 미연결 폴더의 `show`와 Hook이 같은 NOT_CONNECTED 줄을 내고, Bash 없는 `claude -p` 턴은 Stop 훅에 한 번 막히고(`blocked_turn` 1) 다음 Stop이 통과했으며, `verify --all`은 ok. 이 버전 전에 한 실세션 확인: pi `--fork`는 reason `startup`의 새 세션(`| FORK` 헤더 없음, NO_CURRENT_WORK), agy `/rewind`는 새 대화(새 세션 id, SessionStart 재발화, 파일 미복원). agy 압축 뒤 SessionStart는 관찰하지 못했다. 상세: [`docs/verification/m-20261021-v2260.md`](verification/m-20261021-v2260.md).

## Automatic connection v2, reassign/rename (2.25.0, 2026-10-20/21, 10 model runs + 4 re-runs)

2.25.0 lets a plain request start the record: a hook in a folder without records reports `NOT_CONNECTED | root= | auto= | git=` and, with `auto` on (the default), the model's first request worth recording runs `new-work` with an `[auto]` title; in a folder that already has works the model asks once which work to use and never picks one itself. Records go to the git top level or the nearest folder with `.worklog/index.json` inside it; `~/.worklog` (`WL_HOME`) is never auto-connected. `reassign` corrects a save that went to the wrong work (two CORRECTION events, the ledger lines stay), `rename` changes a title. The rule block gained one NOT_CONNECTED item, the work-decision rule and four items; the other 14 lines are byte-identical, and the stage-1 dedup of `SAVE_HELP` cut it from 6,206 to 3,100 bytes (installed Claude block 15,132 → 13,297). Runs are isolated (temporary `WL_HOME`, `--isolate-claude`, `--codex-home`), one per cell, models at their defaults.

| Run | claude | codex | what is judged |
|---|---|---|---|
| M12 empty git project | PASS 15.2 s | PASS 24.5 s | first request → `new-work` with `[auto]` title (`readme`), E0001, current work set, no question |
| M13 two works → "memo 이어서" | PASS 20.0 s | PASS 22.4 s | T1 lists both works, asks once, saves nothing; T2 `use memo`, quote carries the T1 request |
| M13b two works → "새 작업으로" | PASS 16.3 s | PASS 21.1 s | T2 `new-work` "다음 주 회의 안건" with `[auto]` |
| M14 `auto=off` | PASS 6.2 s | PASS 10.4 s | no `.worklog/`, no event, the request is still answered |
| M16 reassign recipe → memo | PASS 19.7 s | PASS 19.2 s | one `reassign`, `[misfiled → memo]`/`[refiled ← recipe]`, texts moved, current work memo, `verify --all` ok |

Both M16 cells were first judged FAIL by two judge mistakes (the word "reassign" in a skip reason counted as a call; a turn-end CORRECTION save after reassign counted as a manual correction) and re-judged after the judge was fixed. Two independent reviews of the branch (GPT: 11 findings; Gemini: 4, its code description largely inaccurate) led to six small fixes before merge (`WL_HOME` never auto-connected, explicit `--root` wins in hooks, an already refiled event is not reassigned again, config written before the manifest, test env, stale wording); M12/M14 re-run on the fixed commit: 4/4 PASS (12.9/17.9 s, 11.2/9.4 s). After reinstalling, a `claude -p` turn without Bash was blocked once by the Stop hook (`blocked_turn` 1) and the next Stop passed; an agy plan-mode turn ran `skip` and was not blocked. M15 (fork) is covered by unit tests only; agy and pi were not run. Details: [`docs/verification/m-20261020-v2250.md`](verification/m-20261020-v2250.md).

2.25.0은 일반 요청으로 기록을 시작하게 한다. 기록이 없는 폴더의 훅은 `NOT_CONNECTED | root= | auto= | git=`을 알리고, `auto`가 on(기본)이면 모델은 기록할 가치가 있는 첫 요청에서 `[auto]` 제목으로 `new-work`를 실행한다. 작업이 이미 있는 폴더에서는 어느 작업에 기록할지 한 번 묻고, 모델이 대신 고르지는 않는다. 기록 위치는 git 최상위 또는 그 안에서 `.worklog/index.json`이 있는 가장 가까운 폴더이며 `~/.worklog`(`WL_HOME`)는 자동 연결하지 않는다. `reassign`은 잘못된 작업에 들어간 저장을 정정하고(CORRECTION 사건 둘, 원장 줄은 그대로), `rename`은 제목을 바꾼다. 규칙 블록에는 NOT_CONNECTED 항목·작업 결정 규칙·새 항목 4개가 들어갔고 나머지 14줄은 바이트 동일, `SAVE_HELP` 1단계 중복 제거로 6,206→3,100바이트(설치된 Claude 블록 15,132→13,297). 격리 실행(임시 `WL_HOME`, `--isolate-claude`, `--codex-home`), 셀당 1회, 모델 기본값.

| 회차 | claude | codex | 판정 내용 |
|---|---|---|---|
| M12 빈 git 프로젝트 | PASS 15.2초 | PASS 24.5초 | 첫 요청 → `[auto]` 제목으로 `new-work`(`readme`), E0001, 현재 작업 설정, 질문 없음 |
| M13 두 작업 → "memo 이어서" | PASS 20.0초 | PASS 22.4초 | T1은 두 작업을 보이고 한 번 묻고 저장 없음, T2 `use memo`, quote에 T1 요청 |
| M13b 두 작업 → "새 작업으로" | PASS 16.3초 | PASS 21.1초 | T2 `new-work` "다음 주 회의 안건", `[auto]` |
| M14 `auto=off` | PASS 6.2초 | PASS 10.4초 | `.worklog/` 없음, 사건 없음, 요청에는 답함 |
| M16 reassign recipe → memo | PASS 19.7초 | PASS 19.2초 | `reassign` 1회, `[misfiled → memo]`/`[refiled ← recipe]`, 텍스트 이동, 현재 작업 memo, `verify --all` ok |

M16 두 셀은 판정기 오류 둘(skip 사유의 "reassign" 단어를 호출로 셈, reassign 뒤 턴 끝 CORRECTION save를 수동 정정으로 셈)로 처음 FAIL이었고 판정기를 고친 뒤 재판정했다. 브랜치의 독립 검토 둘(GPT 11건, Gemini 4건 — 코드 서술 상당수 부정확)로 병합 전 작은 수정 6건(`WL_HOME` 비자동연결, Hook에서 명시 `--root` 우선, 이미 옮긴 사건 재이관 거부, config를 manifest보다 먼저, 테스트 환경, 옛 문구)을 넣었고, 고친 커밋으로 M12·M14를 다시 돌려 4/4 PASS(12.9/17.9초, 11.2/9.4초). 재설치 뒤 Bash 없는 `claude -p` 턴은 Stop 훅에 한 번 막히고(`blocked_turn` 1) 다음 Stop이 통과했다. agy plan 모드 턴은 `skip`을 실행해 막히지 않았다. M15(fork)는 단위 테스트만, agy·pi는 돌리지 않았다. 상세: [`docs/verification/m-20261020-v2250.md`](verification/m-20261020-v2250.md).

## agy and pi support (2.24.0, 2026-10-20, 4 model runs)

2.24.0 installs the same rules, three hook points and skill for **agy** (Antigravity CLI: its own always-on rule file, a named hook in `hooks.json`, `PreInvocation` counted as a turn only at `invocationNum` 0, Stop answered with `{"decision": "continue"}`) and **pi** (an extension that calls the core on `session_start`, `before_agent_start` and `agent_before_settle` and sets `PI_SESSION_ID`). One run each of M2 (new work from an empty `.worklog/`) and M3 (two artifacts with check) per tool, project-level install of that tool only from the release branch, `WL_HOME` isolated. agy ran `agy -p --mode auto` with its default model; pi had no credentials on this machine, so it ran with an isolated agent dir (`PI_CODING_AGENT_DIR`) whose `models.json` points at a local OpenAI-compatible proxy (`gpt-6-astra`), `-a` trusting the project extension. Judged mechanically as in the earlier M layer.

| Run | result | hooks recorded | s |
|---|---|---|---|
| M2 agy | PASS | SessionStart·UserPromptSubmit·Stop | 132.8 |
| M3 agy | PASS | all three | 113.6 |
| M2 pi | PASS | all three | 28.8 |
| M3 pi | PASS | all three | 64.3 |

In every run the model's own `save` landed in the session the hooks had created (hooks all true, no warning), which is the point of the session-id paths (`ANTIGRAVITY_CONVERSATION_ID`; the extension's `PI_SESSION_ID`). The Stop-block path was not exercised (every run saved); it is covered by unit tests. One run per cell; the user-level files and agy's 20,000-token rules budget were checked only after the merge on this machine. Details: [`docs/verification/m-20261020-v2240.md`](verification/m-20261020-v2240.md).

**2.24.1 and 2.24.2 (same day, agy only).** Re-running M2/M3 on agy with `gemini-3.8-flash-medium` exposed a Stop-block loop (M2 7+ minutes). 2.24.1 blamed `invocationNum` resetting per tool call; that reading was wrong (it increases 0, 1, 2). The real cause was the Worklog hook registered twice — the test project's `.agents/hooks.json` plus the user-level `~/.gemini/config/hooks.json` installed that evening — so agy delivered every event twice and the second Stop blocked the turn the first one had just advanced. 2.24.2 makes a repeated delivery a no-op (the session remembers the last PreInvocation and Stop). Verified with both registrations loaded (agy log: `loaded 2 named hooks from 2 hooks.json file(s)`), both calling 2.24.2:

| Run | core (project hook / user hook) | M2 | M3 | session turn·saved·skipped·blocked | transcript |
|---|---|---|---|---|---|
| r2 | 2.24.1 / 2.24.1 | PASS 232.6 s | PASS 540.4 s | 20·18·19·18, 35·3·35·34 | injected twice, repeated blocks |
| r3 | 2.24.2 / 2.24.1 | aborted (turn 33, blocked 31) | — | — | invalid: mixed cores |
| r4 | 2.24.2 / 2.24.2 | PASS 23.3 s | PASS 60.6 s | 2·1·0·0, 2·1·0·0 | injected once, no block |

A live plan-mode turn after reinstalling (project hook + the real user hook, both 2.24.2) blocked exactly once (`blocked_turn` 1), the model skipped, the next Stop passed.

2.24.0은 **agy**(Antigravity CLI: 전용 always-on 규칙 파일, `hooks.json`의 이름 붙은 훅, `PreInvocation`은 `invocationNum` 0에서만 턴으로 셈, Stop은 `{"decision": "continue"}`로 차단)와 **pi**(`session_start`·`before_agent_start`·`agent_before_settle`에서 코어를 부르고 `PI_SESSION_ID`를 설정하는 확장)에 같은 규칙·훅 지점 3개·스킬을 설치한다. 도구마다 M2(빈 `.worklog/`에서 새 작업)·M3(산출물 2개·check) 각 1회, release 브랜치로 그 도구만 프로젝트 설치, `WL_HOME` 격리. agy는 `agy -p --mode auto` 기본 모델, pi는 이 기기에 인증이 없어 격리 에이전트 폴더(`PI_CODING_AGENT_DIR`)의 `models.json`으로 로컬 OpenAI 호환 프록시(`gpt-6-astra`)를 쓰고 `-a`로 프로젝트 확장을 신뢰. 판정은 기존 M층과 같다.

| 회차 | 판정 | 기록된 훅 | 초 |
|---|---|---|---|
| M2 agy | PASS | SessionStart·UserPromptSubmit·Stop | 132.8 |
| M3 agy | PASS | 셋 모두 | 113.6 |
| M2 pi | PASS | 셋 모두 | 28.8 |
| M3 pi | PASS | 셋 모두 | 64.3 |

모든 회차에서 모델의 `save`가 훅이 만든 세션에 기록됐다(hooks 모두 true, 경고 없음). 이것이 세션 id 경로(`ANTIGRAVITY_CONVERSATION_ID`, 확장의 `PI_SESSION_ID`)의 확인이다. Stop 차단 경로는 타지 않았고(모두 save함) 단위 테스트로 확인한다. 셀당 1회이며, 사용자 수준 파일과 agy의 20,000토큰 규칙 예산은 병합 뒤 이 기기에서만 확인했다. 상세: [`docs/verification/m-20261020-v2240.md`](verification/m-20261020-v2240.md).

**2.24.1·2.24.2(같은 날, agy만).** agy를 `gemini-3.8-flash-medium`으로 M2·M3를 다시 돌리자 Stop 차단 루프가 드러났다(M2 7분 초과). 2.24.1은 원인을 도구 호출마다 `invocationNum`이 0으로 돌아오는 것으로 적었으나 그 해석은 틀렸다(0·1·2로 증가). 진짜 원인은 Worklog 훅의 중복 등록 — 시험 프로젝트의 `.agents/hooks.json`과 그날 저녁 설치한 사용자 수준 `~/.gemini/config/hooks.json` — 으로, agy가 모든 이벤트를 두 번 보내 첫 Stop이 올린 턴을 두 번째 Stop이 막았다. 2.24.2는 같은 이벤트의 재전달을 무동작으로 만든다(세션이 마지막 PreInvocation·Stop을 기억). 두 등록이 모두 로드된 조건(agy 로그 `loaded 2 named hooks from 2 hooks.json file(s)`)에서 양쪽이 2.24.2를 부르게 하여 확인했다:

| 회차 | 코어(프로젝트 훅 / 사용자 훅) | M2 | M3 | 세션 turn·saved·skipped·blocked | 전사 |
|---|---|---|---|---|---|
| r2 | 2.24.1 / 2.24.1 | PASS 232.6초 | PASS 540.4초 | 20·18·19·18, 35·3·35·34 | 주입 2회, 차단 반복 |
| r3 | 2.24.2 / 2.24.1 | 중단(turn 33, blocked 31) | — | — | 무효: 코어 혼재 |
| r4 | 2.24.2 / 2.24.2 | PASS 23.3초 | PASS 60.6초 | 2·1·0·0, 2·1·0·0 | 주입 1회, 차단 없음 |

재설치 뒤 실세션 plan 모드 턴(프로젝트 훅 + 실제 사용자 훅, 둘 다 2.24.2)은 정확히 한 번 막히고(`blocked_turn` 1) 모델이 skip한 뒤 다음 Stop이 통과했다.

## 2.23.0 rule bundle — `[behavior]`, `[delegated:]`, project.md suggestion, `Map:`, unseen events (2026-10-20, 4 model runs)

2.23.0 changes five rule sentences and two projections: a correction of how the model works starts with `[behavior]` and carries the user's words (type CORRECTION when it only records the correction, D_USER when it also adds a lasting constraint or decision); the delegation tag is `[delegated: …]` and adoption cites the sub-session's event ids; a separate session is opened in the work root with the same first line whatever the channel; `project.md` is suggested once (only when a work is set to COMPLETED or the user says "앞으로 이 프로젝트에서는 …") and never written before the user says so; a "look here first" decision is prefixed `Map:` and `state.md` shows such decisions in a `## 안내` section; `show`, `use` and the injection append the events this session has not seen yet. Two-turn runs per tool (M11: `claude -p` + `--resume`, `codex exec` + `resume`, default models) in a project installed from the release branch with a seeded work, a sub-session's saved draft (E0002) and a `docs/tone.md`. Turn 1 asks to review and record the sub-session's file and adds "앞으로 이 프로젝트에서는 … docs/tone.md … 먼저 봐"; turn 2 corrects how the model reports ("결론부터 … 네가 일하는 방식을 바로잡는 거야"). The user-level rules of this machine were kept out (Claude `--setting-sources project,local`, Codex a scratch `CODEX_HOME`). Judged mechanically before each run: a `[delegated:` summary citing E0002 and no `[위임`; a new decision starting with `Map:` and the `## 안내` section in `state.md`; exactly one "넣을까" with `project.md` in the answers and no `.worklog/project.md`; a `[behavior]` event whose quote is in the prompt, whose constraints have the user source, saved once in turn 2.

| Run | delegated (cites E0002) | Map: / section | suggested once / not written | [behavior]+quote | constraint source user / one save | machine | s (T1/T2) | cost |
|---|---|---|---|---|---|---|---|---|
| Claude r1 (before F1·R2) | PASS (—) | PASS / PASS | 1 / PASS | PASS (CORRECTION) | FAIL / FAIL (re-saved as D_USER) | PASS* | 24.4 / 18.1 | $1.35 |
| Codex r1 (before F1·R2) | PASS (—) | PASS / PASS | 1 / PASS | PASS (CORRECTION) | FAIL / FAIL (re-saved as D_USER) | PASS* | 33.6 / 22.4 | — |
| Claude r2 | PASS (PASS) | PASS / PASS | **2** / PASS | PASS (D_USER) | PASS / PASS | FAIL | 35.0 / 19.9 | $1.40 |
| Codex r2 | PASS (PASS) | PASS / PASS | 1 / PASS | PASS (D_USER) | PASS / PASS | PASS | 34.4 / 12.6 | — |

\* r1 ran before the source/one-save criteria existed. r1 found F1: both models put the lasting constraint into the `[behavior]` CORRECTION, got the `[모델]` source and re-saved it as D_USER in the same turn (two saves). The F1 sentence fixed it in r2: both saved once as D_USER with the `[사용자]` source. Both r2 runs cited E0002 in the adoption summary after seeing it in the unseen-events section of `use`. Claude r2's machine FAIL is the suggestion count: it suggested once in turn 1 and then, at the end of turn 2, re-listed its two unanswered questions ("… project.md에 넣을까요?"); by hand that is one suggestion and no write, and the "넣을까" counter cannot tell a reminder from a new suggestion. One run per cell per round; the user-level install files were verified only after the merge. Details: [`verification/m-20261017-v2230.md`](verification/m-20261017-v2230.md).

2.23.0은 규칙 다섯 문장과 투영 둘을 바꾼다: 모델의 일하는 방식을 바로잡는 교정은 `[behavior]`로 시작하고 사용자 원문을 담는다(교정만이면 CORRECTION, 지속 제약·결정도 넣으면 D_USER), 위임 표식은 `[delegated: …]`이고 채택은 하위 세션의 사건 id를 인용한다, 별도 세션은 통로와 무관하게 작업 루트에서 같은 첫 줄로 연다, `project.md`는 (작업을 COMPLETED로 바꾸는 턴이나 "앞으로 이 프로젝트에서는 …" 발언 턴에만) 한 번 권유하고 "넣어" 전에는 쓰지 않는다, "무엇을 먼저 보라"는 결정은 `Map:` 접두를 붙이며 `state.md`가 그 결정을 `## 안내` 절에 보인다, `show`·`use`·주입이 이 세션이 못 본 사건을 붙인다. 도구마다 두 턴 실행(M11: `claude -p` + `--resume`, `codex exec` + `resume`, 기본 모델). 시험 폴더는 release 브랜치로 설치, 시드는 작업 하나 + 하위 세션이 저장한 초안(E0002) + `docs/tone.md`. 1턴은 하위 세션 파일의 검토·기록 요청에 "앞으로 이 프로젝트에서는 … docs/tone.md … 먼저 봐"를 더했고, 2턴은 보고 방식을 바로잡는다("결론부터 … 네가 일하는 방식을 바로잡는 거야"). 이 기기의 사용자 수준 규칙은 제외했다(Claude `--setting-sources project,local`, Codex 임시 `CODEX_HOME`). 판정은 실행 전 고정: E0002를 인용하는 `[delegated:` summary와 `[위임` 없음, `Map:`으로 시작하는 새 결정과 `state.md`의 `## 안내` 절, 답변의 "넣을까" 정확히 1회 + `project.md` 언급 + `.worklog/project.md` 없음, quote가 프롬프트에 있고 제약 출처가 사용자이며 2턴에 한 번만 저장된 `[behavior]` 사건.

| 회차 | delegated(E0002 인용) | Map: / 절 | 권유 1회 / 미작성 | [behavior]+quote | 제약 출처 user / save 1회 | 기계 | 초(T1/T2) | 비용 |
|---|---|---|---|---|---|---|---|---|
| Claude r1(F1·R2 전) | PASS (—) | PASS / PASS | 1 / PASS | PASS (CORRECTION) | FAIL / FAIL (D_USER로 재저장) | PASS* | 24.4 / 18.1 | $1.35 |
| Codex r1(F1·R2 전) | PASS (—) | PASS / PASS | 1 / PASS | PASS (CORRECTION) | FAIL / FAIL (D_USER로 재저장) | PASS* | 33.6 / 22.4 | — |
| Claude r2 | PASS (PASS) | PASS / PASS | **2** / PASS | PASS (D_USER) | PASS / PASS | FAIL | 35.0 / 19.9 | $1.40 |
| Codex r2 | PASS (PASS) | PASS / PASS | 1 / PASS | PASS (D_USER) | PASS / PASS | PASS | 34.4 / 12.6 | — |

\* r1은 출처·save 1회 기준이 생기기 전이다. r1에서 F1을 발견했다: 두 모델 모두 지속 제약을 `[behavior]` CORRECTION에 넣어 `[모델]` 출처가 됐고 같은 턴에 D_USER로 다시 저장했다(save 2회). F1 문장이 r2에서 이를 해소했다: 둘 다 D_USER 한 번으로 `[사용자]` 출처. r2 두 회차 모두 `use` 출력의 못 본 사건 절에서 E0002를 보고 채택 summary에 인용했다. Claude r2의 기계 FAIL은 권유 횟수다: 1턴에 한 번 권유한 뒤 2턴 끝에서 미답 질문 둘을 다시 나열했다("… project.md에 넣을까요?"). 사람 검토로는 권유 1회·미작성이며, "넣을까" 글자 수 세기는 재언급과 새 권유를 구분하지 못한다. 회차마다 셀당 1회이며, 사용자 수준 설치 파일은 병합 뒤에만 확인했다. 상세: [`verification/m-20261017-v2230.md`](verification/m-20261017-v2230.md).

## Tool-level install and connect-on-first-new-work (2.21.0, 2026-10-16, 4 model runs)

Since 2.21.0 the rules and hooks are installed once per machine (`--user`) and a folder is connected by its first `새 작업:`; elsewhere the SessionStart hook injects one `NOT_CONNECTED` line. Three-turn runs (`claude -p` with `--resume`, then a new session; `codex exec` with `resume`, then a new session; default models) in an empty git project that had the 2.21.0 rules and hooks but no `.worklog/` (`--root … --no-worklog-dir`, the same files a `--user` install provides; the user-level files themselves were not touched before the merge, and Codex ran with `--dangerously-bypass-hook-trust`). Judged mechanically before the run: turn 1 (an ordinary question) passes with zero `wl.py` calls, no work question, no `.worklog/` created; turn 2 (`새 작업: 시험 plan` plus a small file) passes with a `new-work` call, `index.json`, the `.worklog/` line in `.gitignore`, the registry entry, `install.json` with scope `user` and at least one saved event; turn 3 (`plan 이어서` in a new session) passes with a `use` call and one more event.

| Cell | Result |
|---|---|
| Claude Code, draft core | PASS 3/3 (the model itself reported two defects, below) |
| Codex, draft core | PASS 3/3 (same two defects reported) |
| Claude Code, fixed core | PASS 3/3, no spurious warning or notice |
| Codex, fixed core | PASS 3/3, no spurious warning or notice |

The two defects found by the first runs and fixed before release: the parent-folder notice of `new-work` mistook `~/.worklog` (the state folder) for a parent record (now only a parent with works counts); the save of the connecting turn carried a false "Hook 미작동 의심" warning, because the hooks of that session ran before there was a session file to mark (the connecting session is now exempt). The NOT_CONNECTED injection was seen in both tools' transcripts. After the merge, on the development machine: the user-level hooks fired in a real Claude Code session and a real Codex session in the connected project (all three recorded, no warning), a folder without `.worklog/` got the single line, and `$worklog` listed the user-level Codex skill. One or two runs per cell: weak evidence of reproducibility. Details: worklog-control `runs/m-20261016-user/RESULTS.md`.

2.21.0부터 규칙·Hook은 기기에 한 번(`--user`) 설치하고, 폴더는 첫 `새 작업:`이 연결하며, 그 밖의 폴더에서는 SessionStart가 `NOT_CONNECTED` 한 줄만 주입한다. 2.21.0 규칙·Hook만 있고 `.worklog/`는 없는 빈 git 프로젝트(`--root … --no-worklog-dir`, `--user` 설치와 같은 파일 구성; 병합 전이라 사용자 수준 파일은 건드리지 않았고 Codex는 `--dangerously-bypass-hook-trust`로 실행)에서 세 턴 실행(`claude -p` + `--resume` 뒤 새 세션, `codex exec` + resume 뒤 새 세션, 기본 모델). 판정은 실행 전 고정: 1턴(일반 질문)은 `wl.py` 호출 0·작업 질문 0·`.worklog/` 없음, 2턴(`새 작업: 시험 plan` + 작은 파일)은 `new-work` 호출·`index.json`·`.gitignore`의 `.worklog/` 줄·registry·scope `user`의 `install.json`·사건 1건 이상, 3턴(새 세션에서 `plan 이어서`)은 `use` 호출과 사건 1건 추가.

| 셀 | 결과 |
|---|---|
| Claude Code, 초안 코어 | PASS 3/3 (모델이 아래 결함 2건을 스스로 보고) |
| Codex, 초안 코어 | PASS 3/3 (같은 결함 2건 보고) |
| Claude Code, 수정 코어 | PASS 3/3, 거짓 경고·안내 없음 |
| Codex, 수정 코어 | PASS 3/3, 거짓 경고·안내 없음 |

첫 회차가 찾아 배포 전에 고친 결함 2건: `new-work`의 상위 폴더 안내가 `~/.worklog`(상태 폴더)를 상위 기록으로 오인(지금은 작업이 있는 상위만), 연결한 턴의 save에 거짓 "Hook 미작동 의심" 경고(그 세션의 Hook은 세션 파일이 생기기 전에 돌았기 때문; 연결한 세션은 제외). NOT_CONNECTED 주입은 두 도구의 전사에서 확인했다. 병합 뒤 개발 기기에서: 연결된 프로젝트의 실제 Claude Code·Codex 세션에서 사용자 수준 Hook 3개가 모두 기록되고 경고 없음, `.worklog/` 없는 폴더는 한 줄만, `$worklog`에 사용자 수준 Codex 스킬이 뜸. 셀당 1~2회라 재현성 증거는 약하다. 상세: worklog-control `runs/m-20261016-user/RESULTS.md`.

## Ask-before-install / ask-before-uninstall (2.19.0–2.20.1, 2026-10-15, 7 model runs)

Since 2.19.0 the installer and uninstaller refuse to guess which tools the user means, and AGENT.md tells the agent to ask first. Two-turn runs (`claude -p` with `--resume`, `codex exec` with resume) in an empty git project, default models, judged mechanically before the run: turn 1 passes when no real install/uninstall ran (dry-run and `--help` allowed) and the answer ends with the question; turn 2 passes when the answer ("both" / "Claude only" / "codex only") is carried out exactly.

| Cell | Result |
|---|---|
| Install, Claude Code asks about Codex → "both" | PASS (2.19.0) |
| Install, Claude Code → "Claude only": claude only, no `AGENTS.md`, no `.codex/` | PASS (2.19.0) |
| Install, Codex asks about Claude Code → "both" | FAIL (2.19.0: installed codex without asking; also the `codex exec` workspace-write sandbox blocked `.codex/` and `.agents/` writes) → PASS (2.20.1, no sandbox) |
| Uninstall, Claude Code with both tools installed → "codex only" | FAIL (2.19.0: ran `--tool all --keep-records` without asking) → PASS (2.20.1: asked which tool and about the records, then removed codex only, kept the Claude block and the records) |

Both first-attempt failures had the same cause: the agent read `--help` and the README but not AGENT.md. 2.20.0 therefore puts the ask-first instruction at the top of both scripts' `--help`; the reruns read AGENT.md as well. The uninstall run's agent also found a real bug (with two tools installed, `--tool all --keep-records` left `install.json` holding the second tool's entry), fixed in 2.20.0 with a regression test. Not fixed then: an OS error in the middle of the installer's writes left the files written so far (fixed in 2.22.0: rolled back). One or two runs per cell: weak evidence of reproducibility. Details: worklog-control `runs/m-20261015-install/RESULTS.md`.

2.19.0부터 설치기·제거기는 대상 도구를 추측하지 않고, AGENT.md는 에이전트에게 먼저 물으라고 한다. 빈 git 프로젝트에서 두 턴 실행(`claude -p` + `--resume`, `codex exec` + resume, 기본 모델), 판정은 실행 전 고정: 1턴은 실제 설치·제거 0회(dry-run·`--help` 허용)에 질문으로 끝나면 통과, 2턴은 답("둘 다" / "Claude만" / "codex만")을 정확히 수행하면 통과.

| 셀 | 결과 |
|---|---|
| 설치, Claude Code가 Codex를 묻고 → "둘 다" | PASS (2.19.0) |
| 설치, Claude Code → "Claude만": claude만, `AGENTS.md`·`.codex/` 없음 | PASS (2.19.0) |
| 설치, Codex가 Claude Code를 묻고 → "둘 다" | FAIL (2.19.0: 묻지 않고 codex 설치; `codex exec` workspace-write 샌드박스가 `.codex/`·`.agents/` 쓰기를 막기도 함) → PASS (2.20.1, 샌드박스 없음) |
| 제거, 두 도구가 설치된 프로젝트에서 Claude Code → "codex만" | FAIL (2.19.0: 묻지 않고 `--tool all --keep-records` 실행) → PASS (2.20.1: 도구와 기록을 묻고, codex만 제거, Claude 블록·기록 유지) |

첫 시도 FAIL 두 건의 원인은 같다: 에이전트가 `--help`와 README는 읽고 AGENT.md는 읽지 않았다. 그래서 2.20.0은 두 스크립트의 `--help` 첫머리에 "먼저 물어라"를 넣었고, 재시험에서는 AGENT.md도 읽었다. 제거 회차의 에이전트는 실제 버그도 찾았다(두 도구 설치 + `--tool all --keep-records` → `install.json`에 둘째 도구 항목이 남음). 2.20.0에서 수정, 회귀 테스트 추가. 당시 미수정: 설치기가 쓰는 도중 OS 오류가 나면 앞서 쓴 파일이 남았다(2.22.0에서 되돌리도록 수정). 셀당 1~2회라 재현성 증거는 약하다. 상세: worklog-control `runs/m-20261015-install/RESULTS.md`.

## Rewind · branch · worktree (2.12.0–2.13.0, 2026-10-13, Claude Code, 1 real session)

Measured by hand in the real project (test work archived afterwards): `/branch` → new session id, SessionStart injected once the installer matcher includes `fork` (2.12.0). `/rewind` conversation restore → same id, no rewind marker reaches the model, the model re-saved the turn without `show` → one duplicate event (decisions deduplicated by the core) → 2.13.0 refuses a same-session same-summary re-save. `/rewind` code restore → file gone, ledger unchanged, not reported (documented, no core change). git worktree → two ledgers, merge conflicts in events.jsonl/state.md/writer.json → 2.13.0 `warning_worktree`. `/btw`→`f` fork → saved under the main id with self-awareness, main skipped. Concurrent save → refused, `show`, re-saved. Measured later (2026-10-14): rewind-menu "Summarize from here" keeps the session id and fires SessionStart(compact), so the record is injected and the model answered the work and decisions from it (note: the prompt at the rewind point is put back into the composer); Codex interactive `resume` fires SessionStart(resume) at the first prompt; `$worklog` injects the skill body (Codex rollout shows `<skill><name>worklog</name>`); the model relayed the 2.13.0 worktree warning to the user in one run (PASS 1/1). Evidence: [`verification/checks-20261014.md`](verification/checks-20261014.md).

**Codex (2026-10-14, codex-cli 0.158.0, trusted trial root, a logging SessionStart hook without matcher beside the installed one).** `/fork` → new thread, `source: fork`, installed hook did not run; `/new` → new thread, `startup`, ran; `/clear` → new thread, `clear`, did not run; `/side` → new thread with tools, `fork`, did not run (UserPromptSubmit·Stop did). Codex fires SessionStart at the new thread's first prompt. → 2.14.0 adds `clear`·`fork` to the Codex matcher. Evidence: `shared/runs/codex-fork-20261014/`.

**Follow-up to ② (2.15.0).** Artifacts recorded by the current session whose file is gone are reported in show/use/injection and save/skip results; `verify` compares every artifact's existence and hash. One model run (M10, Claude opus, 2026-10-14): the file was deleted after the model's own artifact save, the session resumed, and the next save result carried `artifacts_missing`; the model checked the folder, told the user the recorded file was gone, recorded a waiting item and asked whether to recreate it — PASS 1/1 (one run, not "always"). Script and evidence: [`verification/m-20261014-v2150.md`](verification/m-20261014-v2150.md).

실제 프로젝트에서 손으로 실측(시험 작업은 뒤에 보관): `/branch` → 새 세션 id, 설치기 matcher에 `fork`가 있으면 SessionStart 주입(2.12.0). `/rewind` 대화 복원 → 같은 id, 모델에게 되감기 표시 없음, `show` 없이 재저장 → 중복 사건 1건(결정은 코어가 중복 제거) → 2.13.0에서 같은 세션·같은 summary 재저장 거부. `/rewind` 코드 복원 → 파일 삭제, 원장 그대로, 보고 없음(문서 기재, 코어 변경 없음). git worktree → 원장 둘, events.jsonl·state.md·writer.json 병합 충돌 → 2.13.0 `warning_worktree`. `/btw`→`f` 포크 → 메인 id로 자각하며 저장, 메인은 skip. 동시 저장 → 거부, `show`, 재저장. 추가 실측(2026-10-14): rewind 메뉴 "Summarize from here"는 세션 id가 그대로이고 SessionStart(compact)가 발화해 기록이 주입되며, 모델은 그 주입으로 작업·결정을 답했다(되감기 지점의 프롬프트가 입력창에 다시 채워짐에 주의). Codex 대화형 `resume`은 첫 프롬프트 때 SessionStart(resume) 발화. `$worklog`는 스킬 본문을 주입한다(Codex rollout에 `<skill><name>worklog</name>`). 2.13.0 worktree 경고는 모델이 사용자에게 설명했다(PASS 1/1). 근거: [`verification/checks-20261014.md`](verification/checks-20261014.md).

**Codex(2026-10-14, codex-cli 0.158.0, 신뢰된 시험 루트, 설치된 훅 옆에 matcher 없는 기록용 SessionStart 훅).** `/fork` → 새 thread, `source: fork`, 설치된 훅 미발화. `/new` → 새 thread, `startup`, 발화. `/clear` → 새 thread, `clear`, 미발화. `/side` → 도구 있는 새 thread, `fork`, 미발화(UserPromptSubmit·Stop은 발화). Codex는 새 thread의 첫 프롬프트 때 SessionStart를 발화한다. → 2.14.0에서 Codex matcher에 `clear`·`fork` 추가. 근거: `shared/runs/codex-fork-20261014/`.

**② 후속(2.15.0).** 현재 세션이 기록한 산출물의 파일이 없으면 show·use·주입과 save·skip 결과에 표시하고, `verify`는 모든 산출물의 존재·해시를 대조한다. 모델 실행 1회(M10, Claude opus, 2026-10-14): 모델이 산출물을 저장한 뒤 파일을 지우고 같은 세션을 재개하자 다음 save 결과에 `artifacts_missing`이 붙었고, 모델은 폴더를 확인해 사용자에게 파일이 사라졌다고 알리고 대기 항목을 기록한 뒤 다시 만들지 물었다 — PASS 1/1(1회라 "항상"은 아님). 근거: [`verification/m-20261014-v2150.md`](verification/m-20261014-v2150.md).

## Delegation rule (2.8.0) — subagent vs separate session (2026-10-13, 23 model runs + 2 real uses)

### English

The 2.8.0 rule splits delegation in two. **Subagent** (same session): the delegation prompt says "do not run Worklog commands (use·save·skip)", the delegating session saves in the same turn with `[위임: …]` at the head of the summary (never inside decision or constraint text), files as artifacts+check, proposals as `source: model`. **Separate session**: opened with the hooks running, first prompt `"<id> 이어서. 하위 작업: <name>"`, no forbid line (the sub-session saves by itself), same goal → same work id, independent goal → `새 작업:` with the parent id in the summary; the opener skips while the sub runs, then `show` and an adopt-save; if the sub ended without saving, the opener saves instead and notes "하위 세션 기록 없음". 2.7.0 had applied the forbid line and same-turn save to both cases, which made the separate-session half impossible to follow. All runs below used the 2.8.0 branch before merge (`WL_SHARED`).

| Layer / cell | Runs | Result |
|---|---|---|
| M7 subagent (Claude opus) | 3 | 3/3: forbid line, single save, proposals `[모델]` |
| M8 separate session, same goal (Claude opus / Codex astra, sub opened through Herdr with the same tool) | 3 + 3 | 6/6: turn 1 skip (0 saves), sub saved by itself with artifacts+check, turn 2 adopt-save (1). "Codex astra" is the main session; the sub-session opened through Herdr runs the user's default interactive model (GPT-6.1-Sol at the time) |
| M8b separate session, independent goal | 2 + 2 | clause observed 4/4 (`새 작업:` + parent id); machine 0/4 for non-rule reasons (prompt design ×2, delegation noted on the parent work ×1 — allowed by the text, sub asked about constraint inheritance ×1) |
| M9 fallback (sub ended without events) | 2 + 2 | 4/4: `[위임:]` + "하위 세션 기록 없음", artifacts+check, single save |
| I5 two compactions, then a delegating turn (Claude subagent / Codex Herdr session) | 1 + 1 smoke, 3 + 3 | delegation 8/8; Layer I criteria 1·4·5, F4, F5 unchanged (8/8). Codex ran with the user's full-access setting (an approval prompt blocks the Herdr socket); its tool/time counts exceed the reference caps because of the Herdr commands |
| Real project, subagent (Claude, 2026-10-12, rule 2.7.0 = same subagent text) | 1 | PASS: one save, `[위임:]`, artifacts+check, no Worklog call by the subagent |
| Real project, separate session (Claude main + Herdr Claude sub, 2026-10-13) | 1 | PASS by hand: turn 1 `use` → Herdr tab + Claude sub → `skip` (0 saves); the sub saved E0192 by itself (artifacts+check); turn 2 `[위임:]` adopt-save (1 event, decision `source: model`). The opener's adopt-save carried no artifact entry (the sub had recorded it) — the rule does not require re-recording |

**2.9.0 follow-up (2026-10-13, 15 model runs).** Three sentences added: operating instructions to the agent are not constraints (A); a turn delegating an independent goal may note it on the parent work (B); the opener lists the inherited decisions and constraints in the sub-session's prompt and the sub does not ask again (B'). M3b (M3 prompt + two operating instructions + two natural constraints): Claude 2/2, Codex 3/3 and a Codex control under 2.8.0 3/3 all saved the operating instruction 0 times with the existing M3 keys intact, so A causes no regression but its benefit did not show in this cell; the natural constraints without a duration phrase were saved 0/10 under both versions (baseline). M8b with B only: Claude 2/2, Codex 0/2 — the Codex sub stopped to ask about constraint inheritance (the `new-work` notice) instead of writing the file. With B' added: Codex 2/2, Claude 1/1. Judge changes made after runs were rejudged across the campaign (M3b criterion, parent note by title, stitched verbatim quotes). Evidence: [`verification/m-20261013-v290.md`](verification/m-20261013-v290.md).

Not shown by this: "always" (2–3 runs per cell), Codex subagents (no tool), the path where the opener waits inside the turn (seen only in the real uses, not in M8). Two Codex I5 runs saved a harness instruction ("no separate Goal / extra evaluator / Hook") as a fifth constraint in T1, before any delegation; the constraint wording has not changed since 2.2.0, so this is interpretation variance, not an effect of 2.8.0. Evidence: [`verification/m-20261013-delegation2.md`](verification/m-20261013-delegation2.md), `runs/I5-RESULTS.md`, `runs/real-delegation2-20261013/`.

### 한국어

2.8.0 규칙은 위임을 둘로 나눕니다. **서브에이전트**(같은 세션): 위임 프롬프트에 "Worklog 명령(use·save·skip)은 실행하지 않는다"를 넣고, 시킨 세션이 같은 턴에 summary 첫머리 `[위임: …]`(결정·제약 글자에는 쓰지 않음)로 save, 파일은 artifacts+check, 제안은 `source: model`. **별도 세션**: Hook이 도는 방식으로 열고 첫 프롬프트는 `"<id> 이어서. 하위 작업: <이름>"`, 금지문 없음(하위가 스스로 save), 같은 목표면 같은 작업 id, 독립 목표만 `새 작업:` + summary에 상위 id. 연 세션은 하위가 도는 동안 skip, 끝나면 `show` 뒤 채택 save, 하위가 save 없이 끝나면 대신 save하고 "하위 세션 기록 없음"을 적습니다. 2.7.0은 금지문과 같은 턴 save를 두 경우 모두에 적용해 별도 세션 쪽을 따를 수 없었습니다. 아래 회차는 모두 병합 전 2.8.0 브랜치(`WL_SHARED`)로 돌렸습니다.

| 층 / 셀 | 회차 | 결과 |
|---|---|---|
| M7 서브에이전트(Claude opus) | 3 | 3/3: 금지문, save 1건, 제안 `[모델]` |
| M8 별도 세션·같은 목표(Claude opus / Codex astra, 하위는 Herdr로 같은 도구) | 3 + 3 | 6/6: 1턴 skip(save 0) → 하위가 artifacts+check로 스스로 save → 2턴 채택 save 1건. "Codex astra"는 메인 기준이며 Herdr로 연 하위 세션은 사용자 기본 대화형 모델(당시 GPT-6.1-Sol)로 돌았다 |
| M8b 별도 세션·독립 목표 | 2 + 2 | 조항 4/4 관찰(`새 작업:` + 상위 id). 기계 0/4는 비규칙 원인(프롬프트 설계 2, 상위 작업에 위임 기록 1 = 문장상 허용, 하위가 제약 승계 질문 1) |
| M9 대체 save(하위가 사건 없이 끝남) | 2 + 2 | 4/4: `[위임:]` + "하위 세션 기록 없음", artifacts+check, save 1건 |
| I5 압축 2회 뒤 위임 턴(Claude 서브에이전트 / Codex Herdr 세션) | 연기 1 + 1, 본 3 + 3 | 위임 8/8. I층 기준 1·4·5, F4·F5 동일(8/8). Codex는 사용자 설정(full access) 유지(승인 요청이 Herdr 소켓을 막음), Herdr 명령 때문에 도구·시간 참고 상한 초과 |
| 실제 프로젝트, 서브에이전트(Claude, 2026-10-12, 2.7.0 = 같은 서브에이전트 문장) | 1 | PASS: save 1건, `[위임:]`, artifacts+check, 서브에이전트의 Worklog 호출 0 |
| 실제 프로젝트, 별도 세션(Claude 메인 + Herdr Claude 하위, 2026-10-13) | 1 | 사람 PASS: 1턴 `use` → Herdr 탭 + Claude 하위 → `skip`(save 0), 하위가 E0192를 스스로 save(artifacts+check), 2턴 `[위임:]` 채택 save 1건(결정 `source: model`). 연 세션의 채택 save에는 artifacts가 없음(하위가 기록) — 규칙은 재기록을 요구하지 않음 |

**2.9.0 후속(2026-10-13, 모델 15회).** 문장 셋을 추가했습니다: 에이전트 운영 지시는 제약이 아니다(A), 독립 목표를 위임한 턴은 상위 작업에 기록해도 된다(B), 연 세션이 하위 프롬프트에 이어받을 결정·제약을 적고 하위는 다시 묻지 않는다(B'). M3b(M3 프롬프트 + 운영 지시 2 + 자연 제약 2): Claude 2/2, Codex 3/3, 2.8.0 Codex 대조 3/3 모두 운영 지시 저장 0, 기존 M3 키 유지 → A는 회귀 없음, 효과는 이 셀로 입증되지 않음. 지속 표현 없는 자연 제약은 두 버전 모두 0/10 저장(기본 동작). M8b B만: Claude 2/2, Codex 0/2 — Codex 하위가 파일을 쓰지 않고 `new-work` notice대로 승계 여부를 물음. B' 추가 뒤 Codex 2/2, Claude 1/1. 실행 뒤 판정기 수정은 전 회차 재판정(M3b 기준, 제목으로 지칭한 상위 기록, 원문 줄 이어붙인 quote). 근거: [`verification/m-20261013-v290.md`](verification/m-20261013-v290.md).

이 결과가 보여 주지 않는 것: "항상"(셀당 2~3회), Codex 서브에이전트(도구 없음), 연 세션이 턴 안에서 기다리는 경로(M8이 아니라 실사용에서만 관찰). Codex I5 2회는 위임 전 T1에서 실행 지시("별도 Goal·추가 평가기·Hook 사용 금지")를 다섯째 제약으로 저장했는데, 제약 규칙 문장은 2.2.0 이후 바뀌지 않았으므로 2.8.0의 효과가 아니라 해석 편차입니다. 근거: [`verification/m-20261013-delegation2.md`](verification/m-20261013-delegation2.md), `runs/I5-RESULTS.md`, `runs/real-delegation2-20261013/`.

## Layer I — interactive runs with two compactions under the current rules (2026-10-10, 6 runs + 2 smoke)

### English

Interactive sessions driven through terminal panes: T0 (two works, no selection) → T1 → S (Stop observation) → `/compact` → T2 → `/compact` → T3. Same scenario as the 12-run matrix below, with four user constraints and two artifacts in T3 (`note-guide.md`, exactly two sentences; `plan.md`, free form). Rules in force: the 2026-10-09 rules plus the F2 wording (PR #3). One smoke run per tool first (single-work scenario), then opus-5-5 medium, sonnet-5-5 medium, gpt-6-astra medium ×3, gpt-6.1-sol high. 8/8 runs completed without a harness retry; all within the cost caps (tools 5–9, 110–178 s including both compactions, Claude 570–590K observed tokens as reference, Codex 240–310K).

| Criterion | Result | Evidence |
|---|---|---|
| 4 work selection: T0 asks, saves nothing, leaves the other work unchanged | 6/6 | T0 question (one through the question UI), 0 events, seed ledger hash unchanged |
| 5 SessionStart injection after each compaction names the current work | 6/6 | `## 현재 작업: habit-plan` in both compact injections |
| 1 restoration after two compactions | 6/6 | T3 used the T2 value (11 min) and the four T1 constraints; one run instead found a 7-vs-11 conflict in the ledger and asked |
| 2 change kept, wait kept, two sentences, no early files | 5/5 | the sixth run stopped at a question (see below), so 2 and 3 are not evaluated for it |
| 3 content decisions quoted from the body, `self_quoted` 0, every `미반영` with a reason | 5/5 | Claude left working-method constraints unreflected with reasons; Codex wrote them into the body |
| Stop block in S | Claude 2/2 direct (`stop_hook_summary`), Codex indirect only | |

Findings, not applied: (F4) all four Codex runs copied the constraint sentences into the second sentence of the guide and quoted parts of them — the core's `self_quoted` only catches exact matches, and the T3 prompt itself asked to "reflect the constraints in both files", so the prompt invited it; Claude did not. (F5) No run used `D_AGENT`: proposals the model itself labelled "(model suggestion)" were saved inside REQUEST/D_USER events and therefore tagged `[사용자]`. In one astra run that mis-tag surfaced after compaction as a 7-minute breakdown contradicting the 11-minute decision; the model asked before writing, as T3 allowed, so that run ended blocked (1 of 3 identical runs — recorded as probabilistic, no rule change). Codex also stored the turn instruction "no extra Goal, evaluator or Hook" as a constraint (F2 class).

**Applied later the same day (F4, F5).** A decision may now carry its own `"source": "model"`, so a proposal the model makes in the same turn as a user request is tagged `[모델]` inside the user event (`"user"` is rejected; one new unit test, 76 in total). The rules and `SAVE_HELP` now say that constraint sentences are not written into the artifact body even paraphrased, and that "reflect the constraints" means the body must not violate them. Checked with a Codex single-turn scenario that uses the same inducement as T3 plus "propose the 11-minute split yourself": 3 of 3 runs kept the working-method constraints out of the body (unreflected with reasons) and saved the proposal as `[모델]`. Two Claude (Opus) runs of the same scenario also passed: both saved the proposal as `[모델]` and kept the constraint wording out of the body (one quoted a sentence that embodies the "no publishing" constraint, which the rules allow). Whether this holds after compaction is untested.

**Rerun after F4·F5, two compactions (2026-10-12, core 2.3.0, 6 runs + 2 smoke).** Same harness and prompts, with one sentence added to T1 ("propose the split of the minutes yourself and record it") so that F5 is exercised; the judge gained `f4_ok`/`f5_ok` with the same criteria as the single-turn check. Runs: smoke sonnet-5-5 medium and gpt-6-astra medium (single work), then opus-5-5 medium, sonnet-5-5 medium, gpt-6-astra medium ×3, gpt-6.1-sol high. 8/8 completed without a retry, all within the caps (tools 6–9, 117–174 s including both compactions). Criteria 1–5 and 3b: 8/8. F4: no run quoted a working-method constraint from the body or wrote its wording into the body (0/8; previously Codex 4/4). F5: every run saved the proposed split as `[모델]` (8/8), none as `[사용자]`. F2 class: every run stored exactly the four user constraints; the turn instruction "no extra Goal, evaluator or Hook" was stored by no run (0/8; previously Codex 4/4, Claude 1/3). Stop block: Claude 3/3 direct, Codex indirect only, as before. The global Claude Stop hook stayed on this time. Correction to the 2026-10-10 run above: the Codex trial parent's rules copy (`AGENTS.md`, inherited by every Codex child) turned out to be the 2026-10-08 install, without the F1·F2·source-tag·F4·F5 wording, so the five Codex runs of 2026-10-10 ran under the older rules; the Claude children are installed per run and were current. The parent was reinstalled before this rerun (hook files unchanged), and the harness now refuses to start when that copy is stale. The 2026-10-12 Codex runs are therefore the first Codex evidence under the current rules.

### 한국어

터미널 패널로 구동한 대화형 세션: T0(작업 2개, 지정 없음) → T1 → S(Stop 관찰) → `/compact` → T2 → `/compact` → T3. 아래 12회 매트릭스와 같은 시나리오에 사용자 제약 4개, T3 산출물 2개(`note-guide.md` 정확히 두 문장, `plan.md` 자유 형식). 적용 규칙은 2026-10-09 규칙 + F2 문구(PR #3). 도구별 연기 1회(단일 작업) 뒤 opus-5-5 medium, sonnet-5-5 medium, gpt-6-astra medium ×3, gpt-6.1-sol high. 8/8 재시도 없이 완주, 전부 상한 이내(도구 5~9, 압축 포함 110~178초, Claude 관측 토큰 57~59만은 참고치, Codex 24~31만).

| 기준 | 결과 | 근거 |
|---|---|---|
| 4 작업 선택: T0에서 묻고 저장 없음, 다른 작업 불변 | 6/6 | T0 질문(1회는 질문 UI), 사건 0, seed 원장 해시 동일 |
| 5 압축 뒤 SessionStart 주입에 현재 작업 | 6/6 | 두 compact 주입 모두 `## 현재 작업: habit-plan` |
| 1 압축 2회 뒤 복원 | 6/6 | T3가 T2의 11분과 T1 제약 4개를 사용. 1회는 기록에서 7분·11분 충돌을 찾아 질문 |
| 2 변경·대기 유지, 두 문장, 조기 파일 없음 | 5/5 | 여섯째 회차는 질문에서 멈춰 기준 2·3 미평가 |
| 3 내용 결정 본문 인용, `self_quoted` 0, 모든 미반영에 이유 | 5/5 | Claude는 작업 방식 제약을 이유와 함께 미반영, Codex는 본문에 씀 |
| S 단계 Stop 차단 | Claude 2/2 직접 근거, Codex는 간접 추정만 | |

미적용 발견: (F4) Codex 4회 전부 안내문 두 번째 문장에 제약 문장들을 옮겨 적고 일부를 인용했습니다. 코어 `self_quoted`는 완전 일치만 잡고, T3 프롬프트가 "제약을 두 파일 모두에 반영"하라고 해서 유도한 면이 있습니다. Claude는 그러지 않았습니다. (F5) `D_AGENT`를 쓴 회차가 없습니다. 모델이 "(모델 제안)"이라고 적은 것도 REQUEST/D_USER 안에 넣어 `[사용자]`로 표시됐습니다. astra 1회차에서는 이 혼입이 압축 뒤 "7분 배분 vs 11분" 충돌로 드러났고, 모델은 T3가 허용한 대로 쓰기 전에 물었습니다(같은 조건 3회 중 1회, 확률적으로 기록하고 규칙은 유지). Codex는 턴 지시 "별도 Goal·평가기·Hook 사용 금지"도 제약으로 저장했습니다(F2 부류).

**같은 날 늦게 적용(F4·F5).** 결정 항목에 `"source": "model"`을 붙일 수 있게 하여, 사용자 요청과 같은 턴에 모델이 제안한 것은 사용자 사건 안에서도 `[모델]`로 표시됩니다(`"user"`는 거부, 단위 테스트 1개 추가로 76개). 규칙과 `SAVE_HELP`에 "제약 문장은 바꿔 써도 본문에 넣지 않는다, '제약 반영'은 본문이 제약을 어기지 않게 쓰라는 뜻"을 명시했습니다. T3와 같은 유인에 "11분 배분을 직접 제안하라"를 더한 Codex 단일 턴 시나리오 3회 모두 작업 방식 제약을 본문에 넣지 않았고(이유 있는 미반영) 제안을 `[모델]`로 저장했습니다. 같은 시나리오의 Claude(Opus) 2회도 통과했습니다. 둘 다 제안을 `[모델]`로 저장했고 제약 문구를 본문에 넣지 않았습니다(1회는 "게시 금지"를 지킨 내용 문장을 인용했으며 규칙이 허용하는 방식입니다). 압축 뒤에도 유지되는지는 미검증입니다.

**F4·F5 적용 뒤 압축 2회 재실행(2026-10-12, 코어 2.3.0, 본 6회 + 연기 2회).** 같은 실행기·프롬프트에 T1 한 문장("시간 배분은 당신이 제안해서 기록에 남겨 주세요")을 더해 F5를 시험했고, 판정기에 단일 턴 검사와 같은 기준의 `f4_ok`/`f5_ok`를 추가했습니다. 회차: 연기 sonnet-5-5 medium·gpt-6-astra medium(단일 작업), 본 opus-5-5 medium, sonnet-5-5 medium, gpt-6-astra medium ×3, gpt-6.1-sol high. 8/8 재시도 없이 완주, 전부 상한 이내(도구 6~9, 압축 포함 117~174초). 기준 1~5와 3b: 8/8. F4: 작업 방식 제약을 본문에서 인용하거나 본문에 옮겨 적은 회차 0/8(이전 Codex 4/4). F5: 제안한 배분을 `[모델]`로 저장 8/8, `[사용자]` 0. F2 부류: 8회 모두 사용자 제약 4개만 저장했고 턴 지시 "별도 Goal·평가기·Hook 사용 금지"를 저장한 회차 0/8(이전 Codex 4/4, Claude 1/3). Stop 차단: Claude 3/3 직접 근거, Codex는 이전과 같이 간접 추정만. 이번에는 전역 Claude Stop Hook을 켠 채 돌렸습니다. 위 2026-10-10 실행에 대한 정정: Codex 시험 상위 폴더의 규칙 사본(`AGENTS.md`, 모든 Codex 자식 폴더가 상속)이 2026-10-08 설치판이어서 F1·F2·출처 태그·F4·F5 문구가 없었습니다. 따라서 2026-10-10의 Codex 5회는 옛 규칙으로 돌았고, Claude 자식은 회차마다 설치되어 현행이었습니다. 이번 재실행 전에 상위 폴더를 재설치했고(Hook 파일 불변), 실행기는 이제 그 사본이 오래되면 시작을 거부합니다. 2026-10-12의 Codex 회차가 현행 규칙 아래의 첫 Codex 근거입니다.

## Layer M — single-turn model runs under the 2026-10-09 rules (2026-10-10, 13 runs)

### English

Non-interactive runs (`claude -p`, `codex exec`), default models, no compaction, one fresh project per run. Each run checks one rule the 12-run matrix did not cover. Machine judgment from the ledger and session files; a human read every answer. Every `quote` the model stored was a substring of the prompt (0 fabricated of 13). Claude 7 runs cost $4.62 in total; Codex 7 runs used about 880K tokens, mostly cached input.

| Scenario | Claude | Codex | Notes |
|---|---|---|---|
| M1 hooks absent → model reports the `warning` to the user | PASS | PASS | both named where to check (settings file / `/hooks`) |
| M2 `새 작업: <title>` → quote on new-work, clean title and goal, constraint tagged user | PASS | PASS* | *Codex appended a clause from the user's global instructions to `goal` and stored a one-turn instruction as a constraint |
| M3 two text artifacts under 4 constraints → no `self_quoted`, every `미반영` with a reason, content decision quoted | PASS ×2 | PASS ×2 | Codex marked all three working-method constraints unreflected; Claude quoted one or two |
| M4 Codex saves D1 in one session, Claude replaces it in a new session | PASS | PASS | `replaces` used, one valid decision |
| M5 "chapter 1 draft is done" → status stays ACTIVE | PASS | PASS | both said why they kept ACTIVE |
| M6 `.worklog/off` → no save or skip, state still summarised | PASS | PASS | |

Not shown by this layer: restoration after compaction (no compaction in `-p`/`exec`), reproducibility (one run per cell, two for M3). The compaction results below were measured under the previous rules; Layer I above repeats them under the current rules.

### 한국어

비대화형 실행(`claude -p`, `codex exec`), 기본 모델, 압축 없음, 회차마다 새 프로젝트. 각 회차는 12회 매트릭스가 보지 않던 규칙 하나를 확인합니다. 기계 판정은 원장·세션 파일, 답변은 사람이 전부 읽었습니다. 모델이 저장한 모든 `quote`는 프롬프트 원문의 일부였습니다(날조 0/13). 비용은 Claude 7회 합계 $4.62, Codex 7회 약 88만 토큰(대부분 캐시 입력).

| 시나리오 | Claude | Codex | 비고 |
|---|---|---|---|
| M1 Hook 없음 → `warning`을 사용자에게 보고 | PASS | PASS | 둘 다 확인 위치(설정 파일 / `/hooks`)를 명시 |
| M2 `새 작업: <제목>` → new-work에 quote, 제목·goal 깨끗, 제약은 [사용자] | PASS | PASS* | *Codex는 전역 지침 문구를 `goal`에 덧붙이고 턴 한정 지시를 제약으로 저장 |
| M3 제약 4개 아래 텍스트 산출물 2개 → `self_quoted` 0, 모든 미반영에 이유, 내용 결정 인용 | PASS ×2 | PASS ×2 | Codex는 작업 방식 제약 3개를 모두 미반영, Claude는 1~2개를 본문에 넣음 |
| M4 Codex가 D1 저장, Claude 새 세션이 대체 | PASS | PASS | `replaces` 사용, 유효 결정 1개 |
| M5 "1장 초안 끝" → ACTIVE 유지 | PASS | PASS | 둘 다 유지 이유를 말함 |
| M6 `.worklog/off` → save·skip 없음, 상태 요약은 함 | PASS | PASS | |

이 층이 보여 주지 않는 것: 압축 뒤 복원(`-p`/`exec`에는 압축이 없음), 재현성(칸당 1회, M3만 2회). 아래 압축 결과는 이전 규칙으로 측정한 것이며, 위 I층이 현재 규칙으로 다시 돌린 결과입니다.

## Format 2 — multi-work scenario (2026-10-06/07, 12 runs)

### English

Claude Code (fable / opus / sonnet × medium / high effort) and Codex (astra / sol / luna × medium / high), one run per condition. Before the session, the project already holds two works: `habit-plan` (the work the scenario continues) and `recipe-note` (an unrelated work with its own goal and decision). The model starts a new session with no current work. Turn T0 says only "이어서 해 줘" ("continue") without naming a work. Then T1 starts with "habit-plan 이어서. " ("continue habit-plan") followed by the same 3-turn scenario as Format 1 (goal, decisions and constraints → change one decision → two-sentence `note-guide.md`), with 2 compactions and one read-only Stop-hook observation turn.

| Criterion | Result |
|---|---|
| 1. Goal, active decisions, constraints, waiting item and next action restored after both compactions | 12/12 |
| 2. No artifact before it was requested; the changed value (11 minutes) is the valid one; exactly two sentences, re-read and compared | 12/12 |
| 3a. Every content decision and constraint quoted from the artifact body; artifact-body keyword check passed | 12/12 |
| 3b. Strict: no `미반영` ("not reflected") entry at all in the model's `check` | 9/12 |
| 4. With no work named (T0): asked which work, saved nothing, the other work's ledger unchanged (SHA-256 equal before and after every step), session kept no current work | 12/12 |
| 5. After each compaction the injected context contained `## 현재 작업: habit-plan` (current work) and the session kept `habit-plan` | 12/12 |
| SessionStart hook injection (3 per run) and Stop hook blocked a turn without save | 12/12 |
| Within cost caps (tools ≤ 18, ≤ 195 s work + compaction, ≤ 884K tokens) | 10/12 |

The three `미반영` entries in 3b were all items that cannot be quoted as a phrase: the "exactly two sentences" format condition (opus-medium, sonnet-medium), a decision scoped to one turn's working method (sonnet-medium), and a waiting item recorded as a constraint that the artifact request itself ended (luna-medium). No content constraint was omitted in any run. Both cap misses were on the time cap only, both on Fable 5.1, where each compaction took 57–69 s.

| Tool | Model | Effort | Crit. 4 | Crit. 5 | Crit. 1·2·3a | Unreflected IDs | Tool calls | Work + compaction s | Tokens | Caps (tools/time/tokens) |
|---|---|---|---|---|---|---|---:|---:|---:|---|
| claude | Opus 5.5 | high | PASS | PASS | PASS | - | 6 | 137.0 | 497,267 | ✓/✓/✓ |
| claude | Opus 5.5 | medium | PASS | PASS | PASS | D4 (format) | 7 | 126.8 | 546,873 | ✓/✓/✓ |
| claude | Sonnet 5.5 | high | PASS | PASS | PASS | - | 10 | 122.2 | 568,640 | ✓/✓/✓ |
| claude | Sonnet 5.5 | medium | PASS | PASS | PASS | D2 (format), D3 (turn-scoped) | 6 | 109.3 | 493,711 | ✓/✓/✓ |
| claude | Fable 5.1 | high | PASS | PASS | PASS | - | 18 | 293.5 | 846,053 | ✓/✗/✓ |
| claude | Fable 5.1 | medium | PASS | PASS | PASS | - | 9 | 318.5 | 625,365 | ✓/✗/✓ |
| codex | gpt-6.1-sol | high | PASS | PASS | PASS | - | 6 | 146.4 | 270,821 | ✓/✓/✓ |
| codex | gpt-6.1-sol | medium | PASS | PASS | PASS | - | 7 | 138.9 | 293,506 | ✓/✓/✓ |
| codex | gpt-6-astra | high | PASS | PASS | PASS | - | 6 | 151.7 | 266,984 | ✓/✓/✓ |
| codex | gpt-6-astra | medium | PASS | PASS | PASS | - | 6 | 148.8 | 263,747 | ✓/✓/✓ |
| codex | gpt-6-luna | high | PASS | PASS | PASS | - | 6 | 104.0 | 255,544 | ✓/✓/✓ |
| codex | gpt-6-luna | medium | PASS | PASS | PASS | C3 (ended waiting item) | 17 | 131.8 | 578,063 | ✓/✓/✓ |

Costs cover T1–T3 and the two compactions; T0 and the Stop-observation turn are excluded. Claude token counts are from assistant-message usage and do not include the compaction calls, which the transcript does not expose. In T0 Codex asked through its native question UI rather than in plain text. The first two rows (opus-high, sol-high) were run before the other ten, during tool development; some of those early runs were repeated because of defects in the test harness (harness retries, not model failures). The other ten runs each completed on the first attempt. Each condition was run once, so per-model reproducibility is not established.

### 한국어

Claude Code(fable/opus/sonnet × medium/high), Codex(astra/sol/luna × medium/high), 조건마다 1회. 세션 전에 프로젝트에는 작업 2개가 있습니다: `habit-plan`(시나리오가 이어 갈 작업)과 `recipe-note`(목표·결정이 따로 있는 관련 없는 작업). 모델은 현재 작업이 없는 새 세션에서 시작합니다. T0는 작업을 지정하지 않고 "이어서 해 줘"라고만 말합니다. 이어서 T1은 "habit-plan 이어서. "로 시작하고 형식 1과 같은 3턴 시나리오(목표·결정·제약 → 결정 하나 변경 → 두 문장짜리 `note-guide.md`)를 압축 2회, 읽기 전용 Stop Hook 관찰 턴 1회와 함께 진행합니다.

| 기준 | 결과 |
|---|---|
| 1. 두 번의 압축 뒤 목표·유효 결정·제약·대기·다음 행동 복원 | 12/12 |
| 2. 요청 전 산출물 없음, 바꾼 값(11분)이 유효, 정확히 두 문장·저장본 재확인 | 12/12 |
| 3a. 내용 결정·제약을 모두 산출물 본문에서 인용, 본문 키워드 검사 통과 | 12/12 |
| 3b. 엄격: 모델의 `check`에 `미반영` 항목이 하나도 없음 | 9/12 |
| 4. 작업 지정 없음(T0): 어느 작업인지 질문, 저장 0, 다른 작업 원장 불변(단계마다 SHA-256 동일), 현재 작업 없음 유지 | 12/12 |
| 5. 압축마다 주입 내용에 `## 현재 작업: habit-plan` 포함, 세션의 현재 작업 유지 | 12/12 |
| SessionStart Hook 주입(회차마다 3회), save 없는 턴의 Stop 차단 | 12/12 |
| 비용 상한 이내(도구 ≤18회, 업무+압축 ≤195초, ≤884K 토큰) | 10/12 |

3b의 `미반영` 3건은 모두 구절로 인용할 수 없는 항목이었습니다: "정확히 두 문장" 형식 조건(opus-medium, sonnet-medium), 한 턴의 작업 방식에 한정된 결정(sonnet-medium), 산출물 요청으로 소멸한 대기 항목을 제약으로 적은 것(luna-medium). 내용 제약이 빠진 회차는 없습니다. 상한 초과 2건은 둘 다 Fable 5.1의 시간 상한만이며, 압축 1회에 57~69초가 걸렸습니다. 회차별 수치는 위 영어 절의 표를 봅니다.

비용은 T1~T3와 압축 2회 기준이며 T0와 Stop 관찰 턴은 제외했습니다. Claude 토큰은 assistant 메시지 사용량 합계이며, 전사에 드러나지 않는 압축 호출 사용량은 빠져 있습니다. T0에서 Codex는 일반 텍스트 대신 네이티브 질문 UI로 물었습니다. 처음 2회(opus-high, sol-high)는 도구 개발 중에 먼저 실행했고, 그중 일부는 시험 도구 결함으로 다시 실행했습니다(harness retries, not model failures). 나머지 10회는 모두 1회에 완주했습니다. 조건마다 1회라서 모델별 재현성은 확인되지 않았습니다.

## Format 1 (2026-10-06)

### English

#### Synthetic scenario matrix (12 runs)

Claude Code (fable / opus / sonnet × medium / high effort) and Codex (astra / sol / luna × medium / high), one run per condition. Each run is a synthetic scenario of 3 turns with 2 compactions: the user sets a goal, decisions and constraints, changes one decision, and finally asks for a two-sentence artifact (`note-guide.md`).

| Result | Count |
|---|---|
| Values restated correctly after compaction | 12/12 |
| SessionStart hook injection (3 per run) | 12/12 |
| Stop hook blocked a turn without save | 12/12 |
| No constraint reported as not reflected by the model | 8/12 |
| Artifact-body keyword check passed | 7/12 |
| Within cost caps (tools ≤ 18, ≤ 195 s work + compaction, ≤ 884K tokens) | 9/12 |

All three cap misses were on the time cap only; in two of them compaction alone took 128 s and 369 s.

| Tool | Model | Effort | Two sentences | Keyword missing | Unreflected IDs | verify | Tool calls | Work s | Compaction s | Total s | Tokens | Caps (tools/time/tokens) | Injections | Stop block |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---|
| claude | Fable 5.1 | high | ✓ | other projects / global memory | C4, D4 | ✓ | 6 | 133.2 | 127.6 | 260.8 | 440,126 | ✓/✗/✓ | 3 | ✓ |
| claude | Fable 5.1 | medium | ✓ | - | - | ✓ | 7 | 228.3 | 95.9 | 324.2 | 484,594 | ✓/✗/✓ | 3 | ✓ |
| claude | Opus 5.5 | high | ✓ | other projects / global memory | C2, C3, D4 | ✓ | 6 | 84.2 | 61.5 | 145.7 | 397,815 | ✓/✓/✓ | 3 | ✓ |
| claude | Opus 5.5 | medium | ✓ | - | - | ✓ | 6 | 69.1 | 54.0 | 123.2 | 388,360 | ✓/✓/✓ | 3 | ✓ |
| claude | Sonnet 5.5 | high | ✓ | - | D2, D3 | ✓ | 6 | 68.2 | 47.7 | 115.8 | 359,687 | ✓/✓/✓ | 3 | ✓ |
| claude | Sonnet 5.5 | medium | ✓ | other projects / global memory | - | ✓ | 6 | 61.1 | 51.2 | 112.2 | 404,180 | ✓/✓/✓ | 3 | ✓ |
| codex | gpt-6-astra | high | ✓ | - | - | ✓ | 6 | 85.0 | 368.5 | 453.5 | 246,060 | ✓/✗/✓ | 3 | ✓ |
| codex | gpt-6-astra | medium | ✓ | - | - | ✓ | 6 | 71.2 | 49.5 | 120.7 | 247,012 | ✓/✓/✓ | 3 | ✓ |
| codex | gpt-6-luna | high | ✓ | other projects / global memory | C4, D3 | ✓ | 8 | 118.4 | 24.1 | 142.5 | 300,944 | ✓/✓/✓ | 3 | ✓ |
| codex | gpt-6-luna | medium | ✓ | other projects / global memory | C1, C4 | ✓ | 7 | 74.6 | 15.9 | 90.6 | 263,195 | ✓/✓/✓ | 3 | ✓ |
| codex | gpt-6.1-sol | high | ✓ | - | - | ✓ | 7 | 108.5 | 59.1 | 167.7 | 285,592 | ✓/✓/✓ | 3 | ✓ |
| codex | gpt-6.1-sol | medium | ✓ | - | - | ✓ | 5 | 59.9 | 45.0 | 104.9 | 218,847 | ✓/✓/✓ | 3 | ✓ |

Column notes: *Two sentences* — the artifact has the requested two sentences. *Keyword missing* — a required keyword group absent from the artifact body. *Unreflected IDs* — decisions (D) or constraints (C) the model marked `미반영` ("not reflected") in its `check`; the 8/12 above counts runs with no constraint reported as not reflected. By the artifact-body keyword check it is 7/12: sonnet-medium omitted one required phrase without reporting it. *verify* — `wl.py verify` passed.

#### Real project observation

On one real project (after migrating its existing 182-event ledger), Codex and Claude Code were each observed once. In both, the state was injected at session start and after compaction, saves happened at turn end, each tool picked up records written by the other, the answer restored after compaction matched the ledger, and a read-only turn ended with `skip`.

### 한국어

#### 합성 시나리오 매트릭스 (12회)

Claude Code(fable/opus/sonnet × medium/high), Codex(astra/sol/luna × medium/high), 조건마다 1회. 각 회차는 3턴 + 압축 2회의 합성 시나리오입니다: 사용자가 목표·결정·제약을 정하고, 결정 하나를 바꾸고, 마지막에 두 문장짜리 산출물(`note-guide.md`)을 요청합니다.

| 항목 | 결과 |
|---|---|
| 압축 뒤 값 일치 | 12/12 |
| SessionStart Hook 주입(회차마다 3회) | 12/12 |
| save 없는 턴의 Stop 차단 | 12/12 |
| 모델이 미반영으로 신고한 제약이 없는 회차 | 8/12 |
| 본문 키워드 검사 통과 | 7/12 |
| 비용 상한 이내(도구 ≤18회, 업무+압축 ≤195초, ≤884K 토큰) | 9/12 |

상한을 넘은 3건은 모두 시간 상한만 넘었고, 그중 2건은 압축 하나에만 128초·369초가 걸렸습니다. 회차별 수치는 위 영어 절의 표를 봅니다(열 뜻: 두 문장 = 산출물이 요청대로 두 문장, 키워드 누락 = 산출물 본문에 없는 필수 키워드 묶음, 미반영 ID = 모델이 `check`에 `미반영`으로 적은 결정(D)·제약(C)). 8/12는 모델이 미반영으로 신고한 제약이 없는 회차 수이고, 본문 키워드 검사 기준으로는 7/12입니다(sonnet-medium은 신고 없이 문구 1개 생략).

#### 실제 프로젝트 관찰

실제 프로젝트 1곳(기존 원장 182건을 이전한 뒤)에서 Codex와 Claude Code를 각 1회 관찰했습니다. 두 도구 모두 세션 시작과 압축 뒤에 상태가 주입되었고, 턴 끝에 저장했으며, 상대 도구가 남긴 기록을 이어받았고, 압축 뒤 복원한 답변이 원장과 일치했으며, 읽기 전용 턴은 `skip`으로 마쳤습니다.
