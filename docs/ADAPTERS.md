# 도구별 연결 / Tool adapters

> **English summary.** `tools/install_project.py --tool <claude|codex|agy|pi> --user` installs once per machine (2.21.0; agy and pi 2.24.0): the rules block, three hooks (SessionStart → `wl.py hook`, UserPromptSubmit → `wl.py turn-start`, Stop → `wl.py stop-hook`) and a skill go into the tool's user-level files (`~/.claude/CLAUDE.md` + `~/.claude/settings.json` + `~/.claude/skills/worklog`; `~/.codex/AGENTS.md` + `~/.codex/hooks.json` + `~/.agents/skills/worklog`), the manifest into `~/.worklog/install.json`. A folder is connected the moment its `.worklog/` exists: its first `new-work` creates it and adds the `.worklog/` line to `.gitignore` of a git project, the registry entry and `install.json`. Since 2.25.0 that happens on the first request worth recording, without `새 작업:` (`~/.worklog/config.json` `"auto": "on"`, the default; `--user` writes the key when it is missing); `"auto": "off"` keeps the 2.24 behaviour. Elsewhere the SessionStart hook injects one `NOT_CONNECTED` line (`root=` the candidate root: the git top level or the nearest folder with records inside it, else the folder itself; `auto=`; `git=`) and the other two hooks stay silent. `--root <project>` is the per-project install (2.x), still supported: same files inside the project plus an empty `.worklog/`. Both modes check everything before the first write (a refusal changes nothing, exit 2) and back up changed files to `.bak-worklog-<date-time>`; re-running keeps a single managed block and leaves an equivalent hook untouched, so Codex asks to trust the hooks again only when the hook definition really changed (for example after moving the clone). Codex requires the user to trust the three hooks once in `/hooks` (and each project when first opened); Claude Code needs no hook approval, only the one-time folder trust dialog in a git repository. agy gets its own rule file (`~/.gemini/config/rules/worklog.md`) and a named hook `worklog` in `~/.gemini/config/hooks.json`; Pi gets the rules block in `~/.pi/agent/AGENTS.md`, a skill and an extension (`~/.pi/agent/extensions/worklog.ts`) that runs the three hook commands. With `--root`, Pi's project extension loads only after the project is trusted; until then the rules apply without enforcement. See the table below for all four tools. Hooks read `cwd` and the session ID from the hook event on stdin.
>
> **Works.** A project can hold several works. A new session starts with no current work: the SessionStart injection lists the works, and the model saves nothing until the user names one (2.25.0: in a folder with no works it creates one from the first request instead; it never picks an existing work) — `<id> 이어서` ("continue <id>") becomes `use <id> --quote "…"`, `새 작업: <title>` ("new work: <title>") becomes `new-work "<title>" --quote "…"`. With no choice given, the model asks once and ends the turn with `skip`; with a single work, "이어서" alone selects it. The current work is kept in the session file, so it survives compaction and its full state is injected again. With `"auto": "off"` in `~/.worklog/config.json`, create the first work with `새 작업: <title>`.

## 설치

```sh
python3 -B tools/install_project.py --tool <claude|codex|agy|pi> --user [--migrate] [--dry-run]      # 기기에 한 번(2.21.0, agy·pi 2.24.0)
python3 -B tools/install_project.py --tool <claude|codex|agy|pi> --root <프로젝트> [--dry-run] [--no-worklog-dir]   # 한 프로젝트만(2.x)
```

| | `--user` (기기에 한 번) | `--root` (프로젝트마다) |
|---|---|---|
| 규칙 블록 | `~/.claude/CLAUDE.md` · `~/.codex/AGENTS.md` | 프로젝트 `CLAUDE.md` · `AGENTS.md` |
| Hook 3개 | `~/.claude/settings.json` · `~/.codex/hooks.json` | `.claude/settings.local.json` · `.codex/hooks.json` |
| 스킬 | `~/.claude/skills/worklog` · `~/.agents/skills/worklog` | `.claude/skills/worklog` · `.agents/skills/worklog` |
| 매니페스트 | `~/.worklog/install.json[tool]` | `.worklog/install.json[tool]` |
| `.worklog/`·`.gitignore` 줄·registry | 첫 `new-work`가 만든다(연결 시점) | 설치기가 만든다 |
| `~/.worklog/config.json`의 `auto` | 키가 없으면 `"auto": "on"`을 더한다(2.25.0, 다른 키 유지, 결과의 `config`) | 쓰지 않는다 |

