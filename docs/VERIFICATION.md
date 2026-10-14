# Verification / 검증 결과

> **Criterion change (2026-10-09).** From the next run on, criterion 3b is replaced: *no `self_quoted` entry, and every `미반영` entry has a reason*. The old 3b ("no `미반영` at all") rewarded writing the rule text into the artifact and quoting it back, which `wl.py` now reports as `self_quoted`. The results below were measured under the old criterion.
>
> **기준 변경 (2026-10-09).** 다음 시험부터 3b는 "`self_quoted` 0건, 모든 `미반영`에 이유 있음"으로 바꿉니다. 옛 3b("미반영 0건")는 규칙 문장을 산출물에 써 넣고 그대로 인용하는 행동을 보상했고, 이제 `wl.py`가 그것을 `self_quoted`로 표시합니다. 아래 결과는 옛 기준으로 측정한 것입니다.

## Rewind · branch · worktree (2.12.0–2.13.0, 2026-10-13, Claude Code, 1 real session)

Measured by hand in the real project (test work archived afterwards): `/branch` → new session id, SessionStart injected once the installer matcher includes `fork` (2.12.0). `/rewind` conversation restore → same id, no rewind marker reaches the model, the model re-saved the turn without `show` → one duplicate event (decisions deduplicated by the core) → 2.13.0 refuses a same-session same-summary re-save. `/rewind` code restore → file gone, ledger unchanged, not reported (documented, no core change). git worktree → two ledgers, merge conflicts in events.jsonl/state.md/writer.json → 2.13.0 `warning_worktree`. `/btw`→`f` fork → saved under the main id with self-awareness, main skipped. Concurrent save → refused, `show`, re-saved. Not measured: rewind-menu Summarize, Codex interactive resume (source `resume` per the Codex source code, already in the matcher).

**Codex (2026-10-14, codex-cli 0.158.0, trusted trial root, a logging SessionStart hook without matcher beside the installed one).** `/fork` → new thread, `source: fork`, installed hook did not run; `/new` → new thread, `startup`, ran; `/clear` → new thread, `clear`, did not run; `/side` → new thread with tools, `fork`, did not run (UserPromptSubmit·Stop did). Codex fires SessionStart at the new thread's first prompt. → 2.14.0 adds `clear`·`fork` to the Codex matcher. Evidence: `shared/runs/codex-fork-20261014/`.

실제 프로젝트에서 손으로 실측(시험 작업은 뒤에 보관): `/branch` → 새 세션 id, 설치기 matcher에 `fork`가 있으면 SessionStart 주입(2.12.0). `/rewind` 대화 복원 → 같은 id, 모델에게 되감기 표시 없음, `show` 없이 재저장 → 중복 사건 1건(결정은 코어가 중복 제거) → 2.13.0에서 같은 세션·같은 summary 재저장 거부. `/rewind` 코드 복원 → 파일 삭제, 원장 그대로, 보고 없음(문서 기재, 코어 변경 없음). git worktree → 원장 둘, events.jsonl·state.md·writer.json 병합 충돌 → 2.13.0 `warning_worktree`. `/btw`→`f` 포크 → 메인 id로 자각하며 저장, 메인은 skip. 동시 저장 → 거부, `show`, 재저장. 미실측: rewind 메뉴 Summarize, Codex 대화형 resume(소스상 `resume`, matcher에 이미 있음).

**Codex(2026-10-14, codex-cli 0.158.0, 신뢰된 시험 루트, 설치된 훅 옆에 matcher 없는 기록용 SessionStart 훅).** `/fork` → 새 thread, `source: fork`, 설치된 훅 미발화. `/new` → 새 thread, `startup`, 발화. `/clear` → 새 thread, `clear`, 미발화. `/side` → 도구 있는 새 thread, `fork`, 미발화(UserPromptSubmit·Stop은 발화). Codex는 새 thread의 첫 프롬프트 때 SessionStart를 발화한다. → 2.14.0에서 Codex matcher에 `clear`·`fork` 추가. 근거: `shared/runs/codex-fork-20261014/`.

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

**2.9.0 follow-up (2026-10-13, 15 model runs).** Three sentences added: operating instructions to the agent are not constraints (A); a turn delegating an independent goal may note it on the parent work (B); the opener lists the inherited decisions and constraints in the sub-session's prompt and the sub does not ask again (B'). M3b (M3 prompt + two operating instructions + two natural constraints): Claude 2/2, Codex 3/3 and a Codex control under 2.8.0 3/3 all saved the operating instruction 0 times with the existing M3 keys intact, so A causes no regression but its benefit did not show in this cell; the natural constraints without a duration phrase were saved 0/10 under both versions (baseline). M8b with B only: Claude 2/2, Codex 0/2 — the Codex sub stopped to ask about constraint inheritance (the `new-work` notice) instead of writing the file. With B' added: Codex 2/2, Claude 1/1. Judge changes made after runs were rejudged across the campaign (M3b criterion, parent note by title, stitched verbatim quotes). Evidence: `worklog-control/shared/runs/m-20261013-v290/RESULTS.md`.

Not shown by this: "always" (2–3 runs per cell), Codex subagents (no tool), the path where the opener waits inside the turn (seen only in the real uses, not in M8). Two Codex I5 runs saved a harness instruction ("no separate Goal / extra evaluator / Hook") as a fifth constraint in T1, before any delegation; the constraint wording has not changed since 2.2.0, so this is interpretation variance, not an effect of 2.8.0. Evidence: `worklog-control/shared/runs/m-20261013-delegation2/RESULTS.md`, `runs/I5-RESULTS.md`, `runs/real-delegation2-20261013/`.

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

**2.9.0 후속(2026-10-13, 모델 15회).** 문장 셋을 추가했습니다: 에이전트 운영 지시는 제약이 아니다(A), 독립 목표를 위임한 턴은 상위 작업에 기록해도 된다(B), 연 세션이 하위 프롬프트에 이어받을 결정·제약을 적고 하위는 다시 묻지 않는다(B'). M3b(M3 프롬프트 + 운영 지시 2 + 자연 제약 2): Claude 2/2, Codex 3/3, 2.8.0 Codex 대조 3/3 모두 운영 지시 저장 0, 기존 M3 키 유지 → A는 회귀 없음, 효과는 이 셀로 입증되지 않음. 지속 표현 없는 자연 제약은 두 버전 모두 0/10 저장(기본 동작). M8b B만: Claude 2/2, Codex 0/2 — Codex 하위가 파일을 쓰지 않고 `new-work` notice대로 승계 여부를 물음. B' 추가 뒤 Codex 2/2, Claude 1/1. 실행 뒤 판정기 수정은 전 회차 재판정(M3b 기준, 제목으로 지칭한 상위 기록, 원문 줄 이어붙인 quote). 근거: `worklog-control/shared/runs/m-20261013-v290/RESULTS.md`.

이 결과가 보여 주지 않는 것: "항상"(셀당 2~3회), Codex 서브에이전트(도구 없음), 연 세션이 턴 안에서 기다리는 경로(M8이 아니라 실사용에서만 관찰). Codex I5 2회는 위임 전 T1에서 실행 지시("별도 Goal·추가 평가기·Hook 사용 금지")를 다섯째 제약으로 저장했는데, 제약 규칙 문장은 2.2.0 이후 바뀌지 않았으므로 2.8.0의 효과가 아니라 해석 편차입니다. 근거: `worklog-control/shared/runs/m-20261013-delegation2/RESULTS.md`, `runs/I5-RESULTS.md`, `runs/real-delegation2-20261013/`.

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
