# worklog

[English](README.md)

AI 코딩 에이전트(Claude Code, Codex, Pi)가 함께 쓰는 추가 전용 작업 원장(ledger, 고쳐 쓰지 않고 뒤에 덧붙이기만 하는 기록)입니다. 대화 압축이나 새 세션 뒤에도 목표·결정·제약·다음 행동을 이어가게 하고, Hook으로 턴 끝 저장을 강제합니다.

## 왜 필요한가

대화가 압축되거나 새 세션이 시작되면 에이전트는 맥락을 잃습니다. 목표가 흐려지고, 앞선 결정을 잊고, 사용자가 말한 제약("알림은 만들지 말 것", "다른 프로젝트는 건드리지 말 것")이 최종 산출물에서 조용히 빠집니다. 메모와 이력을 다시 읽어 맥락을 복원하는 데도 비용이 큽니다.

같은 작업을 나란히 비교한 결과(2026-09-30), 원장 없이(기본 메모만) 작업하면 도구 호출 9회·약 0.44M 토큰, 이 도구의 이전 버전(0.3.0)은 58회·약 3.1M 토큰이 들었습니다. 재설계한 현재 코어는 5~8회·약 0.2~0.5M 토큰(검증 12회)으로, 이전 버전의 약 10분의 1이며 원장 없이 작업할 때와 같은 수준입니다.

## 동작 방식

```
save (턴마다 한 번)    →  .worklog/events.jsonl    추가 전용·해시 연결 원장
                       →  .worklog/state.json/.md  현재 상태(원장에서 다시 계산)
SessionStart Hook      →  시작·재개·압축 뒤 state.md 주입
UserPromptSubmit Hook  →  턴 수 세기
Stop Hook              →  save도 skip도 없는 턴의 종료를 막음
skip "이유"            →  읽기 전용 턴 표시. 원장에 쓰지 않음
```

사건 하나가 JSON 한 줄이며 직전 줄과 sha256으로 연결됩니다. 뒤에 사건이 이어진 과거 줄을 바꾸면 읽을 때 감지됩니다. 마지막 사건은 독립적인 기준점이 없어 감지 대상이 아니며, 악의적 변조를 막는 장치가 아닙니다. 상태 파일은 원장의 투영(원장에서 계산해 낸 결과)이라 원장과 다르면 원장이 기준이고 `show`가 다시 만듭니다. 전체 형식은 [docs/FORMAT.md](docs/FORMAT.md)에 있습니다.

## 요구 사항

- Python 3.10 이상, 표준 라이브러리만 사용.
- macOS 또는 Linux(`flock` 사용).
- Claude Code 2.1.x, Codex CLI 0.15x에서 확인.

## 설치

```sh
git clone https://github.com/BUGGIEEEEE/worklog.git && cd worklog
```

그다음 연결할 프로젝트마다:

```sh
python3 -B tools/install_project.py --tool claude --root /path/to/project   # Claude Code
python3 -B tools/install_project.py --tool codex  --root /path/to/project   # Codex
```

`--dry-run`을 붙이면 바뀔 내용만 보여 줍니다. 설치기는 `--root` 안에만 씁니다. 쓰기 대상 전부(파일·백업·새 디렉터리·`.worklog`) 중 하나라도 링크를 거쳐 밖으로 이어지면 거부하고, `.worklog`가 링크면 안쪽을 가리켜도 거부합니다. 바꾸는 파일은 `<파일>.bak-worklog-<날짜시각>`으로 백업하되 같은 이름이 있으면 `-1`, `-2`…를 붙여 덮어쓰지 않으며, 다시 실행해도 관리 블록과 Worklog Hook(예전 저장소 위치의 것 포함)이 중복되지 않고 교체됩니다. 쓰기 전에 모든 대상을 검사하고 내용을 준비하므로, 거부(exit 2, 예: 읽을 수 없는 Hook 설정 파일)되면 아무것도 바뀌지 않습니다.

그래도 쓰는 도중 실패하면(디스크·권한 오류 등) 바뀐 파일은 `<파일>.bak-worklog-<날짜시각>` 사본으로 되돌리고, 백업이 없는 파일(새로 생긴 파일)은 지운 뒤 설치기를 다시 실행합니다.

생기는 것:

