# Verification / 검증 결과

> **Criterion change (2026-10-09).** From the next run on, criterion 3b is replaced: *no `self_quoted` entry, and every `미반영` entry has a reason*. The old 3b ("no `미반영` at all") rewarded writing the rule text into the artifact and quoting it back, which `wl.py` now reports as `self_quoted`. The results below were measured under the old criterion.
>
> **기준 변경 (2026-10-09).** 다음 시험부터 3b는 "`self_quoted` 0건, 모든 `미반영`에 이유 있음"으로 바꿉니다. 옛 3b("미반영 0건")는 규칙 문장을 산출물에 써 넣고 그대로 인용하는 행동을 보상했고, 이제 `wl.py`가 그것을 `self_quoted`로 표시합니다. 아래 결과는 옛 기준으로 측정한 것입니다.

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
