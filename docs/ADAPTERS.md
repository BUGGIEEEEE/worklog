# 도구별 연결 / Tool adapters

> **English summary.** `tools/install_project.py --tool <claude|codex|pi> --root <project>` connects one project. It writes only inside that folder (links pointing outside are refused), checks everything before the first write (a refusal changes nothing, exit 2), and backs up changed files to `.bak-worklog-<date-time>`; re-running keeps a single managed block. Claude Code and Codex get a rules block, three hooks (SessionStart → `wl.py hook`, UserPromptSubmit → `wl.py turn-start`, Stop → `wl.py stop-hook`), a skill, and an empty `.worklog/` folder (the connection signal). Codex requires the user to trust the project and the three hooks in `/hooks`; Claude Code needs no hook approval, only the one-time folder trust dialog in a git repository. Pi gets the rules block and a skill only — no hooks, so nothing is enforced, and it is untested. Hooks read `cwd` and the session ID from the hook event on stdin and stay silent where there is no `.worklog/` folder.
>
> **Works.** A project can hold several works. A new session starts with no current work: the SessionStart injection lists the works, and the model saves nothing until the user names one — `<id> 이어서` ("continue <id>") becomes `use <id> --quote "…"`, `새 작업: <title>` ("new work: <title>") becomes `new-work "<title>" --quote "…"`. With no choice given, the model asks once and ends the turn with `skip`; with a single work, "이어서" alone selects it. The current work is kept in the session file, so it survives compaction and its full state is injected again. Create the first work in the first session with `새 작업: <title>`.

## 설치

```sh
python3 -B tools/install_project.py --tool <claude|codex|pi> --root <프로젝트> [--dry-run] [--no-worklog-dir]
```

그 폴더 안에만 쓰고(밖을 가리키는 링크는 거부), 첫 쓰기 전에 모든 대상을 검사해 거부되면(exit 2) 아무것도 바꾸지 않으며, 바꾸는 파일은 `.bak-worklog-<날짜시각>`으로 백업합니다. Claude·Codex 설치는 빈 `.worklog/` 폴더도 만들며 원장은 만들지 않습니다(작업은 첫 세션에서 만듦). `--no-worklog-dir`은 지침·Hook만 두고 `.worklog/`는 만들지 않습니다(하위 폴더마다 따로 기록할 상위 폴더용). 다시 실행해도 지침 블록은 하나만 남습니다. `.worklog/project.md`는 사용자가 편집하는 선택 파일이며 설치기는 만들거나 덮어쓰지 않습니다.

## 도구별 비교

| | Claude Code | Codex | Pi |
|---|---|---|---|
| 시작 지침 | `CLAUDE.md` 블록 | `AGENTS.md` 블록 | `AGENTS.md` 블록(cwd·상위 폴더에서 읽음) |
| Skill | `.claude/skills/worklog` | `.agents/skills/worklog` (경로 미확인) | `.pi/skills/worklog` (프로젝트 신뢰 후 로드) |
| Hook 위치 | `.claude/settings.local.json` | `.codex/hooks.json` | 없음 |
| SessionStart (시작·압축 뒤 주입) | startup·resume·clear·compact → `wl.py hook --tool claude` | startup·resume·compact → `wl.py hook --tool codex` | 없음 — 지침("못 봤으면 `show`") |
| UserPromptSubmit (턴 시작) | `wl.py turn-start --tool claude` | `wl.py turn-start --tool codex` | 없음 — 지침 |
| Stop (저장 확인) | `wl.py stop-hook --tool claude` | `wl.py stop-hook --tool codex` | 없음 — 지침 |
| 신뢰 절차 | Hook 승인 불필요. git 저장소면 첫 시작 때 폴더 신뢰 대화상자 1회 | 프로젝트 신뢰 + `/hooks`에서 Hook 3개 신뢰. Hook 정의가 바뀌면 재신뢰 | AGENTS.md는 신뢰 불필요, Skill은 프로젝트 신뢰 후 |
| 세션 ID | `CLAUDE_CODE_SESSION_ID` (실측) | `CODEX_THREAD_ID` (실측) | `PI_SESSION_ID` (공식 문서 기준, 미실측) |
| 한계 | — | — | Hook 없음·지침만, 강제되지 않음, 미검증 |

