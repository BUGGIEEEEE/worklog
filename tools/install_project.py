#!/usr/bin/env python3
"""Install the shared Worklog core for a tool — once per machine (--user, 2.21.0) or for one project (--root).

usage: install_project.py --tool <claude|codex> --user [--migrate] [--dry-run]
       install_project.py --tool <claude|codex|pi> --root <project> [--dry-run] [--no-worklog-dir]
Without --tool nothing is written: the refusal (exit 2) tells the agent to ask the user which tools to install for and
reports which tools this machine seems to have (~/.claude, ~/.codex), since an agent tends to install only for itself.

--user  writes the rules block, the three hooks and the skill into the tool's user-level files, so every folder the tool
        is opened in has them. A folder is connected the moment its .worklog/ exists: the first `새 작업: <title>` in it
        runs `new-work`, which creates .worklog/ and does what --root did per project (the `.worklog/` line in .gitignore
        of a git project, the registry entry, install.json). Elsewhere the SessionStart hook says NOT_CONNECTED and nothing
        else happens. Manifest: WL_HOME/install.json[tool] = {version, rules_src_sha, installed_at}.
        claude: ~/.claude/CLAUDE.md + ~/.claude/settings.json + ~/.claude/skills/worklog
        codex:  ~/.codex/AGENTS.md + ~/.codex/hooks.json + ~/.agents/skills/worklog   (user trust in /hooks, once)
        A project that still has this tool's project-level hooks (registry ~/.worklog/installs.json) is refused: the hooks
        would run twice. --migrate removes the block, hooks, skill and manifest entry from those projects first (records,
        session files, .worklog/ and the .gitignore line stay; install.json gets a connection entry).
--root  the 2.x per-project install, kept for compatibility. Writes only inside --root plus the registry.
        claude: CLAUDE.md block + three hooks in .claude/settings.local.json + .claude/skills/worklog
        codex:  AGENTS.md block + three hooks in .codex/hooks.json + .agents/skills/worklog (user trust required)
        pi:     AGENTS.md block + .pi/skills/worklog        (Pi extensions need project trust → not installed; instructions path)
        In a git repository .gitignore gets `.worklog/` (the whole record stays out of git: it is per-machine state and
        quotes the user; 2.18.0); the 2.11.0–2.17.x lines are dropped as redundant.
Every target (files, backups, directories to create, .worklog) is checked and every new content prepared before the
first write; a refusal (a link leading outside the home or --root, a .worklog link, unreadable hook settings) changes
nothing and exits 2. An OS error in the middle of the writes (2.22.0) rolls the installer's own writes back — changed
files are restored from their backups, new files are deleted — and exits 2 with `rolled_back`. Existing files are backed up to <file>.bak-worklog-<timestamp>[-N] (never overwriting a backup)
before change; the managed block and Worklog hooks from any earlier install path are replaced idempotently, and an
equivalent hook is left byte-for-byte so Codex does not ask for trust again. tools/uninstall_project.py reverses both modes.
"""
import argparse, datetime, hashlib, importlib.util, json, os, re, shlex, shutil, sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1]
WL = SHARED / "core" / "wl.py"
WL_CMD = f"python3 -B {shlex.quote(str(WL))}"
# A Worklog hook from any install path or quoting style (plain, "double", shlex 'single').
WL_HOOK = re.compile(r"""python3 -B (['"]?)(.*/)?core/wl\.py\1 (hook|turn-start|stop-hook) --tool (claude|codex|pi)""")
BEGIN, END = "<!-- worklog-shared:begin -->", "<!-- worklog-shared:end -->"


