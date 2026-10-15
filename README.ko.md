# worklog

[English](README.md) · AI 에이전트라면 [AGENT.md](AGENT.md)

**Claude Code와 Codex가 대화 압축이나 새 세션 뒤에도 정한 것을 잊지 않게 합니다.** 설치는 AI에게 시키면 되고, 그 뒤에는 이어서 할 작업의 이름만 말하면 됩니다.

## 어떻게 사용하나

### 설치 — AI에게 시키기

AI에게: `https://github.com/BUGGIEEEEE/worklog 를 clone해서 이 프로젝트에 Worklog 설치해 줘`

에이전트는 먼저 어느 도구(Claude Code · Codex · 둘 다)에 설치할지 묻고, 그 뒤 아래 명령을 실행합니다. clone은 처음 한 번, 연결(install)은 프로젝트·도구마다 한 번입니다. 직접 실행해도 됩니다.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /프로젝트/경로
python3 -B worklog/tools/install_project.py --tool codex  --root /프로젝트/경로
```

사람이 할 일: Codex는 첫 세션에서 프로젝트와 `/hooks`의 Hook 3개를 신뢰, Claude Code는 git 저장소면 폴더 신뢰 대화상자 수락.

설치 확인 — 코어 버전이 출력되면 됩니다(`CHANGELOG.md` 참고):

```sh
python3 -B worklog/core/wl.py version
```

필요한 것: Python 3.9 이상(3.9.6과 3.14에서 시험), macOS 또는 Linux. 클론 폴더는 옮기지 마세요(Hook이 그 경로를 부릅니다). 설치기는 프로젝트 안에만 쓰고 바꾸는 파일은 백업하며, `~/.worklog/installs.json`에 설치한 프로젝트 목록을 적습니다(제거용).

### 작업할 때 하는 말

| 언제 | 하는 말 | 그러면 |
|---|---|---|
| 첫 세션 | `새 작업: 종이 노트 습관 계획 guide` | 작업 `guide`가 생깁니다. id는 제목의 영문·숫자로 만들어집니다(없으면 `work`) |
| 다음 세션 | `guide 이어서. plan.md 써 줘.` | 기록을 받아 이어서 진행합니다 |
| 다른 작업 참조 | `guide에서 정한 시간 배분을 참고해 줘` | 모델이 guide의 기록을 읽어 참고합니다. 가져오는 것은 요청한 내용만입니다 |
| 위임 | 에이전트에게 맡기라고 말하면 됩니다. 별도 세션을 직접 열 때는 첫 프롬프트를 `<id> 이어서. 하위 작업: <이름>`으로 시작하고, 상위 계획과 별개로 끝낼 독립 작업이면 `새 작업: <제목>`과 함께 이어받을 결정·제약을 적어 주세요 | 기록은 에이전트가 규칙대로 남깁니다 |
| 작업이 여러 개일 때 | — | 세션 시작 때 모델이 목록을 보여 주고 어느 작업으로 진행할지 묻습니다 |
| 저장 | — | 턴마다 모델이 저장합니다(읽기 전용 턴은 skip). 사용자가 할 일은 없습니다 |

### 그 밖에 필요할 때

| 언제 | 하는 말 |
|---|---|
| 잠시 끄기 | `워크로그 꺼` (그 프로젝트 전체). `워크로그 켜`로 복귀. 꺼진 동안은 기록 없음 |
| 업데이트 | 새 버전이 있으면 세션 시작 때 한 줄로 알립니다(git clone이면 하루 한 번 배경에서 tag 확인). AI에게 `Worklog 업데이트해 줘` → `python3 -B worklog/core/wl.py update`가 같은 주 번호의 최신 tag로 올리고 현재 프로젝트를 재설치합니다. `update rollback`은 되돌리기, `update --mode off`는 알림 끄기 |
| 현재 상태 보기 | AI에게 `현재 작업 상태 보여 줘`, 또는 `.worklog/works/<id>/state.md`를 열기 |
| 제거 | AI에게 `Worklog 제거해 줘`. 에이전트는 어느 도구를 뺄지 묻고, 마지막 도구를 뺄 때만 기록(`.worklog/`)을 남길지 묻습니다. 예: `python3 -B worklog/tools/uninstall_project.py --root /프로젝트/경로 --tool all --keep-records` (`--delete-records`는 기록까지 삭제, `--tool codex`는 한 도구만). 지침 블록·Hook 3개·스킬·`.gitignore` 줄을 되돌리고 바꾸는 파일은 백업합니다. 완전 제거와 옵션은 [AGENT.md](AGENT.md) |

## 기록의 단위

```
프로젝트/
└── .worklog/                  프로젝트마다 하나
    └── works/                 작업마다 폴더 하나 — 다른 작업의 결정·제약은 섞이지 않음
        ├── guide/
        │   ├── events.jsonl   이력: 모든 결정·결과를 순서대로, 덧붙이기만
        │   └── state.md       현재 상태: 지금 유효한 목표·결정·제약·다음 할 일
        └── report/
