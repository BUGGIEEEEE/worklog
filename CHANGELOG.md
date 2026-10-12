# Changelog

Tags are set by the author only; an external PR gets a tag only after the author merges and reviews it.
Numbering: a ledger-structure change bumps `FORMAT` and the major number (3.0.0, with a migration script); every other change bumps the minor number (2.2.0). `python3 -B core/wl.py version` prints the installed number.

tag는 작성자만 붙인다. 번호: 원장 구조 변경 = FORMAT과 주 번호(3.0.0, 마이그레이션 동반), 그 외 = 부 번호(2.2.0). `python3 -B core/wl.py version`으로 설치된 번호를 확인한다.

## 2.3.0 — 2026-10-12
Every new event records the core that wrote it (`"core": "2.3.0"`). When a ledger holds an event written by a newer core, show/use text, save results and verify results carry `warning_core` (never refuses; events without `core` never warn). Prepares older copies to notice a newer one before external users exist. No reinstall needed.
새 사건마다 쓴 코어 번호(`"core": "2.3.0"`)를 기록한다. 더 새 코어가 쓴 사건이 있으면 show·use 텍스트, save·verify 결과에 `warning_core`를 붙인다(거부 없음, `core` 없는 옛 사건은 경고 없음). 외부 사용자가 생기기 전에 옛 사본이 새 사본을 알아차리게 하는 준비. 재설치 불필요.

## 2.2.0 — 2026-10-12
Installer writes `.worklog/install.json` (per tool: version, sha256 of the `adapters/rules.md` it installed from); the core compares it with its own rules file and adds `warning_install` to save/skip/verify results, the `use` text and the SessionStart injection when they differ (never refuses; missing or broken manifest = no warning). Literal `[사용자]`/`[모델]` tags at either end of a decision or constraint text are dropped at save (the core adds the tag itself).
설치기가 `.worklog/install.json`(도구별 version·설치 원본 `adapters/rules.md`의 sha256)을 쓰고, 코어가 자기 규칙 파일과 대조해 다르면 save·skip·verify 결과, use 텍스트, SessionStart 주입에 `warning_install`을 붙인다(거부 없음, 파일 없음·깨짐은 경고 없음). 결정·제약 글자 앞뒤의 `[사용자]`/`[모델]`은 저장 때 지운다(태그는 코어가 붙인다).

## 2.1.0 — 2026-10-10
Per-decision `source: "model"` for model proposals saved in a user event; constraint sentences stay out of artifact bodies even paraphrased; turn-limited instructions are not constraints; `self_quoted` on checks that quote the rule text; `hooks_seen` self-diagnosis; `[사용자]`/`[모델]` source tags; Python 3.9 support.
결정별 `source: "model"`(사용자 사건 안의 모델 제안), 제약 문장 본문 전사 금지, 턴 한정 지시 제외, `self_quoted`, `hooks_seen`, 출처 태그, Python 3.9 지원.