def load_core():
    spec = importlib.util.spec_from_file_location("wl_core", WL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wl = load_core()  # one copy of the connection logic: gitignore line, registry, manifest live in the core since 2.21.0
GITIGNORE_LINES, GITIGNORE_OLD, IGNORES_WORKLOG = wl.GITIGNORE_LINES, wl.GITIGNORE_OLD, wl.IGNORES_WORKLOG
gitignore_text, register = wl.gitignore_text, wl.register_install
HOME = wl.WL_HOME  # ~/.worklog or WL_HOME: registry, user-level manifest, update state
REGISTRY = HOME / "installs.json"


class Refuse(Exception):
    pass


def rules(tool):
    fmt = f"worklog core {wl.VERSION} (format {wl.FORMAT})\n" + wl.SAVE_HELP
    body = (SHARED / "adapters" / "rules.md").read_text()
    # Core help is tool-neutral; installed command examples must bind the same tool as hooks.
    fmt = fmt.replace("{TOOL}", tool).replace("python3 -B wl.py ", f"{WL_CMD} --tool {tool} ")
    body = body.replace('"{WL}"', shlex.quote(str(WL))).replace("{WL}", str(WL))
    return body.replace("{TOOL}", tool).replace("{FORMAT}", "save 입력 형식:\n```\n" + fmt.strip() + "\n```")


SKILL_ARGS = """## 인자: on / off [이유]
인자와 함께 호출되면(예: `/worklog off 회의 중`, `$worklog on`) 아래 명령만 실행하고 그 턴은 skip으로 마친다.
- `on` → `on`
- `off [이유]` → `off --quote "<호출 원문>"`, 이유가 있으면 `--reason "<이유>"`를 붙인다. 이유가 없어도 묻지 않는다.

"""


def skill(tool):
    return ("---\nname: worklog\ndescription: 이 프로젝트의 작업 기록(.worklog)을 읽고 턴마다 저장해, 압축·새 세션 뒤에도 "
            "목표·결정·제약·대기·다음 행동을 이어간다. 인자 on/off로 이 프로젝트의 Worklog를 켜고 끈다.\n---\n\n"
            + SKILL_ARGS + rules(tool))


def inside(root, path):
    """Refuse a target whose deepest existing ancestor (or itself), after links, is outside root."""
    p = path
    while p != root and not os.path.lexists(p):
        p = p.parent
    if not p.resolve().is_relative_to(root):
        raise Refuse(f"{path}는 설치 대상 폴더 {root} 밖을 가리키는 링크")


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


def rollback(done, made_dir):
    """Undo the installer's own writes after an OS error in the middle (2.22.0): restore each changed file from the
    backup made for it (and drop that backup), delete each file that did not exist before, remove a .worklog it created.
    Best effort, newest first; returns the paths put back."""
    undone = []
    for path, backup, existed in reversed(done):
        try:
            if backup:
                shutil.copy2(backup, path)
                backup.unlink()
            elif not existed:
                path.unlink()
            undone.append(str(path))
        except OSError:
            pass
    if made_dir:
        try:
            made_dir.rmdir()
            undone.append(str(made_dir))
        except OSError:
            pass
    return undone


def with_block(path, tool):
    block = f"{BEGIN}\n{rules(tool).strip()}\n{END}\n"
    old = path.read_text() if path.exists() else ""
    if BEGIN in old:
        head, rest = old.split(BEGIN, 1)
        return head + block + rest.split(END, 1)[1].lstrip("\n")
    return (old.rstrip() + "\n\n" if old.strip() else "") + block


def is_worklog_hook(command):
    return bool(WL_HOOK.fullmatch(command))


def is_current_hook(hook, command, tool):
    """Same install (this wl.py, this subcommand, this tool) in any quoting style."""
    try:
        argv = shlex.split(hook.get("command", ""))
    except ValueError:
        return False
    return hook.get("type") == "command" and hook.get("timeout") == 10 and \
        argv == ["python3", "-B", str(WL), command, "--tool", tool]


def hook_settings(path, tool):
    try:
        settings = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError) as e:
        raise Refuse(f"{path}를 읽을 수 없습니다({e}). 고친 뒤 다시 설치하세요.")
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise Refuse(f"{path}의 형식이 예상과 다릅니다(최상위와 hooks는 JSON 객체). 고친 뒤 다시 설치하세요.")
    hooks = settings.setdefault("hooks", {})
    for event, command in (("SessionStart", "hook"), ("UserPromptSubmit", "turn-start"), ("Stop", "stop-hook")):
        matcher = None
        if event == "SessionStart":
            matcher = "startup|resume|clear|compact|fork" if tool == "claude" else "^(startup|resume|clear|compact|fork)$"  # fork: Claude /branch·--fork-session (2.1.214+), Codex /fork·/side; clear: /clear
        groups, kept = [], False
        try:
            for group in hooks.get(event, []):
                ours = [h for h in group.get("hooks", []) if is_worklog_hook(h.get("command", ""))]
                # An equivalent install is kept byte-for-byte: a rewritten command would change the file hash
                # and make Codex ask the user to trust the hooks again.
                if ours and not kept and group.get("matcher") == matcher and \
                        all(is_current_hook(h, command, tool) for h in ours):
                    groups.append(group)
                    kept = True
                    continue
                # Keep unrelated commands even when they shared a group with an old Worklog hook.
                remaining = [h for h in group.get("hooks", []) if h not in ours]
                if remaining:
                    groups.append({**group, "hooks": remaining})
        except (AttributeError, TypeError):
            raise Refuse(f"{path}의 {event} Hook 형식이 예상과 다릅니다. 고친 뒤 다시 설치하세요.")
        if not kept:
            hook = {"type": "command", "command": f"{WL_CMD} {command} --tool {tool}", "timeout": 10}
            group = {"hooks": [hook]}
            if matcher:
                group["matcher"] = matcher
            groups.append(group)
        hooks[event] = groups
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"