연결 신호는 `.worklog/` 폴더입니다. `--user`는 프로젝트에 아무것도 쓰지 않고, 사용자가 어떤 폴더에서 `새 작업: <제목>`이라 하면 `new-work`가 `.worklog/`를 만들며 git 프로젝트면 `.gitignore`에 `.worklog/` 줄을 더하고(백업 없음, 한 줄 추가뿐), `~/.worklog/installs.json`에 등록하고, `.worklog/install.json`에 `{version, connected_at, scope: "user"}`를 적습니다(결과의 `connected`·`connected_changed`·`connected_notes`; 실패해도 작업은 만들어지고 notes에 남음). 상위 폴더의 `.worklog/`에 작업이 있으면 결과 `notice`로 알립니다(`~/.worklog` 같은 상태 폴더나 빈 연결은 제외). 연결한 세션의 save·skip에는 "Hook 미작동 의심" 경고가 붙지 않습니다(연결 전 Hook은 세션 파일을 남길 수 없음). `.worklog/`가 없는 폴더에서 SessionStart는 `[Worklog worklog/2 SessionStart | NOT_CONNECTED | root=…]` 한 줄만 주입하고 세션 파일·갱신 검사를 하지 않으며, `show`·`use`·`on`·`off`는 "연결되지 않은 폴더"라고 답합니다. registry에 그 도구의 프로젝트 단위 Hook이 남은 프로젝트가 있으면 `--user`는 거부합니다(Hook이 두 번 돌게 됨). `--migrate`는 그 프로젝트들의 블록·Hook·스킬·매니페스트 항목을 먼저 제거하고(기록·세션 파일·`.worklog/`·`.gitignore` 줄 유지, `install.json`에 연결 항목) 전역 설치를 합니다.

두 방식 모두 대상 폴더(홈 또는 프로젝트) 안에만 쓰고(밖을 가리키는 링크는 거부), 첫 쓰기 전에 모든 대상을 검사해 거부되면(exit 2) 아무것도 바꾸지 않으며, 바꾸는 파일은 `.bak-worklog-<날짜시각>`으로 백업합니다. `--root`의 Claude·Codex 설치는 빈 `.worklog/` 폴더도 만들며 원장은 만들지 않습니다(작업은 첫 세션에서 만듦). `--no-worklog-dir`은 지침·Hook만 두고 `.worklog/`는 만들지 않습니다(하위 폴더마다 따로 기록할 상위 폴더용). 다시 실행해도 지침 블록은 하나만 남습니다. `.worklog/project.md`는 사용자가 편집하는 선택 파일이며 설치기는 만들거나 덮어쓰지 않습니다.
registry `~/.worklog/installs.json`(WL_HOME)에는 `{프로젝트: [도구]}`가 적힙니다(2.17.0, 제거용 목록): `--root` 설치와 `new-work`의 연결이 적습니다.

## 제거

```sh
python3 -B tools/uninstall_project.py --user --tool claude|codex|all [--home] [--no-backup] [--purge-backups] [--dry-run]
python3 -B tools/uninstall_project.py --root <프로젝트> --tool claude|codex|pi|all (--keep-records | --delete-records) [--no-backup] [--purge-backups] [--dry-run]
python3 -B tools/uninstall_project.py --all-projects (--keep-records | --delete-records) [--home]
```