저장 보호는 세 도구 공통입니다: 잠금 + 작업별 신선도 검사(`last_seen`). 마지막으로 읽은 뒤 그 작업의 기록이 바뀌었으면 저장이 거부되고, `show` 후 다시 저장합니다. `writer.json`은 마지막 작성자 정보일 뿐 독점이 아닙니다.

## Hook 동작

- 세 Hook은 stdin 이벤트의 `cwd`와 세션 ID를 씁니다. `--tool`은 그 도구의 세션 환경변수만 고르는 데 씁니다.
- `.worklog` 폴더가 없으면 빈 출력으로 통과합니다. 폴더만 있어도(작업이 아직 없어도) 세 Hook이 연결됩니다.
- SessionStart 주입이 있으면 턴 시작 `show`를 생략할 수 있고, 없으면 지침대로 `show`를 한 번 실행합니다. 두 경로 모두 같은 작업별 `works/<id>/state.md` 내용입니다.
- Stop Hook은 save도 skip도 작업 지정(`selected_turn`)도 없는 턴을 한 번 막습니다. 읽기 전용 턴의 예외는 모델이 `skip "이유" --tool <도구>`를 실행하는 데 의존합니다. 막힌 뒤에는 save 또는 skip으로 마칩니다.

## 작업 선택 흐름

1. 턴 시작에 `[Worklog worklog/2 SessionStart`가 보이면 사용합니다. 없으면 `show`를 실행합니다.
2. 사용자가 `habit-plan 이어서`라고 하면 모델이 `use habit-plan --quote "habit-plan 이어서"`를 실행합니다. use가 상태를 출력하므로 show 없이 저장합니다. 새 작업은 `새 작업: 요리 메모` → `new-work "요리 메모" --quote "새 작업: 요리 메모"`입니다.
3. 현재 작업도 지정도 없으면 모델이 목록을 제시하고 한 번 묻습니다. 그 턴은 `skip "작업 지정 대기"`로 끝내며 아무것도 저장하지 않습니다. 작업이 하나뿐이고 사용자가 "이어서"라고 하면 그 작업을 use합니다.
4. 현재 작업은 세션 파일에 남습니다. 압축 뒤에도 같은 작업 전체 상태를 주입합니다. 다른 작업으로 자동 전환하지 않습니다. 새 세션에서는 다시 지정합니다.
5. 잘못 기록했으면 올바른 작업과 잘못 기록한 작업 모두에 CORRECTION을 남깁니다. 사건은 옮기지 않습니다. 다른 작업을 읽는 `show --work`와 사건 입력의 `work`를 사용하며, 사용자 지정 없이 use로 전환하지 않습니다.

`save`가 "현재 작업이 없습니다"로 거부되면 사용자에게 지정을 요청합니다. `use`·`new-work`는 사용자 원문 quote가 필수입니다. 다만 그 원문이 실제 사용자 발언인지까지 기계가 검증하지는 못합니다.

## 형식 1에서 올라오기

`worklog/1`로 기록 중인 프로젝트는 코어가 저장을 거부하고 SessionStart 주입에 이전 안내를 넣습니다. 먼저 dry-run으로 확인한 뒤 `--apply`로 이전합니다. 원장 바이트는 그대로 `works/<id>/`로 옮겨지고 해시를 대조합니다. 자세한 조건: [FORMAT.md](FORMAT.md)의 "이전: 형식 1 → 2".

```sh
python3 -B tools/migrate_v1_to_v2.py --project <프로젝트> --work-id <id> [--title "<제목>"]           # dry-run
python3 -B tools/migrate_v1_to_v2.py --project <프로젝트> --work-id <id> [--title "<제목>"] --apply
```

이전 뒤 설치기를 다시 실행해 지침 블록을 형식 2로 바꿉니다.
