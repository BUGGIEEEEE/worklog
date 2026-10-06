# worklog

[English](README.md)

**프로젝트마다 한 번 설치하면 끝입니다. 그 뒤로 할 일은 없습니다.** Claude Code와 Codex가 작업의 핵심 — 목표·결정·제약·다음 할 일 — 을 프로젝트 폴더의 `.worklog/`에 기록하고, 세션을 시작하거나 대화가 압축될 때 자동으로 다시 읽습니다.

## 무엇을 해 주나

- **압축·새 세션 뒤에도 맥락을 잇습니다.** 세션 시작과 압축 직후에 현재 상태가 모델에 주입되므로, 모델이 추측하지 않고 기록에서 이어 갑니다.
- **기록 없이 턴을 끝내지 못하게 합니다.** 모델이 저장(또는 읽기 전용 선언) 없이 턴을 마치려 하면 Stop Hook이 돌려보내 저장하게 합니다.
- **작업 단위로 나눠 기록합니다.** 한 프로젝트에 여러 작업을 둘 수 있습니다. 세션 시작 때 모델이 작업 목록을 보여 주고, 사용자가 `<id> 이어서` 또는 `새 작업: <제목>`으로 지정합니다. 지정 전에는 저장하지 않고, 지정이 없으면 모델이 묻습니다.
- **여러 도구가 기록 하나를 함께 씁니다.** Claude Code와 Codex가 같은 프로젝트를 번갈아 작업해도 되며, 서로의 기록을 읽은 뒤에 씁니다.

## 설치

필요한 것: Python 3(표준 라이브러리만 사용. 3.14에서 개발·시험했고 3.10 이상에서 동작할 것으로 예상), macOS 또는 Linux. Claude Code 2.1.x, Codex CLI 0.15x에서 확인했습니다.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /프로젝트/경로   # Claude Code
python3 -B worklog/tools/install_project.py --tool codex  --root /프로젝트/경로   # Codex
```

그다음 프로젝트마다 한 번:

- **Codex:** 프로젝트를 신뢰하고, `/hooks`에서 Worklog Hook 3개를 신뢰합니다.
- **Claude Code:** 프로젝트가 git 저장소면 첫 시작 때 폴더 신뢰 대화상자를 수락합니다.

설치기는 프로젝트 안에만 씁니다(`CLAUDE.md`/`AGENTS.md`의 지침 블록, Hook 3개, Skill, 빈 `.worklog/`). 바꾸는 파일은 모두 백업하며 다시 실행해도 안전합니다. 클론한 폴더는 옮기지 마세요 — Hook이 절대경로로 호출합니다. 도구별 상세, Pi, 복구 방법: [docs/ADAPTERS.md](docs/ADAPTERS.md).

## 설치 뒤

평소처럼 작업하면 됩니다.

- **첫 세션에서:** `새 작업: <제목>`이라고 말해 첫 작업을 만듭니다.
- **지금 상태가 궁금하면:** `.worklog/works/<id>/state.md`를 엽니다(목표·유효 결정·제약·다음 할 일).
- **결정을 바꾸거나 제약을 풀고 싶으면:** 대화로 말하면 됩니다. 모델이 그 말을 인용해 기록하며, 제약은 사용자의 말이 있을 때만 해제됩니다.
- **뭔가 이상하면:** 프로젝트 폴더에서 `python3 -B worklog/core/wl.py verify --all`을 실행합니다. 상태 파일은 작업별 원장(`.worklog/works/<id>/events.jsonl`)의 투영이며 `show`가 원장에서 다시 만듭니다.
- **`worklog/1`을 쓰던 프로젝트면:** `python3 -B worklog/tools/migrate_v1_to_v2.py --project /프로젝트/경로 --work-id <id>`로 미리 보고, `--apply`를 붙여 이전한 뒤 설치기를 다시 실행합니다.

## 한계 — 믿고 쓰기 전에 읽을 것

- **제약을 산출물 파일 안에 넣을지는 여전히 모델의 판단입니다.** 검증 12회 중 모델이 모든 제약을 반영했다고 보고한 회차는 8회, 산출물 키워드 검사로는 7회였습니다. 중요하면 "제약도 파일에 넣어"라고 말하세요.
- **원장은 과거 기록의 실수에 의한 변경은 감지하지만, 의도적 변조를 막는 장치는 아닙니다.** 각 기록은 직전 기록과 해시로 연결되지만 마지막 기록은 독립된 기준점이 없습니다.
- Pi: 지침만 있고 Hook이 없어 강제되지 않으며, 미검증입니다. 검증은 조건당 1회였습니다. 사용자의 전역 Hook과의 상호작용은 확인하지 않았습니다.

검증 결과: [docs/VERIFICATION.md](docs/VERIFICATION.md). 기록 형식 `worklog/2`(안정. 형식을 바꾸면 기존 원장을 다시 이전해야 함): [docs/FORMAT.md](docs/FORMAT.md). 모델 지침과 CLI 메시지는 한국어입니다.

## 시험

```sh
python3 -B -m unittest discover -s tests
```

## 라이선스

MIT — [LICENSE](LICENSE) 참조.