`--user`(2.21.0)는 사용자 수준 블록·Hook 3개·스킬·`~/.worklog/install.json` 항목을 제거합니다. 프로젝트는 건드리지 않으므로 `.worklog/`가 있는 폴더는 여전히 연결된 폴더이며, 다시 설치하면 그대로 이어집니다. 한 프로젝트를 끊으려면 `--root … --tool all --delete-records`, 잠시 멈추려면 `wl.py off`.
`--root`는 설치기가 프로젝트에 한 일을 되돌립니다(2.17.0): 지침 블록(블록뿐이던 파일은 삭제), Hook 3개(같은 파일의 다른 Hook·설정은 유지, 비게 된 파일은 삭제), 스킬 폴더, 그 도구의 세션 파일·설치 정보, 남는 도구가 없으면 `.lock`·`off`. 연결만 된 폴더(블록·Hook 없이 `install.json`에 scope user 항목)도 "설치됨"으로 잡힙니다. 기록은 사용자가 정합니다 — `--keep-records`는 `works/`·`index.json`·`project.md`를 남기고(다시 설치하면 이어짐; 폴더는 여전히 연결됨을 notes로 알림), `--delete-records`는 `.worklog/`를 통째로 지우며 다른 도구가 아직 설치돼 있으면 거부합니다. `.gitignore`의 `.worklog/` 줄(2.11.0~2.17.x의 두 줄 포함)은 `--delete-records`일 때만 지웁니다(2.21.0: 남긴 기록이 커밋되면 안 되므로). 둘 다 없으면 터미널에서만 묻고 아니면 거부합니다. 고치거나 지우는 파일은 백업하고(`--no-backup`), 설치기의 옛 백업은 `--purge-backups`일 때만 지웁니다. 첫 쓰기 전에 모든 변경을 계획하므로 거부(exit 2)는 아무것도 바꾸지 않습니다. `--all-projects`는 목록의 모든 프로젝트, `--home`은 목록이 빈 뒤 `~/.worklog`를 지웁니다. clone 폴더, Codex Hook 신뢰(`~/.codex/config.toml`), Claude Code 폴더 신뢰는 건드리지 않습니다.

## 도구별 비교

| | Claude Code | Codex | agy (Antigravity CLI, 2.24.0) | Pi (2.24.0) |
|---|---|---|---|---|
| 시작 지침 | `~/.claude/CLAUDE.md` 블록(`--user`) 또는 프로젝트 `CLAUDE.md` 블록(`--root`) | `~/.codex/AGENTS.md` 블록(`--user`) 또는 프로젝트 `AGENTS.md` 블록(`--root`) | 전용 규칙 파일 `~/.gemini/config/rules/worklog.md`(`--user`, frontmatter `trigger: always_on`, 파일당 24,000바이트 상한이라 GEMINI.md는 건드리지 않음) 또는 프로젝트 `.agents/rules/worklog.md`(`--root`) | `~/.pi/agent/AGENTS.md` 블록(`--user`) 또는 프로젝트 `AGENTS.md` 블록(`--root`, codex와 공유) |
| Skill | `~/.claude/skills/worklog` 또는 `.claude/skills/worklog` | `~/.agents/skills/worklog`(공식 문서의 사용자 범위 경로, 2026-10-16) 또는 `.agents/skills/worklog` (`$worklog`로 호출 확인, 2026-10-14) | `~/.gemini/config/skills/worklog`(2026-10-20 실측: 전역 탐색은 `~/.gemini/config/`). 프로젝트 단위는 스킬 없음(`.agents/skills/worklog`는 codex 것) | `~/.pi/agent/skills/worklog` 또는 `.pi/skills/worklog`(프로젝트 신뢰 뒤 로드) |
| Hook 위치 | `~/.claude/settings.json` 또는 `.claude/settings.local.json` | `~/.codex/hooks.json` 또는 `.codex/hooks.json` | `~/.gemini/config/hooks.json` 또는 `.agents/hooks.json`의 이름 붙은 훅 `worklog`(다른 이름의 훅은 유지) | 확장 `~/.pi/agent/extensions/worklog.ts` 또는 `.pi/extensions/worklog.ts`(템플릿 `adapters/pi/worklog.ts`) |
| SessionStart (시작·압축 뒤 주입) | startup·resume·clear·compact·fork¹ → `wl.py hook --tool claude` | startup·resume·clear·compact·fork² → `wl.py hook --tool codex` | `SessionStart` → `wl.py hook --tool agy`(출력 `injectSteps` systemMessage. 새 대화 시작 때 1회이며 `--conversation <id>` 재개 때는 다시 오지 않는다 — 같은 세션 파일로 턴이 이어진다, 2026-10-20 실측) | 확장 `session_start`(startup·resume·fork 등) → `wl.py hook --tool pi`, 주입은 다음 턴의 custom message |
| UserPromptSubmit (턴 시작) | `wl.py turn-start --tool claude` | `wl.py turn-start --tool codex` | `PreInvocation` → `wl.py turn-start --tool agy`(모델 호출마다 오므로 Stop·SessionStart 뒤 첫 PreInvocation만 턴을 올리고 세션 `in_turn`을 켠다. 같은 턴의 나머지는 무시하고 Stop이 `in_turn`을 끈다, 2.24.1. `invocationNum`은 도구 호출을 거치며 0, 1, 2로 증가한다. 2.24.1이 적은 '도구 호출마다 0부터 다시 시작'은 틀린 해석이었고 반복 차단의 원인은 훅 이중 등록이었다. 세션 파일이 마지막 PreInvocation(`invocationNum/initialNumSteps`)과 Stop(`executionNum`)을 기억해 같은 이벤트가 다시 오면 무동작, 2.24.2) | 확장 `before_agent_start`(사용자 프롬프트) → `wl.py turn-start --tool pi` |
| Stop (저장 확인) | `wl.py stop-hook --tool claude` | `wl.py stop-hook --tool codex` | `Stop` → `wl.py stop-hook --tool agy`(차단은 `{"decision": "continue"}`, 취소·오류 종료는 통과) | 확장 `agent_before_settle` → `wl.py stop-hook --tool pi`(차단은 메시지 + `continue: true`) |

