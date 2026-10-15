#!/usr/bin/env python3
"""Undo install_project.py for a project: the rules block, the three hooks, the skill, the .gitignore lines, the install
manifest and this tool's session files, and, when asked, the records in .worklog. Writes only inside --root, plus the
install registry and (with --home) the state folder ~/.worklog (WL_HOME).

usage: uninstall_project.py --root <project> [--tool claude|codex|pi|all] (--keep-records | --delete-records)
                            [--no-backup] [--purge-backups] [--dry-run]
       uninstall_project.py --all-projects (--keep-records | --delete-records) [--home] [--no-backup] [--purge-backups] [--dry-run]
       uninstall_project.py --home [--dry-run]
--tool all (default) removes every tool's install. A single tool leaves what the other tools share (.worklog/.lock, off
marker, .gitignore lines, records) while another tool is still installed there.
--keep-records   keeps .worklog/works/, index.json and project.md (a later reinstall continues them). Everything else of
                 Worklog in .worklog (sessions, lock, off marker, install.json) goes once no tool remains installed.
--delete-records removes .worklog entirely. Refused while another tool is still installed (use --tool all).
Neither flag: asks on a terminal, otherwise refuses — an agent must ask the user first.
Files it edits or deletes (CLAUDE.md/AGENTS.md, hook settings, .gitignore) are backed up as <file>.bak-worklog-<stamp>
unless --no-backup. Earlier backups left by the installer stay unless --purge-backups (every *.bak-worklog-* the installer
can have made: project root, .claude/, .codex/, the three skill folders).
--all-projects   every project in the registry ~/.worklog/installs.json (kept by installs since 2.17.0; older installs
                 are not listed: run the installer once more or pass --root).
--home           removes ~/.worklog (update mode, update cache, registry) once the registry lists no project.
Every target is checked and every new content prepared before the first write; a refusal (a link leading outside --root,
unreadable hook settings) changes nothing and exits 2. Never touched: Codex hook trust in ~/.codex/config.toml, Claude
Code folder trust, the clone itself (the command to delete it is printed at the end).
"""
import argparse, json, os, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_project import BEGIN, END, GITIGNORE_LINES, SHARED, Refuse, WL_HOOK, backup_path, inside, stamp  # noqa: E402

HOME = Path(os.environ.get("WL_HOME") or Path.home() / ".worklog")
REGISTRY = HOME / "installs.json"
TOOLS = ("claude", "codex", "pi")
RECORDS = ("works", "index.json", "project.md")  # kept by --keep-records
STATE = ("sessions", ".lock", "off", "install.json")  # Worklog's own state: removed once no tool remains


def paths(root, tool):
    """(guide, hook settings or None, SKILL.md) as the installer writes them."""
    if tool == "claude":
        return root / "CLAUDE.md", root / ".claude" / "settings.local.json", root / ".claude" / "skills" / "worklog" / "SKILL.md"
    settings = root / ".codex" / "hooks.json" if tool == "codex" else None
    return root / "AGENTS.md", settings, root / (".agents" if tool == "codex" else ".pi") / "skills" / "worklog" / "SKILL.md"


def without_block(text):
    """Guide text without the managed block; "" when nothing else was there. None when there is no block."""
    if BEGIN not in text:
        return None
    head, rest = text.split(BEGIN, 1)
    tail = rest.split(END, 1)[1] if END in rest else ""
    head, tail = head.rstrip(), tail.lstrip("\n")
    if head.strip() and tail.strip():
        return head + "\n\n" + tail
    return head + "\n" if head.strip() else tail


def is_worklog_hook(hook):
    try:
        return bool(WL_HOOK.fullmatch(hook.get("command", "")))
    except (AttributeError, TypeError):
        return False


