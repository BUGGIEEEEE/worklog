# worklog

[English](README.md) · 설치·업데이트를 맡은 AI 에이전트라면 [AGENT.md](AGENT.md)를 읽으세요.

**Claude Code와 Codex는 대화가 압축되거나 새 세션이 시작되면 무엇을 정했는지 잊어버립니다. worklog는 그것을 적게 하고, 다시 읽게 합니다.** 프로젝트마다 한 번 설치하면 그 뒤로 할 일은 없습니다.

## 무엇을 해 주나

- 모델이 작업마다 목표·결정·제약·다음 할 일을 프로젝트 폴더의 `.worklog/`에 적고, 세션 시작과 압축 직후에 자동으로 다시 읽습니다.
- 저장(또는 읽기만 했다는 선언) 없이는 턴을 끝내지 못합니다. Hook이 돌려보냅니다.
- 한 프로젝트에 작업을 여러 개 둘 수 있습니다. 어느 작업인지는 사용자가 말합니다: `<id> 이어서` 또는 `새 작업: <제목>`. 모델이 추측하지 않습니다.
- Claude Code와 Codex가 같은 기록을 함께 씁니다.

## 설치

필요한 것: Python 3(표준 라이브러리만 사용. 3.14에서 시험했고 3.10 이상에서 동작할 것으로 예상), macOS 또는 Linux. Claude Code 2.1.x, Codex CLI 0.15x에서 확인했습니다.

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git
python3 -B worklog/tools/install_project.py --tool claude --root /프로젝트/경로   # Claude Code
python3 -B worklog/tools/install_project.py --tool codex  --root /프로젝트/경로   # Codex
```

그다음 프로젝트마다 한 번:

- **Codex:** 프로젝트를 신뢰하고, `/hooks`에서 Worklog Hook 3개를 신뢰합니다.
- **Claude Code:** 프로젝트가 git 저장소면 첫 시작 때 폴더 신뢰 대화상자를 수락합니다.

클론한 폴더는 옮기지 마세요. Hook이 그 경로를 부릅니다. 설치기는 프로젝트 안에만 쓰고, 바꾸는 파일은 모두 백업합니다. 이 페이지 주소를 Claude Code나 Codex에 주고 설치해 달라고 해도 됩니다. [AGENT.md](AGENT.md)를 따릅니다.

## 사용

- **첫 세션:** `새 작업: <제목>`이라고 말합니다. 다음 세션부터는 작업 목록이 보이고, `<id> 이어서`라고 말하면 됩니다.
- **지금 상태:** `.worklog/works/<id>/state.md`를 엽니다.
- **어떤 프로젝트에서 잠시 끄기:** `워크로그 꺼`라고 말합니다. 그 프로젝트 전체가 멈추고, 꺼진 동안은 기록에 남지 않습니다. `워크로그 켜`라고 말하면 다시 켜집니다. 설치기를 돌리지 않은 프로젝트는 아무 영향이 없습니다.

## 업데이트

```sh
cd worklog && git pull
python3 -B worklog/tools/install_project.py --tool claude --root /프로젝트/경로   # 프로젝트마다 다시
python3 -B worklog/tools/install_project.py --tool codex  --root /프로젝트/경로
```

`git pull`은 코어를 갱신합니다. 설치기를 다시 돌려야 프로젝트 안의 지침이 갱신됩니다. Hook은 그대로 두므로 Codex가 다시 신뢰를 묻지 않습니다.

## 한계

- 제약을 산출물 파일 안에 넣을지는 여전히 모델의 판단입니다. 검증 12회에서는 내용 제약이 모두 반영됐지만 조건당 1회뿐이었습니다. 중요하면 "제약도 파일에 넣어"라고 말하세요.
- 기록은 과거 항목의 실수에 의한 변경은 감지하지만, 의도적 변조를 막는 장치는 아닙니다.
- Pi: 지침만 있고 Hook이 없어 강제되지 않으며, 미검증입니다.

상세: [docs/ADAPTERS.md](docs/ADAPTERS.md)(도구별 설정, 복구, `worklog/1`에서 이전), [docs/FORMAT.md](docs/FORMAT.md)(기록 형식), [docs/VERIFICATION.md](docs/VERIFICATION.md)(검증 결과).

## 라이선스

MIT — [LICENSE](LICENSE) 참조.