¹ `fork`는 `/branch`·`--fork-session`·`/fork`(세션 복사)·백그라운드 전환으로 생긴 분기 세션의 시작(Claude Code 2.1.214+). 그 미만 버전은 분기를 `resume`으로 보고하므로 영향이 없다. 2.12.0부터 설치기가 넣는다.
² Codex는 `/fork`·`/side`(임시 포크 대화)를 `fork`, `/clear`를 `clear`로 보고하며 새 thread id를 쓴다(2026-10-14 실측, codex-cli 0.158.0). SessionStart는 새 thread의 첫 프롬프트 때 발화한다. 2.14.0부터 설치기가 넣는다. hooks.json 내용이 바뀌므로 기존 설치는 재설치 뒤 `/hooks`에서 재신뢰가 필요하다.
| 신뢰 절차 | Hook 승인 불필요. git 저장소면 첫 시작 때 폴더 신뢰 대화상자 1회 | 프로젝트 신뢰 + `/hooks`에서 Hook 3개 신뢰. Hook 정의가 바뀌면 재신뢰. 설치기를 다시 실행해도 같은 설치의 Hook은 그대로 두므로(파일 바이트 유지) 클론을 옮긴 경우에만 재신뢰 | 전역 훅·규칙은 확인 없이 적용(2026-10-20 `agy -p` 실측). 전역 규칙 합계 20,000토큰 예산을 넘으면 규칙이 경로 포인터로 강등되므로 설치 뒤 한 턴 확인 | 사용자 수준 확장은 신뢰 불필요(문서). 프로젝트 확장·스킬은 프로젝트 신뢰(`--approve`) 뒤 로드 |
| 세션 ID | `CLAUDE_CODE_SESSION_ID` (실측) | `CODEX_THREAD_ID` (실측) | `ANTIGRAVITY_CONVERSATION_ID`(셸 환경, 실측) = 훅 입력의 `conversationId` | `PI_SESSION_ID` — 확장이 `session_start`에서 설정 |
| 한계 | — | — | 훅 입력에 cwd가 없어 `workspacePaths[0]`을 루트로 씀. PreInvocation이 모델 호출마다 돔(비용) | 확장이 코어를 자식 프로세스로 부름. 프로젝트 단위 AGENTS.md는 codex와 공유(마지막 설치의 `--tool`이 남음) |

저장 보호는 네 도구 공통입니다: 잠금 + 작업별 신선도 검사(`last_seen`). 마지막으로 읽은 뒤 그 작업의 기록이 바뀌었으면 저장이 거부되고, `show` 후 다시 저장합니다. `writer.json`은 마지막 작성자 정보일 뿐 독점이 아닙니다.

## Hook 동작