def without_hooks(path, text):
    """(new settings text, or "" when the file would be empty) after dropping every Worklog hook; None when there is none."""
    try:
        settings = json.loads(text)
    except (OSError, ValueError) as e:
        raise Refuse(f"{path}를 읽을 수 없습니다({e}). 고친 뒤 다시 실행하세요.")
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise Refuse(f"{path}의 형식이 예상과 다릅니다(최상위와 hooks는 JSON 객체). 고친 뒤 다시 실행하세요.")
    hooks, changed = settings.get("hooks", {}), False
    for event in list(hooks):
        groups = []
        try:
            for group in hooks[event]:
                remaining = [h for h in group.get("hooks", []) if not is_worklog_hook(h)]
                if len(remaining) != len(group.get("hooks", [])):
                    changed = True
                if remaining or not group.get("hooks"):
                    groups.append({**group, "hooks": remaining} if remaining else group)
        except (AttributeError, TypeError):
            raise Refuse(f"{path}의 {event} Hook 형식이 예상과 다릅니다. 고친 뒤 다시 실행하세요.")
        if groups:
            hooks[event] = groups
        elif changed:
            del hooks[event]
    if not changed:
        return None
    if not hooks:
        del settings["hooks"]
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n" if settings else ""


def has_worklog_hook(path):
    try:
        hooks = json.loads(path.read_text()).get("hooks", {})
        return any(is_worklog_hook(h) for groups in hooks.values() for g in groups for h in g.get("hooks", []))
    except (OSError, ValueError, AttributeError, TypeError):
        return False


def manifest_tools(worklog):
    try:
        data = json.loads((worklog / "install.json").read_text(encoding="utf-8"))
        return set(data) if isinstance(data, dict) else set()
    except (OSError, ValueError):
        return set()


def installed(root, tool):
    """Whether `tool` still has a hook, a skill or a manifest entry here (the guide block is shared by codex and pi)."""
    _, settings, sk = paths(root, tool)
    return (settings is not None and has_worklog_hook(settings)) or sk.exists() or tool in manifest_tools(root / ".worklog")


class Plan:
    """Actions collected before any write, keyed by path so that a file two steps touch (AGENTS.md shared by codex and pi,
    install.json emptied by the last tool and then removed with the state) is planned once. Reads go through the plan so
    later steps see earlier planned changes."""

    def __init__(self, root, backup, when):
        self.root, self.backup, self.when = root, backup, when
        self.order, self.pending, self.prunes = [], {}, []  # pending[path] = ("write", text, backup) | ("delete", backup) | ("rmtree",)
        self.kept, self.notes = [], []

    def exists(self, path):
        if path in self.pending:
            return self.pending[path][0] == "write"
        if any(a[0] == "rmtree" and path.is_relative_to(p) for p, a in self.pending.items()):
            return False
        return os.path.lexists(path)

    def read(self, path):
        a = self.pending.get(path)
        return a[1] if a and a[0] == "write" else path.read_text()

    def _backup(self, path):
        if not self.backup or path in self.pending:
            return None
        return backup_path(self.root, path, self.when)

    def _set(self, path, action):
        if path not in self.pending:
            self.order.append(path)
        self.pending[path] = action

    def edit(self, path, text):
        """Replace a file's content; "" deletes it. Backed up either way (the file was not entirely Worklog's)."""
        inside(self.root, path)
        b = self.pending[path][-1] if path in self.pending else self._backup(path)
        self._set(path, ("write", text, b) if text else ("delete", b))

    def delete(self, path):
        """Remove a file that is entirely Worklog's (no backup)."""
        inside(self.root, path)
        if path not in self.pending:
            self._set(path, ("delete", None))

    def rmtree(self, path):
        inside(self.root, path)
        for p in [p for p in self.pending if p.is_relative_to(path)]:
            self.pending.pop(p)
            self.order.remove(p)
        self._set(path, ("rmtree",))

    def prune(self, path):
        """Remove a directory afterwards if it is empty by then."""
        self.prunes.append(path)

    @property
    def removed(self):
        return [str(p) + ("/" if self.pending[p][0] == "rmtree" else "") for p in self.order if self.pending[p][0] != "write"]

    @property
    def changed(self):
        return [str(p) for p in self.order if self.pending[p][0] == "write"]

    @property
    def backups(self):
        return [str(a[-1]) for p, a in self.pending.items() if a[0] != "rmtree" and a[-1]]

    def run(self):
        for path in self.order:
            action = self.pending[path]
            if action[0] == "rmtree":
                shutil.rmtree(path)
                continue
            if action[-1]:
                shutil.copy2(path, action[-1])
            if action[0] == "write":
                path.write_text(action[1])
            else:
                path.unlink()
        for path in self.prunes:
            try:
                if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                    path.rmdir()
            except OSError:
                pass


