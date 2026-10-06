#!/usr/bin/env python3
"""Connect one project folder to the shared Worklog core for a given tool. Writes only inside --root.

usage: install_project.py --tool <claude|codex|pi> --root <project> [--dry-run] [--no-worklog-dir]
claude: CLAUDE.md block + three hooks in .claude/settings.local.json + .claude/skills/worklog
codex:  AGENTS.md block + three hooks in .codex/hooks.json + .agents/skills/worklog (user trust required)
pi:     AGENTS.md block + .pi/skills/worklog        (Pi extensions need project trust → not installed; instructions path)
Every target (files, backups, directories to create, .worklog) is checked and every new content prepared before the
first write; a refusal (a link leading outside --root, a .worklog link, unreadable hook settings) changes nothing and
exits 2. Existing files are backed up to <file>.bak-worklog-<timestamp>[-N] (never overwriting a backup) before change;
the managed block and Worklog hooks from any earlier install path are replaced idempotently.
"""
import argparse, datetime, json, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1]
WL = SHARED / "core" / "wl.py"
WL_CMD = f"python3 -B {shlex.quote(str(WL))}"
# A Worklog hook from any install path or quoting style (plain, "double", shlex 'single').
WL_HOOK = re.compile(r"""python3 -B (['"]?)(.*/)?core/wl\.py\1 (hook|turn-start|stop-hook) --tool (claude|codex|pi)""")
BEGIN, END = "<!-- worklog-shared:begin -->", "<!-- worklog-shared:end -->"


class Refuse(Exception):
    pass


def rules(tool):
    fmt = subprocess.run([sys.executable, "-B", str(WL), "help"], capture_output=True, text=True, check=True).stdout
    body = (SHARED / "adapters" / "rules.md").read_text()
    # Core help is tool-neutral; installed command examples must bind the same tool as hooks.
    fmt = fmt.replace("{TOOL}", tool).replace("python3 -B wl.py ", f"{WL_CMD} --tool {tool} ")
    body = body.replace('"{WL}"', shlex.quote(str(WL))).replace("{WL}", str(WL))
    return body.replace("{TOOL}", tool).replace("{FORMAT}", "save 입력 형식:\n```\n" + fmt.strip() + "\n```")


def skill(tool):
    return ("---\nname: worklog\ndescription: 이 프로젝트의 작업 기록(.worklog)을 읽고 턴마다 저장해, 압축·새 세션 뒤에도 "
            "목표·결정·제약·대기·다음 행동을 이어간다.\n---\n\n" + rules(tool))


def inside(root, path):
    """Refuse a target whose deepest existing ancestor (or itself), after links, is outside root."""
    p = path
    while p != root and not os.path.lexists(p):
        p = p.parent
    if not p.resolve().is_relative_to(root):
        raise Refuse(f"{path}는 --root 밖을 가리키는 링크")


def backup_path(root, path, stamp):
    """A free backup name next to path: .bak-worklog-<stamp>, then -1, -2, ... Existing names are never reused."""
    n = 0
    while True:
        cand = path.with_name(f"{path.name}.bak-worklog-{stamp}" + (f"-{n}" if n else ""))
        inside(root, cand)
        if not os.path.lexists(cand):
            return cand
        n += 1


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def write(path, text, backup):
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        shutil.copy2(path, backup)
    path.write_text(text)


def with_block(path, tool):
    block = f"{BEGIN}\n{rules(tool).strip()}\n{END}\n"
    old = path.read_text() if path.exists() else ""
    if BEGIN in old:
        head, rest = old.split(BEGIN, 1)
        return head + block + rest.split(END, 1)[1].lstrip("\n")
    return (old.rstrip() + "\n\n" if old.strip() else "") + block


def is_worklog_hook(command):
    return bool(WL_HOOK.fullmatch(command))


def hook_settings(path, tool):
    try:
        settings = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError) as e:
        raise Refuse(f"{path}를 읽을 수 없습니다({e}). 고친 뒤 다시 설치하세요.")
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise Refuse(f"{path}의 형식이 예상과 다릅니다(최상위와 hooks는 JSON 객체). 고친 뒤 다시 설치하세요.")
    hooks = settings.setdefault("hooks", {})
    for event, command in (("SessionStart", "hook"), ("UserPromptSubmit", "turn-start"), ("Stop", "stop-hook")):
        groups = []
        try:
            for group in hooks.get(event, []):
                # Keep unrelated commands even when they shared a group with an old Worklog hook.
                remaining = [h for h in group.get("hooks", []) if not is_worklog_hook(h.get("command", ""))]
                if remaining:
                    groups.append({**group, "hooks": remaining})
        except (AttributeError, TypeError):
            raise Refuse(f"{path}의 {event} Hook 형식이 예상과 다릅니다. 고친 뒤 다시 설치하세요.")
        hook = {"type": "command", "command": f"{WL_CMD} {command} --tool {tool}", "timeout": 10}
        group = {"hooks": [hook]}
        if event == "SessionStart":
            group["matcher"] = "startup|resume|clear|compact" if tool == "claude" else "^(startup|resume|compact)$"
        groups.append(group)
        hooks[event] = groups
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"


def plan(root, tool, worklog_dir, when):
    """All checks and contents before any write: ([(path, text, backup or None)], .worklog to create or None)."""
    if tool == "claude":
        guide, settings = root / "CLAUDE.md", root / ".claude" / "settings.local.json"
        sk = root / ".claude" / "skills" / "worklog" / "SKILL.md"
    else:
        guide = root / "AGENTS.md"
        settings = root / ".codex" / "hooks.json" if tool == "codex" else None  # Trust is a user action.
        sk = root / (".agents" if tool == "codex" else ".pi") / "skills" / "worklog" / "SKILL.md"
    worklog = root / ".worklog"
    if worklog.is_symlink():  # Hooks write here; a link is refused even when it points inside root.
        raise Refuse(f"{worklog}는 심볼릭 링크입니다. .worklog는 실제 디렉터리여야 합니다.")
    for path in (guide, settings, sk, worklog):
        if path:
            inside(root, path)
    make_dir = worklog_dir and tool in {"claude", "codex"} and not worklog.is_dir()
    if make_dir and worklog.exists():
        raise Refuse(f".worklog exists but is not a directory: {worklog}")
    files = [(guide, with_block(guide, tool))]
    if settings:
        files.append((settings, hook_settings(settings, tool)))
    files.append((sk, skill(tool)))
    changed = [(p, t) for p, t in files if not (p.exists() and p.read_text() == t)]
    return [(p, t, backup_path(root, p, when) if p.exists() else None) for p, t in changed], (worklog if make_dir else None)


def main():
    ap = argparse.ArgumentParser(epilog=".worklog/project.md는 사용자가 편집하는 선택 파일이며 설치기가 만들지 않습니다.")
    ap.add_argument("--tool", choices=["claude", "codex", "pi"], required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-worklog-dir", action="store_true", help="shared parent folder: do not create .worklog here")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    try:
        files, worklog = plan(root, a.tool, not a.no_worklog_dir, stamp())
    except Refuse as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
    changes = [str(p) for p, _, _ in files] + ([str(worklog)] if worklog else [])
    if not a.dry_run:
        for path, text, backup in files:
            write(path, text, backup)
        if worklog:
            worklog.mkdir(parents=True, exist_ok=True)  # Connection signal; never create a ledger here.
    print(json.dumps({"tool": a.tool, "root": str(root), "dry_run": a.dry_run, "changed": changes,
                      "next": "다음: 첫 세션에서 `새 작업: <제목>`으로 작업을 만드세요"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
