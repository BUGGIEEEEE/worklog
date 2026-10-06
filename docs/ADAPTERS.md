# 도구별 연결 / Tool adapters

> **English summary.** `tools/install_project.py --tool <claude|codex|pi> --root <project>` connects one project. It writes only inside that folder (links pointing outside are refused), checks everything before the first write (a refusal changes nothing, exit 2), and backs up changed files to `.bak-worklog-<date-time>`; re-running keeps a single managed block. Claude Code and Codex get a rules block, three hooks (SessionStart → `wl.py hook`, UserPromptSubmit → `wl.py turn-start`, Stop → `wl.py stop-hook`), a skill, and an empty `.worklog/` folder (the connection signal). Codex requires the user to trust the project and the three hooks in `/hooks`; Claude Code needs no hook approval, only the one-time folder trust dialog in a git repository. Pi gets the rules block and a skill only — no hooks, so nothing is enforced, and it is untested. Hooks read `cwd` and the session ID from the hook event on stdin and stay silent where there is no `.worklog/` folder.

## 설치

```sh
python3 -B tools/install_project.py --tool <claude|codex|pi> --root <프로젝트> [--dry-run]
```

그 폴더 안에만 쓰고(밖을 가리키는 링크는 거부), 첫 쓰기 전에 모든 대상을 검사해 거부되면(exit 2) 아무것도 바꾸지 않으며, 바꾸는 파일은 `.bak-worklog-<날짜시각>`으로 백업합니다. Claude·Codex 설치는 빈 `.worklog/` 폴더도 만들며 원장은 만들지 않습니다(첫 `save`가 만듦). 다시 실행해도 지침 블록은 하나만 남습니다.

## 도구별 비교

| | Claude Code | Codex | Pi |
|---|---|---|---|
| 시작 지침 | `CLAUDE.md` 블록 | `AGENTS.md` 블록 | `AGENTS.md` 블록 |
| Skill | `.claude/skills/worklog` | `.agents/skills/worklog` (경로 미확인) | `.pi/skills/worklog` (프로젝트 신뢰 후 로드) |
| Hook 위치 | `.claude/settings.local.json` | `.codex/hooks.json` | 없음 |
| SessionStart (시작·압축 뒤 주입) | startup·resume·clear·compact → `wl.py hook --tool claude` | startup·resume·compact → `wl.py hook --tool codex` | 없음 — 지침("못 봤으면 `show`") |
| UserPromptSubmit (턴 시작) | `wl.py turn-start --tool claude` | `wl.py turn-start --tool codex` | 없음 — 지침 |
| Stop (저장 확인) | `wl.py stop-hook --tool claude` | `wl.py stop-hook --tool codex` | 없음 — 지침 |
| 신뢰 절차 | Hook 승인 불필요. git 저장소면 첫 시작 때 폴더 신뢰 대화상자 1회 | 프로젝트 신뢰 + `/hooks`에서 Hook 3개 신뢰. Hook 정의가 바뀌면 재신뢰 | AGENTS.md는 신뢰 불필요, Skill은 프로젝트 신뢰 후 |
| 세션 ID | `CLAUDE_CODE_SESSION_ID` (실측) | `CODEX_THREAD_ID` (실측) | `PI_SESSION_ID` (공식 문서 기준, 미실측) |
| 한계 | — | — | Hook 없음·지침만, 강제되지 않음, 미검증 |

저장 보호는 세 도구 공통입니다: 잠금 + 세션별 신선도 검사. 마지막으로 읽은 뒤 기록이 바뀌었으면 저장이 거부되고, `show` 후 다시 저장합니다. `writer.json`은 마지막 작성자 정보일 뿐 독점이 아닙니다.

## Hook 동작

- 세 Hook은 stdin 이벤트의 `cwd`와 세션 ID를 씁니다. `--tool`은 그 도구의 세션 환경변수만 고르는 데 씁니다.
- `.worklog` 폴더가 없으면 빈 출력으로 통과합니다. 폴더만 있어도(원장이 아직 없어도) 세 Hook이 연결됩니다.
- SessionStart 주입이 있으면 턴 시작 `show`를 생략할 수 있고, 없으면 지침대로 `show`를 한 번 실행합니다. 두 경로 모두 같은 `state.md` 내용입니다.
- Stop Hook은 save도 skip도 없는 턴을 한 번 막습니다. 읽기 전용 턴의 예외는 모델이 `skip "이유" --tool <도구>`를 실행하는 데 의존합니다.