def plan_tool(plan, root, tool):
    guide, settings, sk = paths(root, tool)
    for p in (guide, settings, sk):
        if p:
            inside(root, p)
    if plan.exists(guide):
        text = without_block(plan.read(guide))
        if text is not None:
            plan.edit(guide, text)
    if settings and plan.exists(settings):
        text = without_hooks(settings, plan.read(settings))
        if text is not None:
            plan.edit(settings, text)
            if tool == "codex" and text:
                plan.notes.append("Codex: .codex/hooks.json에 다른 Hook이 남아 있어 다음 /hooks에서 다시 신뢰해야 합니다. ~/.codex/config.toml의 신뢰 기록은 건드리지 않았습니다.")
    if plan.exists(sk):
        plan.delete(sk)
    for d in (sk.parent, sk.parent.parent, sk.parent.parent.parent) + ((settings.parent,) if settings else ()):  # worklog/, skills/, .claude|.agents|.pi, .codex
        plan.prune(d)
    worklog = root / ".worklog"
    if worklog.is_symlink():
        raise Refuse(f"{worklog}는 심볼릭 링크입니다. 손대지 않습니다.")
    if worklog.is_dir():
        inside(root, worklog)
        for s in sorted((worklog / "sessions").glob(f"{tool}_*.json")) if (worklog / "sessions").is_dir() else []:
            plan.delete(s)
        mf = worklog / "install.json"
        if plan.exists(mf):
            try:
                data = json.loads(plan.read(mf))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and tool in data:
                data.pop(tool)
                if data:
                    plan._set(mf, ("write", json.dumps(data, ensure_ascii=False, indent=1) + "\n", None))
                else:
                    plan.delete(mf)


def plan_state(plan, root, delete_records):
    """What every tool shares in .worklog: state, records, and the .gitignore lines."""
    worklog = root / ".worklog"
    if worklog.is_dir():
        if delete_records:
            plan.rmtree(worklog)
        else:
            for name in STATE:
                p = worklog / name
                if p.is_dir() and not p.is_symlink():
                    plan.rmtree(p)
                elif plan.exists(p):
                    plan.delete(p)
            plan.kept.extend(str(worklog / n) for n in RECORDS if os.path.lexists(worklog / n))
            plan.prune(worklog)
    gi = root / ".gitignore"
    if gi.is_file():
        inside(root, gi)
        try:
            lines = gi.read_text().splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return
        rest = [ln for ln in lines if ln.strip() not in GITIGNORE_LINES]
        if len(rest) != len(lines):
            plan.edit(gi, "".join(rest) if "".join(rest).strip() else "")


def plan_backups(plan, root):
    """Every *.bak-worklog-* the installer (or this tool) can have left."""
    for folder in [root, root / ".claude", root / ".codex"] + [paths(root, t)[2].parent for t in TOOLS]:
        if folder.is_dir():
            for b in sorted(folder.glob("*.bak-worklog-*")):
                if b.is_file():
                    plan.delete(b)


def plan_project(root, tools, delete_records, backup, purge_backups, when):
    plan = Plan(root, backup, when)
    for tool in tools:
        plan_tool(plan, root, tool)
    remaining = [t for t in TOOLS if t not in tools and installed(root, t)]
    if remaining and delete_records:
        raise Refuse(f"{', '.join(remaining)}가 아직 설치돼 있어 기록을 지우지 않습니다. 함께 제거하려면 --tool all.")
    if remaining:
        plan.notes.append(f"{', '.join(remaining)}가 아직 설치돼 있어 .worklog 상태·기록과 .gitignore 줄은 그대로 둡니다.")
    else:
        plan_state(plan, root, delete_records)
    if purge_backups:
        plan_backups(plan, root)
    return plan


# --- registry ~/.worklog/installs.json: {"<root>": ["claude", "codex"]} ---

def load_registry():
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {r: [t for t in ts if t in TOOLS] for r, ts in data.items() if isinstance(ts, list)} if isinstance(data, dict) else {}