- 세 Hook은 stdin 이벤트의 `cwd`와 세션 ID를 씁니다. `--tool`은 그 도구의 세션 환경변수만 고르는 데 씁니다.
- 기록 위치는 이벤트 cwd의 루트 후보입니다(2.25.0): cwd가 연결돼 있으면 cwd, git 안이면 git 최상위까지 올라가며 `.worklog/index.json`이 있는 가장 가까운 폴더, 없으면 git 최상위, git이 아니면 cwd. 그래서 하위 폴더에서 연 세션도 상위 프로젝트의 기록을 읽고 저장합니다. 자세한 경우표: [FORMAT.md](FORMAT.md)의 '루트 후보'.
- 후보에 `.worklog` 폴더가 없으면 SessionStart는 `| NOT_CONNECTED | root=<후보> | auto=on|off | git=yes|no` 한 줄만 주입하고(2.21.0, 세션 파일·갱신 검사 없음) turn-start·stop-hook은 빈 출력으로 통과합니다. 폴더만 있어도(작업이 아직 없어도) 세 Hook이 연결됩니다. 사용자 수준 Hook(`--user`)은 모든 폴더에서 돌지만 이 규칙 때문에 연결 안 한 폴더에서는 아무 일도 하지 않습니다.
- SessionStart 주입이 있으면 턴 시작 `show`를 생략할 수 있고, 없으면 지침대로 `show`를 한 번 실행합니다. 두 경로 모두 같은 작업별 `works/<id>/state.md` 내용입니다.
- 세 Hook은 돌 때마다 세션 파일에 `hooks_seen`을 남깁니다. save·skip 결과의 `hooks`와 `warning`(Hook 미작동 의심: 세 Hook 기록이 하나도 없을 때만, 2.16.0), `verify --all --tool … --session …`의 `hooks`로 Hook이 실제로 도는지 확인합니다. Codex에서 `/hooks` 신뢰를 빠뜨리면 첫 턴의 결과에서 바로 드러납니다. Claude Code에서 `!` 셸 입력이나 서브에이전트·다른 세션의 알림으로 시작한 턴에는 UserPromptSubmit이 돌지 않습니다(2026-10-15 관측). 그런 세션은 `turn_start: false`로만 보이고 경고는 아닙니다.
- 세션 id와 분기(2026-10-13 실측, Claude Code): `/branch`·`/clear`는 새 세션 id로 SessionStart(fork·clear) 주입을 받습니다. `/btw`→`f`·`/subtask`처럼 사용자가 띄운 포크 서브에이전트는 메인 세션 id를 그대로 쓰며 그 id로 저장합니다(메인은 `show`로 확인 뒤 중복 저장하지 않음). `/rewind` 대화 복원은 같은 세션 id이고 모델에게 되감기 표시가 가지 않으므로, 코어가 같은 세션·같은 summary 재저장을 거부합니다(2.13.0). 프로젝트 루트의 `.git`이 파일이면(git worktree) SessionStart 주입과 save·skip·verify·use에 `warning_worktree`가 붙습니다. Codex는 `/fork`·`/side`가 `fork`, `/clear`가 `clear`, `/new`가 `startup`으로 새 thread id를 받습니다(2026-10-14 실측). pi `--fork`는 새 세션 id와 별도 세션 파일을 만들지만 session_start reason이 `startup`이라 `| FORK`가 붙지 않고 `NO_CURRENT_WORK`로 시작합니다(모델이 작업을 묻습니다). agy `/rewind`는 새 대화(새 세션 id)를 만들어 SessionStart가 다시 오고 현재 작업 없이 시작하며 파일은 복원하지 않습니다(되감기로는 산출물 누락 보고가 생기지 않음). agy에는 수동 압축 명령이 없습니다(2026-10-21 확인).
- 산출물 대조(2.15.0): 현재 세션이 기록한 산출물의 파일이 없으면 show·use·SessionStart 주입에 `[Worklog 산출물 없음]`, save·skip 결과에 `artifacts_missing`이 붙습니다(출력에만, state.md에는 없음). 전체 산출물의 존재·해시는 `verify`의 `artifacts`에서 봅니다.
- 같은 Hook이 사용자 수준과 프로젝트 수준에 두 번 등록돼 있으면(claude·codex) 같은 세션의 두 번째 호출은 무동작입니다(2.25.0): SessionStart는 같은 `source`가 5초 안에 다시 오고 그 사이 턴 변화(turn·UserPromptSubmit·Stop)가 없을 때(2.26.0. 사이에 프롬프트나 Stop이 있었으면 다시 주입), UserPromptSubmit은 같은 `turn_id`(Codex)·`prompt_id`가 다시 올 때(id가 없으면 지금처럼 셈), Stop은 앞 Stop이 끝나기 전에 시작해 같은 턴을 판정하려 할 때. `--migrate`로 프로젝트 Hook을 지우는 것이 여전히 기본 해결입니다.
- SessionStart의 `source`가 `fork`면 헤더 끝에 `| FORK`가 붙고(2.25.0), 규칙은 사용자가 작업을 지정하기 전까지 그 곁가지 세션의 save를 막습니다.
- Stop Hook은 save도 skip도 작업 지정(`selected_turn`)도 없는 턴을 한 번 막습니다. 읽기 전용 턴의 예외는 모델이 `skip "이유" --tool <도구>`를 실행하는 데 의존합니다. 막힌 뒤에는 save 또는 skip으로 마칩니다. 턴을 끝내 주는 Stop Hook은 턴 번호를 1 올리므로(2.16.0) UserPromptSubmit 없이 시작한 다음 턴(`!` 셸 입력, 알림)도 자기 save·skip이 있어야 끝납니다.

