#!/usr/bin/env python3
"""Update the Worklog core from its git origin: tags only, same major version only.

Mode (~/.worklog/config.json, key "update"): notify (default when this folder is a git clone) | off.
  check        fetch tags from origin and write ~/.worklog/update.json      (network, ~1 s)
  apply        check, then fast-forward to the newest tag of the current major (network). Only by hand:
               nothing ever changes files on its own.
  background   check only, prints nothing. The SessionStart hook starts this detached at most once a day
               and never waits for it — hooks read only the cache file.
  rollback     return to the commit recorded before the last apply
  --mode M     set the mode. After apply/rollback the user-level install (tools in ~/.worklog/install.json) is
               reinstalled; --root DIR also reinstalls the project-level rules copy of that project (tools listed in
               its .worklog/install.json without scope "user").
Prints the cache as JSON. A newer major version (3.0.0) is reported but never applied: the ledger structure changes.
"""
import argparse, datetime, json, os, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core" / "wl.py"
HOME = Path(os.environ.get("WL_HOME") or Path.home() / ".worklog")
CONFIG, CACHE = HOME / "config.json", HOME / "update.json"
MODES = ("notify", "off")
FETCH_TIMEOUT = 20


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path, value):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def parse(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


def version_of(core=CORE):
    m = re.search(r'^VERSION = "(\d+\.\d+\.\d+)"', core.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def is_clone():
    return (REPO / ".git").exists()


def mode():
    m = read_json(CONFIG).get("update")
    return m if m in MODES else ("notify" if is_clone() else "off")


def git(*args, timeout=FETCH_TIMEOUT):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", f"{type(e).__name__}: {e}"
    return p.returncode, p.stdout, p.stderr


def check():
    old = read_json(CACHE)
    cache = {"checked_at": now(), "mode": mode(), "current": version_of(), "latest": None, "latest_major": None,
             "error": None, "applied": old.get("applied"), "previous": old.get("previous")}
    if not is_clone():
        cache["error"] = "git 저장소가 아니다(복사본). 원본에서 다시 복사해 갱신한다."
        write_json(CACHE, cache)
        return cache
    rc, _, err = git("fetch", "--tags", "--quiet", "origin")
    if rc:
        cache["error"] = f"git fetch 실패: {err.strip()[:200]}"
    rc, out, _ = git("tag", "-l", "v*", timeout=10)
    cur = parse(cache["current"]) or (0,)
    tags = [parse(t[1:]) for t in out.split() if parse(t[1:])]
    same = [v for v in tags if v[0] == cur[0] and v > cur]
    major = [v for v in tags if v[0] > cur[0]]
    cache["latest"] = ".".join(map(str, max(same))) if same else None
    cache["latest_major"] = ".".join(map(str, max(major))) if major else None
    write_json(CACHE, cache)
    return cache


def apply(cache):
    if not cache.get("latest") or cache.get("error"):
        return cache
    tag = "v" + cache["latest"]
    _, dirty, _ = git("status", "--porcelain", "--untracked-files=no", timeout=10)
    if dirty.strip():
        cache["error"] = "커밋되지 않은 변경이 있어 갱신하지 않았다(git status 확인)"
        write_json(CACHE, cache)
        return cache
    _, head, _ = git("rev-parse", "HEAD", timeout=10)
    rc, _, err = git("merge", "--ff-only", "--quiet", tag, timeout=30)
    if rc:
        cache["error"] = f"{tag}로 fast-forward 실패: {err.strip()[:200]}"
        write_json(CACHE, cache)
        return cache
    got = version_of()
    if got != cache["latest"]:
        git("checkout", "--quiet", "--detach", head.strip(), timeout=30)
        cache["error"] = f"갱신 뒤 버전이 {got}이라 {tag}와 달라 되돌렸다"
        write_json(CACHE, cache)
        return cache
    cache.update(previous=head.strip(), applied={"from": cache["current"], "to": got, "at": now()}, current=got, latest=None)
    write_json(CACHE, cache)
    return cache


def rollback(cache):
    prev = cache.get("previous")
    if not prev:
        cache["error"] = "되돌릴 기록이 없다(apply 이력 없음)"
        write_json(CACHE, cache)
        return cache
    rc, _, err = git("checkout", "--quiet", "--detach", prev, timeout=30)
    if rc:
        cache["error"] = f"되돌리기 실패: {err.strip()[:200]}"
    else:
        cache.update(current=version_of(), previous=None, applied=None, error=None)
    write_json(CACHE, cache)
    return cache


def run_installer(tool, *where):
    p = subprocess.run([sys.executable, "-B", str(REPO / "tools" / "install_project.py"), "--tool", tool, *where],
                       capture_output=True, text=True, timeout=30)
    return p.returncode == 0


def reinstall(root):
    """Reinstall the project-level rules copy of one project for every tool its install.json lists with a project install
    (an entry with scope "user" only records the connection and has no copy there). Returns the tools done."""
    done = []
    for tool, entry in read_json(root / ".worklog" / "install.json").items():
        if isinstance(entry, dict) and entry.get("scope") == "user":
            continue
        if run_installer(tool, "--root", str(root)):
            done.append(tool)
    return done


def reinstall_user():
    """Reinstall the user-level rules copy for every tool in ~/.worklog/install.json (an unchanged hook stays byte-for-byte,
    so Codex does not ask for trust again). Returns the tools done."""
    return [tool for tool in read_json(HOME / "install.json") if run_installer(tool, "--user")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", choices=("check", "apply", "background", "rollback"), default="apply")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--root", help="project to reinstall after apply/rollback")
    a = ap.parse_args()
    if a.mode:
        write_json(CONFIG, dict(read_json(CONFIG), update=a.mode))
    if a.action == "background":
        check()
        return
    cache = check() if a.action in ("check", "apply") else read_json(CACHE)
    before = cache.get("current")
    if a.action == "apply":
        cache = apply(cache)
    elif a.action == "rollback":
        cache = rollback(cache)
    if a.action in ("apply", "rollback") and cache.get("current") != before:
        cache["reinstalled_user"] = reinstall_user()
        if a.root:
            cache["reinstalled"] = reinstall(Path(a.root).resolve())
    print(json.dumps(cache, ensure_ascii=False))


if __name__ == "__main__":
    main()