def save_registry(data):
    data = {r: ts for r, ts in data.items() if ts}
    if data:
        HOME.mkdir(parents=True, exist_ok=True)
        REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    elif REGISTRY.exists():
        REGISTRY.unlink()


def unregister(root, tools):
    data = load_registry()
    key = str(root)
    if key in data:
        data[key] = [t for t in data[key] if t not in tools]
        save_registry(data)


def ask_records():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise Refuse("--keep-records 또는 --delete-records 중 하나를 지정하세요(.worklog의 기록을 남길지 지울지는 사용자가 정합니다).")
    answer = input(".worklog의 기록(works/, index.json, project.md)도 지울까요? [k]eep / [d]elete: ").strip().lower()
    if answer in ("d", "delete"):
        return True
    if answer in ("k", "keep"):
        return False
    raise Refuse("k 또는 d로 답하세요.")


def uninstall_root(root, a, when, delete_records):
    root = Path(root).resolve()
    if not root.is_dir():
        return {"root": str(root), "error": "폴더가 없습니다"}
    tools = list(TOOLS) if a.tool == "all" else [a.tool]
    try:
        plan = plan_project(root, tools, delete_records, not a.no_backup, a.purge_backups, when)
    except Refuse as e:
        return {"root": str(root), "error": str(e)}
    if not a.dry_run:
        plan.run()
        unregister(root, tools)
    return {"tool": a.tool, "root": str(root), "dry_run": a.dry_run, "removed": plan.removed, "changed": plan.changed,
            "kept": plan.kept, "backups": plan.backups, "notes": plan.notes}


def main():
    ap = argparse.ArgumentParser(epilog="--delete-records는 .worklog를 통째로 지웁니다. 되돌릴 수 없습니다.")
    ap.add_argument("--tool", choices=[*TOOLS, "all"], default="all")
    ap.add_argument("--root")
    ap.add_argument("--all-projects", action="store_true", help="registry에 적힌 모든 프로젝트")
    ap.add_argument("--home", action="store_true", help="~/.worklog(WL_HOME) 삭제: registry가 비어 있을 때만")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--keep-records", action="store_true")
    g.add_argument("--delete-records", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--purge-backups", action="store_true", help="설치기가 남긴 *.bak-worklog-* 파일도 삭제")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not (a.root or a.all_projects or a.home):
        ap.error("--root, --all-projects, --home 중 하나는 필요합니다")
    out = {"dry_run": a.dry_run, "projects": [], "notes": []}
    try:
        roots = [a.root] if a.root else []
        if a.all_projects:
            roots += [r for r in load_registry() if r not in roots]
            if not roots:
                out["notes"].append("registry에 프로젝트가 없습니다(2.17.0 이전 설치본은 적히지 않음: --root로 지정)")
        delete_records = None
        if roots:
            delete_records = True if a.delete_records else False if a.keep_records else ask_records()
        when = stamp()
        for r in roots:
            out["projects"].append(uninstall_root(r, a, when, delete_records))
        if a.home:
            left = load_registry() if a.dry_run else {r: ts for r, ts in load_registry().items() if ts}
            if a.dry_run:
                left = {r: [t for t in ts if not (r in roots and (a.tool == "all" or t == a.tool))] for r, ts in left.items()}
                left = {r: ts for r, ts in left.items() if ts}
            if left:
                raise Refuse(f"registry에 아직 설치된 프로젝트가 있습니다: {', '.join(left)}. 먼저 제거하세요(--all-projects).")
            if HOME.is_dir() and not HOME.is_symlink():
                out["home"] = {"removed": str(HOME), "files": sorted(p.name for p in HOME.iterdir())}
                if not a.dry_run:
                    shutil.rmtree(HOME)
            else:
                out["home"] = {"removed": None}
            out["notes"].append(f"clone 폴더는 스스로 지우지 않습니다. 더 쓰지 않으면: rm -rf {SHARED}")
    except Refuse as e:
        print(json.dumps({**out, "error": str(e)}, ensure_ascii=False, indent=1))
        sys.exit(2)
    out["notes"].append("건드리지 않은 것: Codex Hook 신뢰 기록(~/.codex/config.toml), Claude Code 폴더 신뢰, 전역 지침 파일.")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if any("error" in p for p in out["projects"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