```

- 저장할 때마다 이력에 한 줄이 추가되고, 현재 상태는 이력에서 다시 계산됩니다. 값을 바꾸면 이전 결정은 이력에 남고 현재 상태에는 최신만 남습니다.
- Claude Code와 Codex는 같은 `.worklog/`를 함께 씁니다. git 프로젝트면 `.gitignore`에 `.worklog/`가 추가됩니다(기록은 기기별 상태이고 사용자 발언을 인용하므로 git 밖에 둡니다).
- 프로젝트에 생기는 것: `CLAUDE.md` 또는 `AGENTS.md`의 규칙 블록 하나(기존 내용은 그대로), Hook 3개, `skills/worklog/`(Claude: `.claude/`, Codex: `.agents/`), `.gitignore` 한 줄.

## 어떻게 동작하나 (그림)

세션 1에서 정한 결정·제약이 새 세션에서도, 긴 대화를 여러 번 압축한 뒤에도 그대로 적용됩니다.

![예시: 세션 1에서 정한 것이 세션 2와 압축 뒤에도 유지됨](docs/img/ko-03-example.png)

Worklog가 모델의 입력에 더하는 것은 두 층뿐입니다. 규칙 블록(항상 같음)과 세션 시작 때 붙는 기록 요약입니다. 사용자 메시지는 바뀌지 않습니다. 숫자는 2026-10-15에 Claude opus로 전·후 각 1회 측정한 값입니다.

![세션 2의 첫 턴에 모델이 받는 것: Worklog 전과 후의 층과 글자 수](docs/img/ko-04-context.png)

기록 요약의 실제 글자와, 모델이 거기서 읽어 내는 것입니다.

![기록 요약(주입)의 구조와 모델이 읽어 내는 것](docs/img/ko-05-injection.png)

한 턴이 실제로 흘러가는 순서입니다. 사용자 · Worklog 도구 · 모델이 각각 하는 일을 시간 순으로 보여 줍니다.

![Worklog가 있을 때 한 턴의 흐름](docs/img/ko-06-flow.png)

## 알아 둘 것

- **Claude Code와 Codex가 동일하게 작동합니다.** 두 도구 모두 모델 입력에 규칙 블록과 기록 요약이 같은 방식으로 들어가고, 한 프로젝트의 같은 `.worklog/`를 읽고 씁니다. 다른 점은 설정 파일 이름뿐입니다. Pi는 지원 예정이며 현재 미검증입니다. 모델 지침과 메시지는 한국어입니다.

  | | 규칙 블록이 있는 파일 | Hook 설정 |
  |---|---|---|
  | Claude Code | `CLAUDE.md` | `.claude/settings.local.json` |
  | Codex | `AGENTS.md` | `.codex/hooks.json` |

- **다른 창에서 같은 작업을 고쳤다면**: 기록 요약은 세션 시작 때 한 번 들어오므로 그 사이 다른 세션이 저장할 수 있습니다. 이 세션이 저장할 때 도구가 "기록이 바뀌었습니다"로 거부하고 모델이 기록을 다시 읽어 저장합니다. 사용자가 할 일은 없습니다.
- 되감기(`/rewind`)·git worktree·산출물 삭제처럼 기록과 실제가 어긋날 수 있는 상황은 도구가 경고로 알려 줍니다. 자세한 내용은 [docs/ADAPTERS.md](docs/ADAPTERS.md).
- 기록은 실수로 인한 변경은 감지하지만 의도적 변조는 막지 않습니다.

상세: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · 라이선스 MIT([LICENSE](LICENSE))
