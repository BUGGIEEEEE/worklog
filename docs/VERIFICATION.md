# Verification / 검증 결과

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