## 작업 선택 흐름

0. `| NOT_CONNECTED |` 주입이 보이면(연결 안 한 폴더): `auto=on`(기본, 2.25.0)이면 결과를 원하는 첫 요청(구현·분석·설계·질문. 인사·도구 조작·한 줄 확인은 아님)에서 묻지 않고 `new-work "<제목>" --quote "<요청 원문>" --root <root>`로 연결하고 그 턴에 save합니다. 제목을 사용자가 주지 않았으면 요청에서 정하고 첫 summary를 `[auto] 제목 자동: <제목>`으로 시작하며, 답변 끝에 한 줄로 알립니다. `auto=off`면 사용자가 `새 작업: <제목>`이라 할 때만 그렇게 합니다. `<id> 이어서`·`워크로그 켜`에는 연결되지 않았다고 답합니다. `new-work`가 실패하면(`"ok": false`, 쓸 수 없는 폴더) 한 줄로 알리고 요청은 계속합니다.
1. 턴 시작에 `[Worklog worklog/2 SessionStart`가 보이면 사용합니다. 없으면 `show`를 실행합니다.
2. 사용자가 `habit-plan 이어서`라고 하면 모델이 `use habit-plan --quote "habit-plan 이어서"`를 실행합니다. use가 상태를 출력하므로 show 없이 저장합니다. 새 작업은 `새 작업: 요리 메모` → `new-work "요리 메모" --quote "새 작업: 요리 메모"`입니다.
3. 현재 작업도 지정도 없고 기존 작업이 있으면 모델이 요청을 수행하기 전에 목록을 제시하고 "어느 작업에 기록할까요? / 새 작업"을 한 번 묻습니다. 그 턴은 `skip "작업 지정 대기"`로 끝내며 아무것도 저장하지 않습니다. 모델은 기존 작업을 고르지 않습니다(최근·유일·내용 유사를 근거로 삼지 않음). 작업이 하나뿐이고 사용자가 "이어서"라고 하면 그 작업을 use합니다. 기존 작업이 하나도 없으면 묻지 않고 새 작업을 만듭니다. 같은 세션이 같은 턴에 `new-work`를 두 번 하면 코어가 거부합니다(재시도로 생기는 `-2` 작업 방지, 의도했으면 `--force`). 2.26.0부터 폴더를 연결한 첫 턴(턴 0)도 같습니다.
4. 현재 작업은 세션 파일에 남습니다. 압축 뒤에도 같은 작업 전체 상태를 주입합니다. 다른 작업으로 자동 전환하지 않습니다. 새 세션에서는 다시 지정합니다.
5. 작업을 잘못 골랐으면(2.25.0) save 전이면 `use <맞는 id> --quote`, save 뒤면 `reassign <잘못된 id> <맞는 id> --events E0003-E0005 --quote`: 한 잠금 안에서 잘못된 작업에 `[misfiled → …]` CORRECTION(그 사건들이 넣은 결정·제약을 현황에서 뺌), 맞는 작업에 `[refiled ← …]` CORRECTION(같은 결정·제약을 새 번호로, 산출물은 해시 재계산)을 남깁니다. 두 사건은 서로를 가리키지 않습니다: 맞는 작업의 사건은 잘못된 작업의 원래 사건(`refiled_from`)을, 잘못된 작업의 사건은 맞는 작업에 실제로 기록된 사건(`refiled_to`)을 가리킵니다. 사건은 옮기지 않습니다. 2.26.0부터 맞는 작업을 먼저 쓰고, 잘못된 작업의 `refiled_to`는 실제로 기록된 id를 가리킵니다. 같은 글자의 `[모델]` 항목이 맞는 작업에 있으면 옮겨 온 `[사용자]` 항목이 그 자리를 대신합니다(`upgraded`). 어디서 실패해도 결과가 `"partial": true`와 끝난 단계(`done`)이고, 같은 명령을 다시 실행하면 빠진 단계만 합니다(`resumed`). 2.25.0이 남긴 표식이 맞는 작업의 실제 id와 다르면 대상 정정 사건을 하나 더 남깁니다(`corrected_ref`). 자동 제목이 틀렸으면 `rename <id> "<새 제목>" --quote`(index 제목만, CHANGE 사건 한 줄).