def manifest(folder, tool):
    """Write <folder>/install.json[tool] = {version, rules_src_sha, installed_at}: what this copy of the rules was made from
    (folder = the project's .worklog, or WL_HOME for --user). The core compares rules_src_sha with its own adapters/rules.md
    and warns when they differ (never refuses)."""
    path = folder / "install.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[tool] = {"version": wl.VERSION, "rules_src_sha": hashlib.sha256((SHARED / "adapters" / "rules.md").read_bytes()).hexdigest(),
                  "installed_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return path


def targets(tool, root, user):
    """(guide file, hook settings file or None, SKILL.md) for a tool — in the user's home (user=True) or in a project."""
    if user:
        if tool == "claude":
            return root / ".claude" / "CLAUDE.md", root / ".claude" / "settings.json", root / ".claude" / "skills" / "worklog" / "SKILL.md"
        return root / ".codex" / "AGENTS.md", root / ".codex" / "hooks.json", root / ".agents" / "skills" / "worklog" / "SKILL.md"
    if tool == "claude":
        return root / "CLAUDE.md", root / ".claude" / "settings.local.json", root / ".claude" / "skills" / "worklog" / "SKILL.md"
    settings = root / ".codex" / "hooks.json" if tool == "codex" else None  # Trust is a user action.
    return root / "AGENTS.md", settings, root / (".agents" if tool == "codex" else ".pi") / "skills" / "worklog" / "SKILL.md"


def plan(root, tool, worklog_dir, when, user=False):
    """All checks and contents before any write: ([(path, text, backup or None)], .worklog to create or None)."""
    guide, settings, sk = targets(tool, root, user)
    worklog = None if user else root / ".worklog"
    if worklog and worklog.is_symlink():  # Hooks write here; a link is refused even when it points inside root.
        raise Refuse(f"{worklog}는 심볼릭 링크입니다. .worklog는 실제 디렉터리여야 합니다.")
    for path in (guide, settings, sk, worklog):
        if path:
            inside(root, path)
    make_dir = bool(worklog) and worklog_dir and tool in {"claude", "codex"} and not worklog.is_dir()
    if make_dir and worklog.exists():
        raise Refuse(f".worklog exists but is not a directory: {worklog}")
    files = [(guide, with_block(guide, tool))]
    if settings:
        files.append((settings, hook_settings(settings, tool)))
    files.append((sk, skill(tool)))
    if worklog and worklog_dir and tool in {"claude", "codex"} and (root / ".git").exists():  # git project: keep the record out of commits
        gi = root / ".gitignore"
        inside(root, gi)
        text = gitignore_text(gi)
        if text is not None:
            files.append((gi, text))
    changed = [(p, t) for p, t in files if not (p.exists() and p.read_text() == t)]
    return [(p, t, backup_path(root, p, when) if p.exists() else None) for p, t in changed], (worklog if make_dir else None)


def detected_tools():
    """Which tools this machine seems to use: their home folders exist. A hint for the agent's question, not a decision."""
    return {t: (Path.home() / f".{t}").is_dir() for t in ("claude", "codex")}


def uninstaller():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import uninstall_project  # it imports this module, hence the lazy import
    return uninstall_project


def project_hooks_left(tool):
    """Registry projects that still have this tool's project-level Worklog hooks: with a user-level hook they would run
    twice (two turn counts, two Stop checks). Older installs that are not in the registry cannot be found here."""
    un = uninstaller()
    out = []
    for r in un.load_registry():
        settings = targets(tool, Path(r), False)[1]
        if settings and un.has_worklog_hook(settings):
            out.append(Path(r))
    return out


def migration_plans(tool, roots, when):
    """One uninstaller plan per project: block, hooks, skill and manifest entry go; session files (a running session's
    current work), records, .worklog/ and the .gitignore line stay. Planned before any write; a refusal changes nothing."""
    un = uninstaller()
    plans = []
    for root in roots:
        p = un.Plan(root, True, when)
        un.plan_tool(p, root, tool, keep_sessions=True)
        plans.append((root, p))
    return plans