| 도구 | 파일 |
|---|---|
| Claude Code | `CLAUDE.md` 지침 블록 · `.claude/settings.local.json`의 Hook 3개 · `.claude/skills/worklog/SKILL.md` · 빈 `.worklog/` |
| Codex | `AGENTS.md` 지침 블록 · `.codex/hooks.json`의 Hook 3개 · `.agents/skills/worklog/SKILL.md` · 빈 `.worklog/` |
| Pi (`--tool pi`) | `AGENTS.md` 지침 블록 · `.pi/skills/worklog/SKILL.md` (Hook 없음) |

빈 `.worklog/` 폴더가 연결 표시입니다. 이 폴더가 없는 곳에서는 Hook이 아무것도 하지 않습니다. 원장 파일은 첫 `save`가 만듭니다.

Hook은 `core/wl.py`를 절대 경로로 부르므로, 내려받은 폴더를 옮기지 마세요(옮겼다면 설치기를 다시 실행).

처음 한 번 필요한 신뢰 절차:

- **Codex:** 프로젝트를 신뢰하고, `/hooks`에서 Hook 3개를 신뢰합니다. Hook 정의가 바뀌면 다시 신뢰해야 합니다.
- **Claude Code:** 프로젝트가 git 저장소면 첫 시작 때 폴더 신뢰 대화상자가 한 번 나옵니다.

도구별 세부: [docs/ADAPTERS.md](docs/ADAPTERS.md).

## 일상 사용

설치된 지침이 모델에게 요구하는 것:

- **턴 시작:** 마지막 압축 이후 현재 상태를 보지 못했다면(SessionStart 주입이나 자기 마지막 save 결과로) `show`를 한 번 실행.
- **턴 끝:** stdin JSON으로 `save`를 한 번 실행. 사용자 요청·결정은 원문 일부를 `quote`에 넣고, 제약은 사용자가 바꾸기 전까지 유지.
- **읽기 전용 턴:** save 대신 `skip "이유"`.
- **산출물:** `artifacts`를 넣은 save는 유효한 결정·제약마다 산출물 본문을 `check`해야 합니다. 본문 문장을 그대로 인용하거나 `미반영: <이유>`를 적습니다.

사람이 현황을 볼 때는 `.worklog/state.md`를 엽니다.

| 명령 | 용도 |
|---|---|
| `wl.py show` | 현재 상태 출력(이 세션이 읽었다고 표시) |
| `wl.py save` | stdin JSON으로 사건 하나 추가, 검증 후 상태 재계산 |
| `wl.py skip "이유"` | 읽기 전용 턴 선언. 원장에 쓰지 않음 |
| `wl.py verify` | state.json/state.md가 원장과 일치하는지 확인 |
| `wl.py hook` | SessionStart Hook: state.md 주입 |
| `wl.py turn-start` | UserPromptSubmit Hook: 턴 수 세기 |
| `wl.py stop-hook` | Stop Hook: save도 skip도 없는 턴을 막음 |

`wl.py help`가 save 입력 형식을 보여 줍니다. 모델용 지침과 CLI 메시지는 현재 한국어입니다.

## 여러 도구가 한 프로젝트를 쓸 때

여러 도구·세션이 한 `.worklog/`를 함께 써도 됩니다. 저장은 잠금(lock)으로 한 번에 하나씩 처리되고, 이 세션이 마지막으로 읽은 뒤 다른 세션이 저장했다면 거부됩니다("기록이 바뀌었습니다") — 모델은 `show` 후 다시 저장합니다. 독점 소유자는 없습니다. 사용자가 명시적으로 작업을 넘길 때는 save에 `takeover`(사유)와 사용자 원문 `quote`를 넣어 기록할 수 있습니다.

## 한계

- Pi는 Hook 없이 지침만 씁니다. 강제되지 않으며 검증하지 않았습니다.
- 제약을 산출물 본문에 넣을지는 여전히 모델 판단입니다. 모델이 미반영으로 신고한 제약이 없는 회차는 8/12이고, 본문 키워드 검사 기준으로는 7/12입니다(sonnet-medium은 신고 없이 문구 1개 생략). 그래서 지침에 한 줄로 명시했습니다.
- 검증은 조건마다 1회씩만 했습니다.
- 전역(사용자 수준) Hook과 함께 쓸 때의 영향은 확인하지 않았습니다.

검증 세부: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## 형식 안정성

기록 형식은 `worklog/1`입니다. 형식을 바꾸면 기존 원장을 다시 이전해야 합니다. 기존 원장의 뜻이 그대로인 추가만 같은 형식 번호를 유지합니다.

## 시험

```sh
python3 -B -m unittest discover -s tests
```

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
