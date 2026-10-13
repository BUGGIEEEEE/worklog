# worklog

[English](README.md) · AI 에이전트라면 [AGENT.md](AGENT.md)

**Claude Code와 Codex가 대화 압축이나 새 세션 뒤에도 정한 것을 잊지 않게 합니다.** 프로젝트마다 한 번 설치하면 그 뒤로 할 일은 없습니다.

## 어떻게 동작하나

```
설치 (프로젝트마다 한 번)
   │
   ▼
세션 시작 ──── 모델이 .worklog/ 기록을 읽는다
   │             작업이 여러 개면 묻는다 → 사용자: "<id> 이어서" 또는 "새 작업: <제목>"
   ▼
작업 진행 ──── 턴마다 목표·결정·제약·다음 할 일을 저장한다
   │             저장 없이는 턴이 끝나지 않는다 (Hook이 돌려보냄)
   ▼
압축·새 세션 ── 기록을 다시 읽고 이어서 진행한다
```

## 프로젝트에 무엇이 생기나

```
프로젝트/
├── .worklog/works/<id>/state.md   지금 상태. 열면 목표·결정·제약·다음 할 일이 보임
├── CLAUDE.md 또는 AGENTS.md       모델 지침 블록 하나 (기존 내용은 그대로)
├── Hook 3개                        세션 시작에 읽기, 턴 끝에 저장 확인
├── .gitignore                     git 프로젝트만: .worklog/sessions/와 .worklog/.lock 추가 (works/의 기록은 커밋, 세션 파일은 무시)
└── skills/worklog/                `/worklog on|off` 호출용 스킬 파일 (Claude: .claude/, Codex: .agents/)
```

Claude Code와 Codex는 같은 `.worklog/`를 함께 씁니다.

## 사용자가 할 일

| 언제 | 할 일 |
|---|---|
| 설치 | 아래 명령. Codex는 프로젝트와 `/hooks`의 Hook 3개를 신뢰, Claude Code는 git 저장소면 폴더 신뢰 대화상자 수락 |
| 첫 세션 | `새 작업: <제목>` |
| 다음 세션 | 목록에서 골라 `<id> 이어서` |
| 위임 | 에이전트에게 맡기라고 말하면 됩니다. 별도 세션을 직접 열 때는 첫 프롬프트를 `<id> 이어서. 하위 작업: <이름>`으로 시작하고, 상위 계획과 별개로 끝낼 독립 작업이면 `새 작업: <제목>`과 함께 이어받을 결정·제약을 적어 주세요. 기록은 에이전트가 규칙대로 남깁니다 |
| 잠시 끄기 | `워크로그 꺼` (그 프로젝트 전체). `워크로그 켜`로 복귀. 꺼진 동안은 기록 없음 |
| 업데이트 | git clone이면 하루 한 번 세션 시작 때 배경에서 origin의 tag를 확인하고(기다리지 않음), 새 버전이 있으면 다음 세션이 한 줄로 알린다. 스스로 바꾸는 것은 없다: `python3 -B worklog/core/wl.py update`를 치면 같은 주 번호의 최신 tag로 fast-forward 하고 현재 프로젝트를 재설치한다. `update rollback`은 되돌리기, `update --mode off`는 알림 끄기. 새 주 버전은 알리기만 한다. Hook은 그대로라 재신뢰 없음 |

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /프로젝트/경로
python3 -B worklog/tools/install_project.py --tool codex  --root /프로젝트/경로
```

설치 확인: `python3 -B worklog/core/wl.py version`이 코어 버전을 출력합니다(`CHANGELOG.md` 참고).

필요한 것: Python 3.9 이상(3.9.6과 3.14에서 시험), macOS 또는 Linux. 클론 폴더는 옮기지 마세요(Hook이 그 경로를 부릅니다). 설치기는 프로젝트 안에만 쓰고, 바꾸는 파일은 백업합니다.

## 알아 둘 것

- `save` 결과에 Hook이 살아 있는지(`hooks`, 아니면 `warning`)와 check 인용이 규칙 문장을 그대로 베낀 것인지(`self_quoted`, 반영의 증거가 아님)가 표시됩니다.
- 기록은 실수로 인한 변경은 감지하지만 의도적 변조는 막지 않습니다.
- Pi는 미검증입니다. 모델 지침과 메시지는 한국어입니다.

상세: [docs/ADAPTERS.md](docs/ADAPTERS.md) · [docs/FORMAT.md](docs/FORMAT.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · 라이선스 MIT([LICENSE](LICENSE))