`save`가 "현재 작업이 없습니다"로 거부되면 사용자에게 지정을 요청합니다. `use`·`new-work`는 사용자 원문 quote가 필수입니다. 다만 그 원문이 실제 사용자 발언인지까지 기계가 검증하지는 못합니다.

## 켜고 끄기

설치하면 켜진 상태이고 사용자가 끌 때만 꺼집니다. `.worklog/off` 표식 하나로 그 프로젝트 전체(모든 세션·작업)가 꺼집니다. 세 경로가 같은 명령으로 이어집니다: 자연어 `워크로그 꺼 <이유>`·`워크로그 켜`(지침 블록, 두 도구 공통), Skill 인자(Claude `/worklog off <이유>`·`/worklog on`, Codex `$worklog off <이유>`·`$worklog on`), 터미널의 `wl.py off --quote "<사용자 원문>" [--reason "<이유>"]`·`wl.py on`. off는 사용자 원문 `--quote`가 없으면 거부되고 이유는 선택입니다. 꺼진 동안 SessionStart는 `| OFF |` 한 줄만 주입하고, turn-start·stop-hook은 아무것도 하지 않습니다(Stop 차단 없음). Hook 명령은 그대로이므로 Codex 재신뢰가 필요 없습니다. 꺼진 기간은 기록에 남지 않으며, 켠 뒤 그동안 바뀐 것이 있으면 다음 save에 적습니다.

## 형식 1에서 올라오기

`worklog/1`로 기록 중인 프로젝트는 코어가 저장을 거부하고 SessionStart 주입에 이전 안내를 넣습니다. 먼저 dry-run으로 확인한 뒤 `--apply`로 이전합니다. 원장 바이트는 그대로 `works/<id>/`로 옮겨지고 해시를 대조합니다. 자세한 조건: [FORMAT.md](FORMAT.md)의 "이전: 형식 1 → 2".

```sh
python3 -B tools/migrate_v1_to_v2.py --project <프로젝트> --work-id <id> [--title "<제목>"]           # dry-run
python3 -B tools/migrate_v1_to_v2.py --project <프로젝트> --work-id <id> [--title "<제목>"] --apply
```

이전 뒤 설치기를 다시 실행해 지침 블록을 형식 2로 바꿉니다.

## 사용자가 가끔 마주치는 것 (README에서 옮김)

- `save` 결과에 Hook이 살아 있는지(`hooks`, 아니면 `warning`)와 check 인용이 규칙 문장을 그대로 베낀 것인지(`self_quoted`, 반영의 증거가 아님)가 표시됩니다.
- 기록은 실수로 인한 변경은 감지하지만 의도적 변조는 막지 않습니다.
- 되감기(`/rewind`)의 코드 복원은 파일만 되돌리고 기록은 그대로 둡니다. 이 세션이 기록한 산출물이 사라지면 다음 `show`·save 결과에 `[Worklog 산출물 없음]`/`artifacts_missing`으로 표시됩니다(2.15.0). 다른 세션이 지운 파일까지 보려면 `verify`가 모든 산출물의 존재·해시를 대조합니다. 대화 복원 뒤 같은 턴을 다시 저장하면 코어가 거부하고 `show`를 안내합니다(2.13.0).
- git worktree(격리 포크) 안에서 저장한 기록은 본 저장소와 갈라져 병합 때 `.worklog/works/*/events.jsonl`이 충돌합니다. 코어가 `warning_worktree`로 경고합니다. 기록은 본 저장소 세션에서 하세요.