def main():
    ap = argparse.ArgumentParser(
        description="AGENT: before running this, ask the user which tools to install for (claude, codex, or both; they share one "
                    ".worklog) when this machine has more than your own tool (~/.claude, ~/.codex). Do not install for a tool the user "
                    "did not choose. Default is --user (once per machine); --root installs one project only. See AGENT.md 'Install'.",
        epilog=".worklog/project.md는 사용자가 편집하는 선택 파일이며 설치기가 만들지 않습니다.")
    ap.add_argument("--tool", choices=["claude", "codex", "pi"], help="없으면 거부: 사용자에게 어느 도구에 설치할지 먼저 확인")
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--user", action="store_true", help="이 기기의 도구 설정(~/.claude, ~/.codex, ~/.agents)에 한 번 설치. 프로젝트는 첫 `새 작업:`이 연결")
    where.add_argument("--root", help="한 프로젝트에만 설치(2.x 방식)")
    ap.add_argument("--migrate", action="store_true", help="--user: registry의 프로젝트에서 프로젝트 단위 블록·Hook·스킬을 먼저 제거(기록·세션·.gitignore 줄 유지)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-worklog-dir", action="store_true", help="--root: shared parent folder, do not create .worklog here")
    a = ap.parse_args()
    if a.migrate and not a.user:
        ap.error("--migrate는 --user와 함께 씁니다")
    root = Path.home().resolve() if a.user else Path(a.root).resolve()
    migrations = []
    try:
        if not a.tool:
            found = ", ".join(f"{t}={'있음' if v else '없음'}" for t, v in detected_tools().items())
            raise Refuse("사용자에게 어느 도구에 설치할지 확인한 뒤 도구별로 실행하세요: --tool claude | codex (pi는 미검증). "
                         f"이 기기에서 발견: {found}. 기기에 한 번 설치하려면 --user, 한 프로젝트만이면 --root <프로젝트>. "
                         "두 도구는 같은 .worklog를 공유하며, Codex는 설치 뒤 /hooks 신뢰가 필요합니다.")
        if a.user and a.tool == "pi":
            raise Refuse("pi는 사용자 범위 설치를 지원하지 않습니다(미검증). --root <프로젝트>로 설치하세요.")
        if a.user:
            left = project_hooks_left(a.tool)
            if left and not a.migrate:
                raise Refuse(f"프로젝트 단위 {a.tool} Hook이 남아 있는 프로젝트가 있어 전역 Hook과 두 번 돌게 됩니다: "
                             + ", ".join(map(str, left)) + ". --migrate를 붙이면 그 프로젝트의 블록·Hook·스킬을 먼저 제거합니다"
                             "(기록·세션·.gitignore 줄은 유지).")
            if a.migrate:
                migrations = migration_plans(a.tool, left, stamp())
        files, worklog = plan(root, a.tool, not a.no_worklog_dir, stamp(), user=a.user)
    except Refuse as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
    changes = [str(p) for p, _, _ in files] + ([str(worklog)] if worklog else [])
    migrated = [{"root": str(r), "removed": p.removed, "changed": p.changed, "backups": p.backups, "notes": p.notes} for r, p in migrations]
    registry = None
    if not a.dry_run:
        for r, p in migrations:
            p.run()
            if (r / ".worklog").is_dir():
                wl.mark_connected(r / ".worklog", a.tool)  # still connected: the records and the folder stay
        done, made_dir = [], None  # the installer's own writes, for rollback on an OS error in the middle (2.22.0)
        try:
            for path, text, backup in files:
                existed = path.exists()
                write(path, text, backup)
                done.append((path, backup, existed))
            if a.user:
                changes.append(str(manifest(HOME, a.tool)))
            else:
                if worklog:
                    worklog.mkdir(parents=True, exist_ok=True)  # Connection signal; never create a ledger here.
                    made_dir = worklog
                wl_dir = root / ".worklog"
                if a.tool in ("claude", "codex") and not a.no_worklog_dir and wl_dir.is_dir():
                    changes.append(str(manifest(wl_dir, a.tool)))
        except OSError as e:
            undone = rollback(done, made_dir)
            print(json.dumps({"error": f"쓰기 도중 실패({e}). 앞서 쓴 파일은 되돌렸습니다(백업에서 복원·새 파일 삭제): {undone}. "
                                       "원인을 고친 뒤 다시 실행하세요.", "rolled_back": undone,
                              "migrated": migrated}, ensure_ascii=False))
            sys.exit(2)
        if not a.user:
            registry = register(root, a.tool)
    out = {"tool": a.tool, "scope": "user" if a.user else "project", "root": str(root), "dry_run": a.dry_run, "changed": changes}
    if a.user:
        out["migrated"] = migrated
        out["next"] = ("다음: " + ("Codex는 /hooks에서 Hook 3개를 신뢰하고, " if a.tool == "codex" else "")
                       + "열린 세션을 다시 시작한 뒤 프로젝트 폴더의 첫 세션에서 `새 작업: <제목>`으로 작업을 만드세요(그때 .worklog/가 생깁니다)")
    else:
        out["registry"] = registry
        out["next"] = "다음: 첫 세션에서 `새 작업: <제목>`으로 작업을 만드세요"
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
