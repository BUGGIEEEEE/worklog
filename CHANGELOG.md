# Changelog

Tags are set by the author only; an external PR gets a tag only after the author merges and reviews it.
Numbering: a ledger-structure change bumps `FORMAT` and the major number (3.0.0, with a migration script); every other change bumps the minor number (2.2.0). `python3 -B core/wl.py version` prints the installed number.

tag는 작성자만 붙인다. 번호: 원장 구조 변경 = FORMAT과 주 번호(3.0.0, 마이그레이션 동반), 그 외 = 부 번호(2.2.0). `python3 -B core/wl.py version`으로 설치된 번호를 확인한다.

## 2.1.0 — 2026-10-10
Per-decision `source: "model"` for model proposals saved in a user event; constraint sentences stay out of artifact bodies even paraphrased; turn-limited instructions are not constraints; `self_quoted` on checks that quote the rule text; `hooks_seen` self-diagnosis; `[사용자]`/`[모델]` source tags; Python 3.9 support.
결정별 `source: "model"`(사용자 사건 안의 모델 제안), 제약 문장 본문 전사 금지, 턴 한정 지시 제외, `self_quoted`, `hooks_seen`, 출처 태그, Python 3.9 지원.
