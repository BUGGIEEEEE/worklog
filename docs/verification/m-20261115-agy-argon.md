<!-- copied from control shared/runs/m-20261115-agy-argon/RESULTS.md on 2026-11-15 · run against the deployed 2.37.0 (control shared) · run_m.py = control 6bacfb00616d -->
# agy argon 보충 시험 결과 (M21·M22, 2026-11-15)

2.35.0·2.36.0 게이트 3에서 개인 한도 소진으로 돌리지 못한 agy `gemini-4-argon-high` 셀을 한도 리셋 뒤에 돌린 기록이다.

- 대상: control `shared`의 배포본 2.37.0(core/wl.py sha256 40cb7269fc9c, adapters/rules.md 8be4bc253bfb). 시험 프로젝트에 설치된 규칙 블록은 `worklog core 2.37.0`이다.
- 원래 게이트와의 차이: M21은 2.35.0, M22는 2.36.0 작업 트리에서 돌린 셀이고 그 작업 트리는 지워졌다. rules.md는 2.36.0과 해시가 같다(M22 조건 동일). 2.35.0과는 2.36.0이 고친 두 문장(15행 포인터, 17행 완료 요청)이 다르다(M21은 그 차이를 안고 돌았다).
- 하네스: control `tools/run_m.py`(6bacfb00616d, M21·M22 포함). 정답표는 판정기의 기계 판정 그대로(M21 a–g: PLAN-M-2350 §2, M22 a–e: PLAN-2.36.0 §7.2).
- 격리: 임시 `WL_HOME`, `--agy-home`(임시 HOME. `.gemini` 링크에서 GEMINI.md·skills·config의 hooks·hooks.json·rules·skills·plugins 제외, `Library` 링크). `--out`은 `$HOME` 밖(scratchpad).
- 명령: `WL_HOME=<임시> python3 -B tools/run_m.py --out <scratch>/runs-agy-argon --runs M21:agy M22:agy --model-agy gemini-4-argon-high --agy-home <임시 HOME>`

| 셀 | 내용 | 결과 | 조건 | 시간 |
|---|---|---|---|---|
| M21 | 할 일 추가·완료(두 턴) | PASS | a–g 모두 참, verify ok | 52.2초(판정기 기록) |
| M22 | 작업을 다른 프로젝트로 옮기기(한 턴) | PASS | a–e 모두 참, 두 프로젝트 verify ok | 212.3초 |

- 판독 불가(unknown) 0건, 프롬프트에 없는 인용 0건, 답변에 Hook 언급 없음. 호출 수는 agy에서 포착되지 않는다(`tool_calls` 없음).
- M21: 턴 1에 T2 초안(open)·T3 검토(open, 선행 T2)·T4 표지(deferred), 턴 2에 T2 done·T4 cancelled·T3 open.
- M22: 새 프로젝트 작업에 T1 초안·T2 검토(선행 T1)를 다시 적고 summary에 `worklog:proj-a/report#E0001`, `#E0002` 포인터. 옛 프로젝트의 남은 할 일 둘은 cancelled.

## 한계

- 셀마다 1회라 반복 편차는 알 수 없다.
- stderr에 `warning: --mode auto is not available for this account; continuing in the default mode.`가 세 턴 모두 있었다. 턴과 save는 끝났다. 이전 agy 실행에 같은 경고가 있었는지는 대조하지 않았다.
- 2.36.0 게이트의 M18·M19b는 argon으로 돌리지 않았다(이번 범위는 M21·M22).
- 원래 게이트의 버전(2.35.0·2.36.0)이 아니라 2.37.0에서 돌렸다.

## 파일

`summary.json` · `M21-judge.json` · `M22-judge.json` · 묶음 `m-argon-runs.tgz`(실행 폴더 2개와 `run.log`).
