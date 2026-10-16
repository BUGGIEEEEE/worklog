# worklog

[English](README.md) · AI 에이전트라면 [AGENT.md](AGENT.md)

**Claude Code와 Codex가 대화 압축이나 새 세션 뒤에도 정한 것을 잊지 않게 합니다.** 설치는 AI에게 시키면 되고, 그 뒤에는 이어서 할 작업의 이름만 말하면 됩니다.

![1. 기록의 단위](docs/img/ko-01-units.png)

기기에 생기는 것(도구마다 한 번): 사용자 지침 파일(`~/.claude/CLAUDE.md` 또는 `~/.codex/AGENTS.md`)의 규칙 블록 하나(기존 내용은 그대로), Hook 3개(`~/.claude/settings.json` 또는 `~/.codex/hooks.json`), `skills/worklog/`(Claude: `~/.claude/`, Codex: `~/.agents/`). 프로젝트에 생기는 것: 첫 `새 작업:` 때 `.worklog/`와, git 프로젝트면 `.gitignore`의 `.worklog/` 줄(기록은 기기별 상태이고 사용자 발언을 인용하므로 git 밖에 둡니다). 그 전까지는 어느 폴더를 열어도 Worklog가 아무것도 하지 않습니다.

![2. 어떻게 사용하나](docs/img/ko-02-usage.png)

복사용 문구: `새 작업: <제목>` · `<id> 이어서` · `<id>에서 정한 <것>을 참고해 줘` · `워크로그 꺼` / `워크로그 켜` · `Worklog 업데이트해 줘` · `현재 작업 상태 보여 줘` · `Worklog 제거해 줘`

설치 — AI가 실행하는 명령(직접 실행해도 됩니다. clone은 처음 한 번, install은 도구마다 한 번이고 기기 전체에 적용됩니다. 한 프로젝트에만 설치하려면 `--user` 대신 `--root /프로젝트/경로`):

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --user
python3 -B worklog/tools/install_project.py --tool codex  --user
```

설치 확인 — 코어 버전이 출력되면 됩니다(`CHANGELOG.md` 참고):

```sh
python3 -B worklog/core/wl.py version
```

제거 — 에이전트가 어느 도구에서 뺄지 묻습니다. 프로젝트의 기록 `.worklog/`는 그대로 남습니다(한 프로젝트의 기록을 지우려면 `--root /프로젝트/경로 --tool all --delete-records`). 예(`--tool codex`는 한 도구만):

```sh
python3 -B worklog/tools/uninstall_project.py --user --tool all
```

- 필요한 것: Python 3.9 이상(3.9.6과 3.14에서 시험), macOS 또는 Linux. 클론 폴더는 옮기지 마세요(Hook이 그 경로를 부릅니다). 설치기는 도구의 설정 파일만 바꾸고 바꾸는 파일은 백업합니다. 연결된 프로젝트 목록은 `~/.worklog/installs.json`에 적힙니다(제거용).
- 업데이트: git clone이면 하루 한 번 세션 시작 때 배경에서 origin의 tag를 확인하고, 새 버전이 있으면 다음 세션이 한 줄로 알립니다. `wl.py update`는 같은 주 번호의 최신 tag로 올리고 기기의 설치(규칙 블록·스킬)를 재설치합니다. `update rollback`은 되돌리기, `update --mode off`는 알림 끄기.
- 위임: 에이전트에게 맡기라고 말하면 됩니다. 별도 세션을 직접 열 때는 첫 프롬프트를 `<id> 이어서. 하위 작업: <이름>`으로 시작하고, 상위 계획과 별개로 끝낼 독립 작업이면 `새 작업: <제목>`과 함께 이어받을 결정·제약을 적어 주세요. 기록은 에이전트가 규칙대로 남깁니다.
- 완전 제거(모든 프로젝트 + `~/.worklog`)와 제거 옵션: [AGENT.md](AGENT.md).

![3. 예시](docs/img/ko-03-example.png)

![4. 세션 2의 첫 턴에 모델이 받는 것 — 전 / 후](docs/img/ko-04-context.png)

![5. 주입의 구조](docs/img/ko-05-injection.png)

![6. Worklog가 있을 때 한 턴의 흐름](docs/img/ko-06-flow.png)

![7. 참고 사항](docs/img/ko-07-notes.png)

상세: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · 라이선스 MIT([LICENSE](LICENSE))
