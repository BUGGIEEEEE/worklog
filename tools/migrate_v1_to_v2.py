#!/usr/bin/env python3
"""Format 1 → 2: move <project>/.worklog/{events.jsonl, state.*, writer.json} into .worklog/works/<id>/ unchanged.

usage: migrate_v1_to_v2.py --project <root> --work-id <id> [--title "<제목>"] [--apply]
Default is a dry run (nothing written). --apply moves the ledger bytes as they are (os.replace), writes index.json,
rebuilds state.json/state.md as worklog/2 and deletes the regular .worklog/sessions/*.json files. Line hashes are
compared before and after. Runs only when a format-1 ledger exists and neither works/ nor index.json does; a rerun is
refused. Every precondition (regular files, no links, empty target) is checked before the first change and again
inside .worklog/.lock. Writes and deletes nothing outside <project>/.worklog. Standard library only.
"""
import argparse, importlib.util, json, os, sys
from contextlib import nullcontext
from pathlib import Path

WL_PATH = Path(__file__).resolve().parents[1] / "core" / "wl.py"
_spec = importlib.util.spec_from_file_location("wl", WL_PATH)
wl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wl)

MOVE = ("events.jsonl", "state.json", "state.md", "writer.json")


def line_hashes(path):
    return [wl.sha(raw) for raw in path.read_bytes().splitlines() if raw.strip()]


def preconditions(d):
    """Every refusal before any write or delete; returns (session files to delete, skipped names).
    Run again inside the lock: a concurrent second run then sees works/ and gets "이미 형식 2"."""
    if os.path.lexists(d / "works") or os.path.lexists(d / "index.json"):
        raise wl.Reject(f"이미 형식 2입니다({d}에 works/ 또는 index.json이 있음). 다시 이전하지 않습니다.")
    for name in MOVE:
        p = d / name
        if os.path.lexists(p) and (p.is_symlink() or not p.is_file()):
            raise wl.Reject(f"{p}가 일반 파일이 아닙니다(링크·디렉터리 등). 아무것도 옮기지 않고 중단합니다.")
    if not (d / "events.jsonl").is_file():
        raise wl.Reject(f"형식 1 원장이 없습니다: {d / 'events.jsonl'}")
    sessions = d / "sessions"
    if sessions.is_symlink() or (os.path.lexists(sessions) and not sessions.is_dir()):
        raise wl.Reject(f"{sessions}가 실제 디렉터리가 아닙니다(링크 등). 아무것도 지우지 않고 중단합니다.")
    delete, skipped = [], []
    for p in sorted(sessions.glob("*.json")) if sessions.is_dir() else []:
        # 삭제 대상은 .worklog/sessions 안에 실제로 있는 일반 파일만: 링크는 따라가지 않고 남긴다
        inside = not p.is_symlink() and p.is_file() and p.resolve().parent == sessions.resolve()
        (delete if inside else skipped).append(p if inside else p.name)
    return delete, skipped


def migrate(root, wid, title, do_apply):
    d = wl.store(root)
    if d.is_symlink() or not d.is_dir():
        raise wl.Reject(f"{d}가 실제 디렉터리가 아닙니다. 형식 1 원장이 있는 .worklog에서만 이전합니다.")
    if not (len(wid) <= wl.ID_MAX and wl.WORK_ID.fullmatch(wid)):
        raise wl.Reject(f"--work-id는 소문자·숫자·'-'로 된 {wl.ID_MAX}자 이내 슬러그여야 합니다: {wid!r}")
    title = title or wid
    preconditions(d)
    with wl.locked(d) if do_apply else nullcontext():  # dry-run은 .lock도 만들지 않는다
        sessions, skipped = preconditions(d)  # 잠금 뒤 다시 검사(동시 실행)
        events, _ = wl.read_events(d)  # 연결이 끊긴 원장은 옮기지 않는다
        state, _ = wl.fold(events)
        before = line_hashes(d / "events.jsonl")
        file_before = wl.sha((d / "events.jsonl").read_bytes())
        wd = d / "works" / wid
        moves = [(d / n, wd / n) for n in MOVE if (d / n).exists()]
        entry = {"title": title, "status": state["status"], "created_at": events[0]["at"] if events else wl.now(),
                 "updated_at": state["updated_at"] or wl.now(), "last_seq": len(events)}
        report = {"ok": True, "mode": "apply" if do_apply else "dry-run", "project": str(d.parent), "work_id": wid,
                  "title": title, "events": len(events), "moves": [f"{a.relative_to(d)} → {b.relative_to(d)}" for a, b in moves],
                  "sessions_deleted": [p.name for p in sessions], "sessions_skipped": skipped,
                  "index_entry": entry, "before_sha256": file_before}
        if not do_apply:
            report["next"] = "확인 후 --apply로 실행"
            return report
        wd.mkdir(parents=True)
        for a, b in moves:
            a.replace(b)  # 같은 디렉터리 트리 안의 이름 변경: 바이트 불변
        wl.write_index(d, {"format": wl.FORMAT, "works": {wid: entry}})
        moved, _ = wl.read_events(wd)
        rebuilt, _ = wl.fold(moved)
        wl.project(wd, rebuilt, wid, title)
        for p in sessions:
            p.unlink()
        after = line_hashes(wd / "events.jsonl")
        report.update(after_sha256=wl.sha((wd / "events.jsonl").read_bytes()), line_hashes_match=before == after,
                      state_format=json.loads((wd / "state.json").read_text())["format"])
        report["hashes_match"] = report["line_hashes_match"] and report["after_sha256"] == file_before
        report["ok"] = report["hashes_match"]
        return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--work-id", required=True)
    ap.add_argument("--title")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    try:
        report = migrate(Path(a.project), a.work_id, a.title, a.apply)
    except (wl.Reject, OSError, ValueError) as e:
        error = str(e) if isinstance(e, wl.Reject) else f"{type(e).__name__}: {e}. 사용자에게 보고하세요."
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        sys.exit(2)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not report["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
