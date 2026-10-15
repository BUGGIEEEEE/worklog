#!/usr/bin/env python3
"""Worklog shared core (format 2): several works per project, one append-only event log per work.

Commands:  works | use | new-work | show | save | skip | verify | archive | reopen | off | on | version | update | help | hook | turn-start | stop-hook
Storage:   <root>/.worklog/{index.json, project.md?, works/<id>/{events.jsonl, state.json, state.md, writer.json},
           sessions/<tool>_<session>.json, .lock, off?}   (off = 이 프로젝트의 Worklog가 꺼짐. 원장 아님)
Standard library only. Never runs business commands.
"""
import argparse, datetime, fcntl, hashlib, json, os, re, shlex, subprocess, sys, uuid
from contextlib import contextmanager
from pathlib import Path

FORMAT = "worklog/2"
VERSION = "2.17.0"  # 코어·규칙 버전(CHANGELOG.md와 같아야 한다). FORMAT은 원장 구조 전용
TYPES = ["REQUEST", "APPROVAL", "D_USER", "D_AGENT", "ASSUMPTION", "RESULT", "VERIFICATION",
         "BLOCKER", "CORRECTION", "CHECKPOINT", "HANDOFF", "CHANGE", "Q",
         "WRITER_ACQUIRED", "WRITER_RELEASED"]
USER_TYPES = {"REQUEST", "APPROVAL", "D_USER"}
REMOVE_TYPES = {"D_USER", "APPROVAL", "CORRECTION"}
STATUSES = ["ACTIVE", "PAUSED", "BLOCKED", "COMPLETED", "CANCELLED"]
TOOL_ENV = [("codex", "CODEX_THREAD_ID"), ("claude", "CLAUDE_CODE_SESSION_ID"), ("pi", "PI_SESSION_ID")]
WORK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ID_MAX = 40
PROJECT_MAX = 4000
LIST_MAX = 10
DONE_MAX = 3      # SessionStart 목록 뒤에 보여 주는 최근 COMPLETED 작업 수
ART_MAX = 15      # state.md: 산출물이 이보다 많으면 폴더별 요약
NEW_WORK_PREFIX = re.compile(r"^\s*새\s*작업\s*[:：]\s*")
WORKTREE_WARNING = ("git worktree 안입니다. 여기서 저장한 기록은 본 저장소와 갈라져 병합 때 .worklog/works/*/events.jsonl이 충돌합니다. "
                    "기록은 본 저장소 세션에서 하고, 여기서 저장했다면 병합 전에 충돌을 사람이 정리하세요.")
HOOK_WARNING = ("Hook 미작동 의심: 이 세션 파일에 Hook 기록이 하나도 없습니다(SessionStart·UserPromptSubmit·Stop). Hook이 꺼져 있거나 "
                "신뢰되지 않았거나 세션 ID가 다릅니다. Codex는 /hooks에서 신뢰, Claude Code는 .claude/settings.local.json을 확인하고 사용자에게 보고하세요.")
NO_WORK_GUIDE = ("사용자에게 작업을 지정받을 때까지 저장하지 않는다. 지정이 없으면 한 번 묻고 skip으로 마친다. "
                 "작업이 하나뿐이고 \"이어서\"면 그 작업을 use한다.")

SAVE_HELP = """save: 턴마다 한 번, stdin으로 JSON 하나를 넣는다.  예) python3 -B wl.py save <<'EOF' ... EOF
{
  "work": "habit-plan",                    # 선택. 생략하면 이 세션의 현재 작업(use/new-work로 정함)
  "type": "REQUEST",                       # REQUEST APPROVAL D_USER D_AGENT ASSUMPTION RESULT VERIFICATION BLOCKER CORRECTION CHECKPOINT HANDOFF CHANGE Q
  "summary": "이번 턴에 일어난 일 한두 문장",   # 위임한 턴은 첫머리에 "[위임: 안내문 초안] 서브에이전트가 note-guide.md 초안 작성, 두 문장 확인". 결정·제약 글자에는 쓰지 않는다
  "quote": "사용자 원문 일부(그대로)",      # REQUEST/APPROVAL/D_USER, 목표 설정, 사용자 제약 해제에 필수
  "goal": "최초 목표",                     # 처음 한 번만. 생략하면 첫 save가 작업 제목을 목표로 쓴다. 이후 값 변경은 decisions(replaces)로
  "decisions": [{"text": "11분으로 변경(이유)", "replaces": "D1"},   # 지금 고른 방법·범위. 바뀌면 replaces. 작업량·목표 범위(몇 화까지 등)는 여기에
                {"text": "3·5·3분 배분(모델 제안)", "source": "model"}],  # 모델이 제안한 것은 사용자 발언과 같은 save에 있어도 "source": "model"을 붙인다 → [모델]로 표시
  "constraints": ["다른 프로젝트 자료 조회 금지(사용자 변경 전까지)"],  # 계속 지킬 금지·자료 범위만. 작업량·목표 범위는 decisions에. 해제는 constraints_remove
                                           # "다음 요청까지 작성 보류"처럼 요청이 오면 끝나는 것은 waiting에
                                           # "파일은 만들지 마"·"두 줄로 답해"처럼 이번 턴에만 적용되는 지시는 기록하지 않는다. "외부 게시 금지"처럼 계속 적용되는 것만 제약이다
                                           # 운영 지시(도구·서브에이전트·평가기·Hook·Goal·질문 방식·테스트 실행 여부에 대한 "~하지 마/써라")는 제약이 아니다. 그 턴에 지키고 summary에만 남긴다
  "constraints_remove": {"C2": "해제 근거"},   # [사용자] 제약: type D_USER/APPROVAL/CORRECTION + quote. [모델] 제약: 사유만으로 해제. 같은 제약 재입력은 자동 무시
  "waiting": ["note-guide.md는 다음 요청까지 작성 보류", "확인 필요: 2화는 원작 282행부터라고 가정"],  # 전체 교체. 생략하면 유지, []면 비움. 확인 안 된 가정도 여기에
  "next_action": "다음 행동",
  "status": "ACTIVE",                      # ACTIVE PAUSED BLOCKED COMPLETED CANCELLED. 사용자가 작업이 끝났다고 말하기 전까지 COMPLETED로 바꾸지 않는다
  "artifacts": [{"path": "note-guide.md"}],
  "check": {"D1": "'저녁 식사 후 11분'", "C1": "미반영: 알림은 만들지 않았고 본문에 넣을 내용이 아님"}
                                           # 텍스트 산출물이 있으면 모든 유효 결정·제약 ID 필수. 값은 둘 중 하나:
                                           # ① 규칙이 지켜졌음을 보여 주는 산출물 본문 구절(4자 이상)을 따옴표로 인용(본문에서 대조, 공백 무시)
                                           # ② "미반영: <이유>" — 작업 방식 제약이나 그림·압축 파일처럼 인용할 수 없는 것. 정상이며 결과의 unreflected에 표시
                                           # 규칙 문장을 본문에 써 넣고 그대로 인용하지 않는다. 그런 인용은 결과의 self_quoted에 표시된다
                                           # 제약 문장을 본문에 옮겨 적지 않는다(일부만 바꿔 써도 같다). "제약을 반영해 달라"는 본문이 제약을 어기지 않게 쓰라는 뜻이다
}
필드는 필요한 것만 넣는다. 거부되면 메시지대로 고쳐 다시 실행한다. 소스 코드를 읽을 필요는 없다.
"기록이 바뀌었습니다" 거부는 다른 세션이 저장했다는 뜻: show로 읽고 반영한 뒤 다시 저장한다.
"직전 사건과 같은 세션·같은 summary" 거부는 되감기(rewind) 뒤 재저장일 수 있다: show로 확인하고 이미 저장됐으면 skip, 새 내용이면 summary를 바꾼다.
결과의 artifacts_missing(또는 show의 "[Worklog 산출물 없음]"): 이 세션이 기록한 산출물이 실제 파일에 없다(되감기 코드 복원·삭제). 사용자에게 알린다.
읽기 전용 턴(저장할 것이 없음): python3 -B wl.py skip "이유" — 원장에는 아무것도 쓰지 않는다.

작업 선택 — 사용자가 지정한다. 모델이 임의로 고르거나 만들지 않는다.
  python3 -B wl.py works                                         작업 목록(JSON)
  python3 -B wl.py use habit-plan --quote "habit-plan 이어서 해"   기존 작업을 이 세션의 현재 작업으로(현황 출력, show 불필요)
  python3 -B wl.py new-work "습관 계획 habit-plan" --quote "새 작업: 습관 계획"
                                       새 작업을 만들고 현재 작업으로(id 반환: 제목의 영문·숫자 → habit-plan, 한글만·숫자만이면 work, work-2…)
                                       결과의 notice: 다른 작업의 제약은 새 작업에 적용되지 않는다. 이어받을 것은 맡긴 프롬프트에 적힌 것만 저장하고, 없으면 사용자에게 확인한다
  python3 -B wl.py show [--work <id>]                            현황 읽기(현재 작업이 없으면 목록)
  python3 -B wl.py verify [--work <id> | --all]
  python3 -B wl.py archive <id> / reopen <id>                    COMPLETED ↔ ACTIVE
현재 작업이 없고 사용자 지정도 없으면 한 번 묻고 skip으로 마친다. 작업이 하나뿐이고 "이어서"면 그 작업을 use한다.

켜고 끄기 — 사용자가 말할 때만. 원장에는 쓰지 않는다(꺼진 기간은 기록에 남지 않는다).
  python3 -B wl.py off --quote "워크로그 꺼" [--reason "이유"]    이 프로젝트 전체를 끈다(.worklog/off)
  python3 -B wl.py on                                           다시 켠다"""
QUOTE = re.compile(r"'(.+?)'|\"(.+?)\"|‘(.+?)’|“(.+?)”", re.DOTALL)
MIN_QUOTE = 4


class Reject(Exception):
    pass


def norm(text):
    return " ".join(str(text).split())


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def store(root):
    return Path(root).resolve() / ".worklog"


def identity(args):
    tool, sid = os.environ.get("WL_TOOL"), os.environ.get("WL_SESSION_ID")
    if getattr(args, "tool", None):
        tool = args.tool
    if getattr(args, "session", None):
        sid = args.session
    if not (tool and sid):
        for name, env in TOOL_ENV:
            if os.environ.get(env) and (not tool or tool == name):
                tool, sid = name, sid or os.environ[env]
                break
    if not (tool and sid):
        raise Reject("세션을 확인할 수 없습니다. --tool <codex|claude|pi> --session <ID>를 지정하세요.")
    return tool, sid


def try_identity(args):
    try:
        return identity(args)
    except Reject:
        return None


@contextmanager
def locked(d):
    """The one .worklog/.lock: ledger appends, index updates and every session-file read→update→write happen inside it.
    Not re-entrant: never call a locking command handler (show, verify, …) while holding it."""
    if (d / ".lock").is_symlink():  # open(..., "w")는 링크를 따라가 밖의 파일을 비운다
        raise Reject(f"{d / '.lock'}는 심볼릭 링크입니다. 사용자에게 보고하세요.")
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write_atomic(path, text):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --- 세션 보조 파일 (원장 아님) ---

def session_path(d, tool, sid):
    return d / "sessions" / re.sub(r"[^A-Za-z0-9._-]", "_", f"{tool}_{sid}.json")


SESSION_TURNS = ("turn", "saved_turn", "skipped_turn", "selected_turn")


class SessionCorrupt(Exception):
    pass


def new_session():
    return {"current_work": None, "last_seen": {}, "hooks_seen": {}, **dict.fromkeys(SESSION_TURNS, 0)}


def load_session(d, tool, sid):
    """Missing keys get defaults; None if absent; SessionCorrupt if unreadable."""
    path = session_path(d, tool, sid)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise SessionCorrupt(path)
    if not isinstance(data, dict):
        raise SessionCorrupt(path)
    s = new_session()
    s.update({k: data[k] for k in s if k in data})
    if (any(type(s[k]) is not int for k in SESSION_TURNS)
            or not (s["current_work"] is None or isinstance(s["current_work"], str))
            or not isinstance(s["last_seen"], dict) or any(type(v) is not int for v in s["last_seen"].values())
            or not isinstance(s["hooks_seen"], dict) or any(not isinstance(v, str) for v in s["hooks_seen"].values())):
        raise SessionCorrupt(path)
    return s


def session_or_new(d, tool, sid):
    try:
        return load_session(d, tool, sid) or new_session()
    except SessionCorrupt:
        return new_session()  # 손상 파일은 새로 만든다


def update_session(d, tool, sid, seen=None, **changes):
    """Call inside locked(d). seen=(work id, seq) records what this session has read of that work."""
    s = session_or_new(d, tool, sid)
    s.update(changes)
    if seen:
        s["last_seen"][seen[0]] = seen[1]
    path = session_path(d, tool, sid)
    path.parent.mkdir(exist_ok=True)
    write_atomic(path, json.dumps(s, ensure_ascii=False) + "\n")
    return s


def mark_hook(d, who, name):
    """Inside locked(d): record that hook `name` ran for this session (self-diagnosis shown by save·skip·verify)."""
    seen = dict(session_or_new(d, *who)["hooks_seen"], **{name: now()})
    update_session(d, *who, hooks_seen=seen)


RULES_SRC = Path(__file__).resolve().parents[1] / "adapters" / "rules.md"
INSTALLER = Path(__file__).resolve().parents[1] / "tools" / "install_project.py"
SOURCE_TAG = re.compile(r"^(?:\s*\[(?:사용자|모델)\]\s*)+|(?:\s*\[(?:사용자|모델)\]\s*)+$")


def strip_source_tag(text):
    """F6: the core adds [사용자]/[모델] itself; literal tags at either end of a decision/constraint text are dropped."""
    return SOURCE_TAG.sub("", text).strip()


def rules_src_sha():
    try:
        return hashlib.sha256(RULES_SRC.read_bytes()).hexdigest()
    except OSError:
        return None


def install_report(d, tool):
    """{"warning_install": ...} when .worklog/install.json says this tool's rules copy was made from a different adapters/rules.md.
    Anything missing or broken (no manifest, bad JSON, no entry, no adapters) means no warning and no error."""
    try:
        entry = json.loads((d / "install.json").read_text(encoding="utf-8")).get(tool)
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(entry, dict):
        return {}
    recorded, current = entry.get("rules_src_sha"), rules_src_sha()
    if not (isinstance(recorded, str) and current) or recorded == current:
        return {}
    return {"warning_install": f"규칙 사본이 설치 당시(v{entry.get('version') or '?'})와 다릅니다(코어 {VERSION}). "
                               f"python3 -B {shlex.quote(str(INSTALLER))} --tool {tool} --root {shlex.quote(str(d.parent))} 를 다시 실행하세요."}


def parse_version(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


def core_report(events):
    """{"warning_core": ...} when any event carries a `core` with a newer major or minor number than this VERSION
    (patch differences are text-only by the numbering rule; older events without `core`, or unparsable values, never warn).
    FORMAT is untouched, so nothing is refused."""
    mine = parse_version(VERSION)[:2]
    newer = [ev["core"] for ev in events if (parse_version(ev.get("core")) or mine)[:2] > mine]
    if not newer:
        return {}
    top = max(newer, key=parse_version)
    return {"warning_core": f"이 기록은 코어 {top}이 썼습니다(현재 {VERSION}). 코어를 갱신하세요."}


# --- 갱신 알림 (tools/update.py가 한다. Hook은 캐시 파일만 읽고, 하루 한 번 배경 검사를 띄울 뿐 기다리지 않는다. 적용은 사용자가 `update`를 칠 때만) ---

UPDATE_PY = Path(__file__).resolve().parents[1] / "tools" / "update.py"
WL_HOME = Path(os.environ.get("WL_HOME") or Path.home() / ".worklog")
UPDATE_MODES = ("notify", "off")
CHECK_EVERY = datetime.timedelta(hours=24)


def home_json(name):
    try:
        value = json.loads((WL_HOME / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def update_mode():
    """notify by default for a git clone of the repo; a plain copy (no .git) has nothing to check."""
    m = home_json("config.json").get("update")
    return m if m in UPDATE_MODES else ("notify" if (UPDATE_PY.parents[1] / ".git").exists() else "off")


def recent(stamp, within=CHECK_EVERY):
    try:
        at = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.datetime.now(datetime.timezone.utc) - at < within


def spawn_update_check():
    """SessionStart: start `update.py background` (fetch + cache only) detached at most once a day. Never waits, never fails the hook.
    The cache's checked_at is claimed first so parallel sessions do not start it twice."""
    try:
        if update_mode() == "off" or not UPDATE_PY.is_file():
            return
        cache = home_json("update.json")
        if recent(cache.get("checked_at")):
            return
        WL_HOME.mkdir(parents=True, exist_ok=True)
        write_atomic(WL_HOME / "update.json", json.dumps(dict(cache, checked_at=now()), ensure_ascii=False))
        subprocess.Popen([sys.executable, "-B", str(UPDATE_PY), "background"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, ValueError):
        pass


def update_note():
    """One line for the SessionStart injection, from the cache file only (no network)."""
    cache, mode = home_json("update.json"), update_mode()
    if mode == "off" or not cache:
        return ""
    cmd = f"python3 -B {shlex.quote(str(Path(__file__).resolve()))} update"
    applied = cache.get("applied") or {}
    if isinstance(applied, dict) and applied.get("to") == VERSION and recent(applied.get("at")):
        return (f"[Worklog 갱신] 코어를 v{applied.get('from')}에서 v{VERSION}으로 갱신했다({applied.get('at')}). "
                f"변경 내용: {UPDATE_PY.parents[1] / 'CHANGELOG.md'}. 되돌리기: {cmd} rollback\n")
    if cache.get("latest_major"):
        return (f"[Worklog 갱신 안내] 새 주 버전 v{cache['latest_major']}이 있다(현재 {VERSION}). 기록 구조가 바뀌므로 자동 갱신하지 않는다. "
                "CHANGELOG의 마이그레이션 안내를 읽고 사용자가 직접 진행한다.\n")
    latest = cache.get("latest")
    if latest and (parse_version(latest) or (0,)) > (parse_version(VERSION) or (0,)):
        if cache.get("error"):
            return f"[Worklog 갱신 실패] v{latest} 갱신 실패: {cache['error']}. 다시 시도: {cmd}\n"
        return f"[Worklog 갱신 안내] 새 버전 v{latest}(현재 {VERSION}). 갱신: {cmd}\n"
    return ""


def cmd_update(args):
    """update [check|rollback] [--mode notify|off]: runs tools/update.py and prints its JSON. Only this applies an update."""
    action = args.arg or "apply"
    if action not in ("check", "apply", "rollback"):
        raise Reject("update 형식: update [check|rollback] [--mode notify|off]")
    cmd = [sys.executable, "-B", str(UPDATE_PY), action, "--root", str(Path(args.root).resolve())]
    if args.mode:
        cmd += ["--mode", args.mode]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise Reject(f"update.py 실패: {(p.stderr or p.stdout).strip()[:300]}")
    print(p.stdout, end="")


ARTIFACTS_MISSING = "이 세션이 기록한 산출물이 실제 파일에 없다"


def own_missing_artifacts(d, events, state, who):
    """["path(Eid)"] for artifacts this session recorded whose file is gone (rewind code restore, deletion).
    Only this session's: a file another session or the user removed on purpose is not nagged every turn (verify checks all)."""
    if not who or not state.get("artifacts"):
        return []
    tool, sid = who
    by_id = {e["id"]: e for e in events}
    out = []
    for a in state["artifacts"]:
        ev = by_id.get(a.get("event"))
        if ev and ev.get("tool") == tool and ev.get("session_id") == sid and not (d.parent / a["path"]).is_file():
            out.append(f"{a['path']}({a['event']})")
    return out


def artifacts_note(missing):
    """Text line for show·use·SessionStart (output only, never in state.md)."""
    return (f"[Worklog 산출물 없음] {ARTIFACTS_MISSING}: {', '.join(missing)}. 되감기(rewind) 코드 복원이나 삭제가 원인일 수 있다. "
            "사용자에게 알린다.\n") if missing else ""


def artifacts_check(d, state):
    """verify: every artifact — missing files and changed hashes. Not an error: a recorded file may change afterwards."""
    arts = state.get("artifacts", [])
    missing, changed = [], 0
    for a in arts:
        p = d.parent / a["path"]
        if not p.is_file():
            missing.append(f"{a['path']}({a['event']})")
        elif sha(p.read_bytes()) != a.get("sha256"):
            changed += 1
    return {"missing": missing, "changed": changed, "checked": len(arts)}


def worktree_report(d):
    """{"warning_worktree": ...} when the project root is a git worktree (.git is a file, not a directory): its ledger diverges from the main checkout."""
    return {"warning_worktree": WORKTREE_WARNING} if (d.parent / ".git").is_file() else {}


def hooks_report(d, tool, sid):
    """{"hooks": {...}} for JSON results, plus "warning" when this session has no hook record at all (none of the three ran:
    not trusted, not installed, or another session id) and "warning_worktree" inside a git worktree. Pi has no hooks, so only
    the worktree warning is reported for it. A missing UserPromptSubmit alone is not a warning: a turn started by `!` shell
    input or by another session's notification does not fire it (observed 2026-10-15), while SessionStart and Stop still run."""
    if tool == "pi":
        return worktree_report(d)
    try:
        s = load_session(d, tool, sid) or new_session()
    except SessionCorrupt:
        s = new_session()
    seen = s["hooks_seen"]
    out = {"hooks": {"session_start": "SessionStart" in seen, "turn_start": "UserPromptSubmit" in seen, "stop": "Stop" in seen}}
    if not seen:
        out["warning"] = HOOK_WARNING
    out.update(install_report(d, tool))
    out.update(worktree_report(d))
    return out


def hooks_note(d, who):
    """Text warning line for use (text output) when hooks look inactive."""
    if not who:
        return ""
    report = hooks_report(d, *who)
    note = f"[Worklog Hook 경고] {HOOK_WARNING}\n" if "warning" in report else ""
    if "warning_install" in report:
        note += f"[Worklog 사본 경고] {report['warning_install']}\n"
    if "warning_worktree" in report:
        note += f"[Worklog worktree 경고] {report['warning_worktree']}\n"
    return note


# --- 작업 목록 (index.json) ---

def load_index(d):
    """index.json or None when absent. A format-1 ledger at the top of .worklog is refused (migrate first)."""
    if (d / "events.jsonl").exists():
        raise Reject("형식 1 기록(.worklog/events.jsonl)이 있습니다. tools/migrate_v1_to_v2.py로 먼저 이전하세요. 사용자에게 보고하세요.")
    try:
        data = json.loads((d / "index.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Reject(f"index.json을 읽을 수 없습니다({e}). 고치지 말고 사용자에게 보고하세요.")
    if not (isinstance(data, dict) and data.get("format") == FORMAT and isinstance(data.get("works"), dict)):
        raise Reject(f"index.json이 {FORMAT} 형식이 아닙니다. 고치지 말고 사용자에게 보고하세요.")
    for wid, w in data["works"].items():
        problem = entry_problem(wid, w)
        if problem:
            raise Reject(f"index.json의 작업 {wid} 항목이 손상됨: {problem}. 고치지 말고 사용자에게 보고하세요.")
    return data


def entry_problem(wid, w):
    """What is wrong with one index entry, or None."""
    if not (len(wid) <= ID_MAX and WORK_ID.fullmatch(wid)):
        return "작업 id 형식이 아님"
    if not isinstance(w, dict):
        return "객체가 아님"
    for key in ("title", "created_at", "updated_at"):
        if not isinstance(w.get(key), str) or not w[key]:
            return f"{key}가 비어 있지 않은 문자열이 아님"
    if w.get("status") not in STATUSES:
        return f"status가 {STATUSES} 중 하나가 아님"
    if type(w.get("last_seq")) is not int or w["last_seq"] < 0:
        return "last_seq가 0 이상의 정수가 아님"
    return None


def index_or_new(d):
    return load_index(d) or {"format": FORMAT, "works": {}}


def write_index(d, index):
    """Call inside locked(d)."""
    write_atomic(d / "index.json", json.dumps(index, ensure_ascii=False, indent=1) + "\n")


def contained(path, parent):
    """Refuse a link, or an existing path that resolves outside parent (works/ and works/<id>, also before creation)."""
    if path.is_symlink() or (os.path.lexists(path) and not path.resolve().is_relative_to(parent.resolve())):
        raise Reject(f"{path}가 심볼릭 링크이거나 {parent} 밖을 가리킵니다. 쓰지 않고 중단합니다. 사용자에게 보고하세요.")
    return path


def works_root(d):
    return contained(d / "works", d)


def work_dir(d, wid):
    if not (isinstance(wid, str) and len(wid) <= ID_MAX and WORK_ID.fullmatch(wid)):
        raise Reject(f"작업 id 형식이 아닙니다: {wid!r}")
    return contained(works_root(d) / wid, d / "works")


def make_id(title, taken):
    """Title → ASCII slug (a-z, 0-9, '-', ≤40); 'work' when nothing ASCII or only digits is left ("던전디펜스 1화" → "1" is
    not a usable id); '-2', '-3' on collision."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:ID_MAX].strip("-")
    if not base or base.replace("-", "").isdigit():
        base = "work"
    wid, n = base, 1
    while wid in taken:
        n += 1
        wid = base[:ID_MAX - len(f"-{n}")].strip("-") + f"-{n}"
    return wid


def sorted_works(works):
    """ACTIVE … CANCELLED, newest update first within a status."""
    items = sorted(works.items(), key=lambda x: x[1].get("updated_at") or "", reverse=True)
    return sorted(items, key=lambda x: STATUSES.index(x[1].get("status")) if x[1].get("status") in STATUSES else len(STATUSES))


def work_list(index):
    return "; ".join(f"{i} · {w.get('title')} · {w.get('status')}" for i, w in sorted_works(index["works"])) or "(없음)"


def no_work_msg(index):
    return ("현재 작업이 없습니다. 사용자가 지정한 작업으로 use <id> --quote 또는 new-work \"제목\" --quote 후 저장하세요. "
            f"작업 목록: {work_list(index)}")


def entry(index, wid):
    if not isinstance(wid, str) or wid not in index["works"]:
        raise Reject(f"없는 작업입니다: {wid}. 작업 목록: {work_list(index)}")
    return index["works"][wid]


# --- 원장과 투영 (형식 1과 같은 사건 구조) ---

def read_events(wd):
    path = wd / "events.jsonl"
    if not path.exists():
        return [], None
    events, prev = [], None
    for n, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            ev = None
        if not isinstance(ev, dict) or ev.get("prev") != prev or ev.get("seq") != len(events) + 1:
            raise Reject(f"{wd.name}/events.jsonl {n}행의 연결(seq/prev)이 맞지 않습니다. 고치지 말고 사용자에게 보고하세요.")
        events.append(ev)
        prev = sha(raw)
    return events, prev


def empty_state():
    return {"format": FORMAT, "seq": 0, "goal": None, "status": "ACTIVE", "decisions": [],
            "constraints": [], "waiting": [], "next_action": None, "artifacts": [],
            "superseded": [], "removed_constraints": [], "updated_at": None, "updated_by": None}


def apply(state, ev):
    """Pure fold of one event into state. Raises Reject on invalid references.
    Decisions and constraints carry source = "user" (event type REQUEST/APPROVAL/D_USER) or "model" (any other type).
    A decision may carry its own "source": "model" (a model proposal saved in a user event)."""
    s = json.loads(json.dumps(state))
    c, eid = ev.get("changes", {}), ev["id"]
    source = "user" if ev.get("type") in USER_TYPES else "model"
    if c.get("goal") is not None:
        if s["goal"]:
            raise Reject("목표는 처음 한 번만 정합니다. 바뀐 목표는 decisions로 남기세요.")
        s["goal"] = c["goal"]
    ids = {x["id"] for x in s["decisions"]}
    for d in c.get("decisions", []):
        rep = d.get("replaces")
        if rep:
            if rep not in ids:
                raise Reject(f"replaces={rep}: 유효 결정에 없는 ID입니다. 현재: {sorted(ids)}")
            s["decisions"] = [x for x in s["decisions"] if x["id"] != rep]
            s["superseded"].append({"id": rep, "by_event": eid})
            ids.discard(rep)
        nid = f"D{ev['next_d']}"
        ev["next_d"] += 1
        item = {"id": nid, "text": d["text"], "event": eid, "source": d.get("source") or source}
        if rep:
            item["replaces"] = rep
        s["decisions"].append(item)
        ids.add(nid)
    cids = {x["id"] for x in s["constraints"]}
    for cid, why in (c.get("constraints_remove") or {}).items():
        if cid not in cids:
            raise Reject(f"constraints_remove {cid}: 유효 제약에 없는 ID입니다. 현재: {sorted(cids)}")
        s["constraints"] = [x for x in s["constraints"] if x["id"] != cid]
        s["removed_constraints"].append({"id": cid, "reason": why, "by_event": eid})
    for text in c.get("constraints", []):
        s["constraints"].append({"id": f"C{ev['next_c']}", "text": text, "event": eid, "source": source})
        ev["next_c"] += 1
    for key in ("waiting", "next_action", "status"):
        if key in c:
            s[key] = c[key]
    for a in c.get("artifacts", []):
        s["artifacts"] = [x for x in s["artifacts"] if x["path"] != a["path"]] + [dict(a, event=eid)]
    s["seq"], s["updated_at"], s["updated_by"] = ev["seq"], ev["at"], {"tool": ev["tool"], "session_id": ev["session_id"]}
    return s


def fold(events):
    s, counters = empty_state(), {"next_d": 1, "next_c": 1}
    for ev in events:
        tmp = dict(ev, **counters)
        s = apply(s, tmp)
        counters = {"next_d": tmp["next_d"], "next_c": tmp["next_c"]}
    return s, counters


def tag(item):
    """' [사용자]' / ' [모델]' from an item's source (older state files without source show nothing)."""
    return {"user": " [사용자]", "model": " [모델]"}.get(item.get("source"), "")


def render(s, wid, title):
    by = s["updated_by"] or {}
    out = [f"# Worklog 현재 상태 — {wid} · {title} (seq {s['seq']}, {s['updated_at']}, {by.get('tool')}:{by.get('session_id')})", "",
           f"최초 목표(원문): {s['goal'] or '(미정)'}"]
    if s["decisions"]:
        last = s["decisions"][-1]
        out.append(f"현재 범위(최신 결정): {last['id']}: {last['text']}")
    out += ["※ 최초 목표의 값이 이후에 바뀌었다면 아래 '유효 결정'이 우선한다. replaces로 기록된 변경은 충돌이 아니다.",
            f"상태: {s['status']}", "", "## 유효 결정 — [사용자]는 사용자 발언, [모델]은 모델 판단"]
    out += [f"- {d['id']}: {d['text']}" + (f" (대체: {d['replaces']})" if d.get("replaces") else "") + tag(d) for d in s["decisions"]] or ["- (없음)"]
    out += ["", "## 유지 제약 — [사용자] 제약은 사용자가 바꾸기 전까지, [모델] 제약은 모델이 사유를 적고 해제할 때까지 유지"]
    out += [f"- {c['id']}: {c['text']}{tag(c)}" for c in s["constraints"]] or ["- (없음)"]
    out += ["", "## 대기"] + ([f"- {w}" for w in s["waiting"]] or ["- (없음)"])
    out += ["", f"## 다음 행동", s["next_action"] or "(미정)"]
    if len(s["artifacts"]) > ART_MAX:  # 긴 작업: 폴더별 개수와 최근 사건만. 전체 목록은 state.json
        groups = {}
        for a in s["artifacts"]:
            g = groups.setdefault(os.path.dirname(a["path"]) or ".", {"n": 0, "event": ""})
            g["n"] += 1
            g["event"] = max(g["event"], a["event"])
        out += ["", f"## 산출물 — {len(s['artifacts'])}개, 폴더별 요약(전체 목록·해시는 state.json)"]
        out += [f"- {folder}/ · {g['n']}개 · 최근 {g['event']}" for folder, g in groups.items()]
    elif s["artifacts"]:
        out += ["", "## 산출물"] + [f"- {a['path']} sha256:{a['sha256'][:12]} ({a['event']})" for a in s["artifacts"]]
    if s["superseded"] or s["removed_constraints"]:
        out += ["", f"대체된 결정 {len(s['superseded'])}개·해제된 제약 {len(s['removed_constraints'])}개는 events.jsonl에 보존."]
    return "\n".join(out) + "\n"


def project(wd, state, wid, title):
    write_atomic(wd / "state.json", json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    write_atomic(wd / "state.md", render(state, wid, title))


def projection_ok(wd, state, wid, title, events):
    """(state.json ok, state.md ok). A work without events may have no projection yet."""
    def same(name, want, parse):
        try:
            return parse((wd / name).read_text(encoding="utf-8")) == want
        except FileNotFoundError:
            return not events
        except (OSError, ValueError):
            return False
    return same("state.json", state, json.loads), same("state.md", render(state, wid, title), str)


def commit(d, index, wid, ev):
    """Inside locked(d): append → reread → rebuild projection → compare → index update. Returns the new state."""
    wd = work_dir(d, wid)
    wd.mkdir(parents=True, exist_ok=True)
    line = json.dumps(ev, ensure_ascii=False, separators=(",", ":")).encode()
    with open(wd / "events.jsonl", "ab") as f:
        f.write(line + b"\n")
        f.flush()
        os.fsync(f.fileno())
    reread, _ = read_events(wd)
    if reread[-1] != json.loads(line):
        raise Reject("저장한 사건을 다시 읽은 값이 다릅니다. 사용자에게 보고하세요.")
    rebuilt, _ = fold(reread)
    project(wd, rebuilt, wid, index["works"][wid]["title"])
    if json.loads((wd / "state.json").read_text()) != rebuilt or rebuilt["seq"] != ev["seq"]:
        raise Reject("현재 상태 파일 대조 실패(원장은 저장됨). `wl.py show`로 복원하세요.")
    index["works"][wid].update(updated_at=ev["at"], last_seq=ev["seq"], status=rebuilt["status"])
    write_index(d, index)
    return rebuilt


def read_writer(path):
    """writer.json (last writer, information only) or None when absent or unreadable."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def new_event(events, prev, kind, tool, sid, summary, quote, refs, changes):
    return {"v": 1, "seq": len(events) + 1, "id": f"E{len(events) + 1:04d}", "type": kind, "at": now(),
            "tool": tool, "session_id": sid, "summary": summary, "quote": quote,
            "refs": refs, "changes": changes, "prev": prev, "core": VERSION}


# --- 저장 ---

def validate(p, root, state):
    if not isinstance(p, dict):
        raise Reject("입력은 JSON 객체여야 합니다. `wl.py help` 참고.")
    unknown = set(p) - {"work", "type", "summary", "quote", "goal", "decisions", "constraints", "constraints_remove",
                        "waiting", "next_action", "status", "artifacts", "check", "refs", "takeover",
                        "occurred_at", "source"}
    if unknown:
        raise Reject(f"알 수 없는 필드: {sorted(unknown)}. `wl.py help` 참고.")
    if p.get("type") not in TYPES:
        raise Reject(f"type은 {TYPES} 중 하나여야 합니다.")
    if not isinstance(p.get("summary"), str) or not p["summary"].strip():
        raise Reject("summary가 필요합니다(문자열).")
    for key in ("quote", "goal", "next_action", "takeover"):
        if p.get(key) is not None and not isinstance(p[key], str):
            raise Reject(f"{key}는 문자열이어야 합니다.")
    for key in ("constraints", "waiting"):
        if key in p and (not isinstance(p[key], list) or not all(isinstance(x, str) for x in p[key])):
            raise Reject(f'{key}는 문자열 목록이어야 합니다. 예: ["알림 등록 금지"]')
    remove = p.get("constraints_remove")
    if remove is not None and (not isinstance(remove, dict) or not all(isinstance(v, str) for v in remove.values())):
        raise Reject('constraints_remove는 {"C2": "해제 근거"}처럼 문자열 값을 가진 객체여야 합니다.')
    if "check" in p and (not isinstance(p["check"], dict) or not all(isinstance(v, str) for v in p["check"].values())):
        raise Reject('check는 {"D1": "\'본문 인용\'"}처럼 문자열 값을 가진 객체여야 합니다.')
    arts_in = p.get("artifacts", [])
    if not isinstance(arts_in, list) or any(not isinstance(a, dict) or not isinstance(a.get("path"), str) for a in arts_in):
        raise Reject('artifacts는 [{"path": "note-guide.md"}] 형식이어야 합니다.')
    # 제약 해제 권한은 출처별: [사용자] 제약은 사용자 출처 사건 + quote, [모델] 제약은 사유만으로 (모르는 ID는 apply가 거부)
    sources = {x["id"]: x.get("source", "user") for x in state["constraints"]}
    user_removed = [cid for cid in (remove or {}) if sources.get(cid, "user") == "user"]
    if user_removed and p["type"] not in REMOVE_TYPES:
        raise Reject(f"사용자 제약 {user_removed}의 해제는 사용자가 바꾼 경우에만 합니다. type을 {sorted(REMOVE_TYPES)} 중 하나로, "
                     "quote에 해제를 말한 사용자 원문을 넣으세요. 같은 제약이 다시 들어오는 것은 자동으로 무시되므로 해제할 필요가 없습니다.")
    needs_quote = p["type"] in USER_TYPES or p.get("goal") or user_removed or p.get("takeover")
    if needs_quote and not str(p.get("quote") or "").strip():
        raise Reject("이 저장에는 사용자 원문 일부 quote가 필요합니다.")
    refs = p.get("refs", [])
    if not isinstance(refs, list) or any(not isinstance(r, dict) or not all(isinstance(v, str) for v in r.values()) for r in refs):
        raise Reject('refs는 [{"kind": "block", "id": "B03"}]처럼 문자열 값만 가진 객체 목록입니다.')
    if "status" in p and p["status"] not in STATUSES:
        raise Reject(f"status는 {STATUSES} 중 하나여야 합니다.")
    decisions = p.get("decisions", [])
    if not isinstance(decisions, list) or any(
            not isinstance(x, dict) or not isinstance(x.get("text"), str) or not x["text"]
            or (x.get("replaces") is not None and not isinstance(x["replaces"], str)) for x in decisions):
        raise Reject('decisions는 [{"text": "...", "replaces": "D1"}] 형식입니다(text·replaces는 문자열).')
    if any(x.get("source") not in (None, "model") for x in decisions):
        raise Reject('decisions의 source는 "model"만 쓸 수 있습니다(모델 제안 표시). 사용자 결정은 type REQUEST/APPROVAL/D_USER로 저장합니다.')
    if not all(x for x in p.get("constraints", [])):
        raise Reject("constraints에 빈 문자열이 있습니다.")
    arts, bodies = [], []
    for a in arts_in:
        path = (Path(root) / a.get("path", "")).resolve()
        if not path.is_file():
            raise Reject(f"산출물 파일이 없습니다: {a.get('path')}")
        data = path.read_bytes()  # 한 번만 읽어 해시와 check 대조에 같은 바이트를 쓴다
        arts.append({"path": a["path"], "sha256": sha(data)})
        try:  # 그림·압축 파일 같은 비텍스트 산출물은 해시만 남기고 인용 대조에서 뺀다
            if b"\x00" not in data:
                bodies.append(norm(data.decode("utf-8")))
        except UnicodeDecodeError:
            pass
    return arts, bodies


def cmd_save(args):
    root = Path(args.root).resolve()
    tool, sid = identity(args)
    raw = sys.stdin.read()
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Reject(f"JSON 해석 실패: {e}. `wl.py help` 참고.")
    d = store(root)
    if not d.is_dir():
        raise Reject(no_work_msg({"works": {}}))
    with locked(d):
        index = index_or_new(d)
        try:
            sess = load_session(d, tool, sid)
        except SessionCorrupt:
            sess = None  # 손상: 무엇을 읽었는지 알 수 없으므로 없는 것으로 보고, 성공 시 새로 만든다
        explicit = isinstance(p, dict) and "work" in p
        if explicit and not (isinstance(p["work"], str) and p["work"].strip()):
            raise Reject(f'work는 비어 있지 않은 문자열(작업 id)이어야 합니다. 예: "work": "habit-plan". 받은 값: {json.dumps(p["work"], ensure_ascii=False)}')
        wid = p["work"] if explicit else (sess or {}).get("current_work")
        if not wid:
            raise Reject(no_work_msg(index))
        title = entry(index, wid)["title"]
        wd = work_dir(d, wid)
        events, prev = read_events(wd)
        state, counters = fold(events)
        arts, bodies = validate(p, root, state)
        # 신선도: 이 세션이 이 작업에서 마지막으로 본 seq 뒤에 다른 저장이 있으면 거부(읽기 전 쓰기 방지)
        seen = (sess or {}).get("last_seen", {}).get(wid)
        if seen is None and events:
            raise Reject(f"show 먼저 실행하세요(작업 {wid}). 이 세션은 아직 이 작업의 현재 기록을 읽지 않았습니다.")
        if seen is not None and seen < len(events):
            raise Reject(f"기록이 바뀌었습니다(seq {seen}→{len(events)}). show 후 다시 저장하세요.")
        # 같은 세션이 직전 사건과 같은 내용을 다시 저장하면 거부: 되감기(rewind) 뒤 기억만 되돌아간 경우(신선도 검사는 통과한다)
        last = events[-1] if events else None
        if last and (last.get("tool"), last.get("session_id"), last.get("type")) == (tool, sid, p["type"]) \
                and norm(last.get("summary") or "") == norm(p["summary"]):
            raise Reject(f"직전 사건 {last['id']}와 같은 세션·같은 summary입니다. 되감기(rewind) 뒤라면 show로 현재 기록을 확인하고, "
                         "이미 저장됐으면 skip하세요. 새 내용이면 summary를 바꿔 저장하세요.")
        # writer.json은 마지막 작성자 정보. takeover는 선택(사용자가 명시적으로 넘길 때 기록)
        wpath = wd / "writer.json"
        writer = read_writer(wpath)  # 정보용: 읽을 수 없으면 없는 것으로 보고 저장 성공 시 덮어쓴다
        acquired = {"from": writer, "reason": p["takeover"]} if p.get("takeover") else None
        changes = {k: p[k] for k in ("goal", "decisions", "constraints", "constraints_remove", "waiting",
                                     "next_action", "status") if k in p}
        if changes.get("goal"):  # "새 작업: 제목" 명령문이 그대로 목표가 되지 않게
            changes["goal"] = NEW_WORK_PREFIX.sub("", changes["goal"]).strip() or changes["goal"]
        elif not events and "goal" not in changes:  # 첫 저장에 목표가 없으면 작업 제목
            changes["goal"] = title
        ignored = []
        if "constraints" in changes:  # F6: 출처 태그는 코어가 붙인다
            changes["constraints"] = [strip_source_tag(t) for t in changes["constraints"]]
            if any(not t for t in changes["constraints"]):
                raise Reject("제약 내용이 비어 있습니다(출처 태그 [사용자]/[모델]는 코어가 붙이므로 글자에 쓰지 않는다).")
            have = {norm(x["text"]) for x in state["constraints"]}
            keep = []
            for t in changes["constraints"]:
                (ignored if norm(t) in have else keep).append(t)
                have.add(norm(t))
            changes["constraints"] = keep
        if "decisions" in changes:
            for item in changes["decisions"]:
                item["text"] = strip_source_tag(item["text"])
                if not item["text"]:
                    raise Reject("결정 내용이 비어 있습니다(출처 태그 [사용자]/[모델]는 코어가 붙이므로 글자에 쓰지 않는다).")
            have = {norm(x["text"]) for x in state["decisions"]}
            keep = []
            for item in changes["decisions"]:
                (ignored if not item.get("replaces") and norm(item["text"]) in have else keep).append(item)
                have.add(norm(item["text"]))
            changes["decisions"] = keep
        if arts:
            changes["artifacts"] = arts
        ev = new_event(events, prev, p["type"], tool, sid, p["summary"], p.get("quote"), p.get("refs", []), changes)
        for k in ("occurred_at", "source"):
            if k in p:
                ev[k] = p[k]
        if acquired:
            ev["writer_acquired"] = acquired
        try:  # 상태 계산·렌더링 실패는 원장 추가 전에 거부로 바꾼다
            new_state = apply(state, dict(ev, **counters))
            render(new_state, wid, title)
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            raise Reject(f"상태를 만들 수 없는 입력입니다({type(e).__name__}: {e}). `wl.py help` 참고.")
        unreflected, self_quoted = [], []
        rules = new_state["decisions"] + new_state["constraints"]
        check = p.get("check") or {}
        if arts and bodies:  # 텍스트 산출물: 모든 유효 결정·제약이 본문에 인용으로 있거나 "미반영: 이유"여야 한다
            need = [x["id"] for x in rules]
            missing = [i for i in need if not str(check.get(i) or "").strip()]
            if missing:
                raise Reject(f"산출물 대조 누락: {missing}. 각 결정·제약마다 산출물 본문의 인용('...') 또는 \"미반영: 이유\"를 check에 적으세요. "
                             f"현재 목록: " + "; ".join(f"{x['id']}={x['text']}" for x in rules))
        elif arts:  # 비텍스트 산출물만: 인용할 본문이 없으므로 check는 선택이고 미반영만 받는다
            need = [i for i in check if i in {x["id"] for x in rules}]
        else:
            need = []
        texts = {x["id"]: norm(x["text"]) for x in rules}
        for i in need:
            value = norm(check[i])
            if value.startswith("미반영:"):
                if not value[len("미반영:"):].strip():
                    raise Reject(f"check {i}의 미반영 이유가 비어 있습니다. \"미반영: <이유>\"로 적으세요.")
                unreflected.append(i)
                continue
            if not bodies:
                raise Reject(f"check {i}: 산출물이 모두 비텍스트(그림·압축 등)라 인용할 본문이 없습니다. \"미반영: 이유\"로 적거나 check를 생략하세요.")
            m = QUOTE.search(value)
            quote = norm(next(g for g in m.groups() if g) if m else value)
            if len(quote) < MIN_QUOTE:
                raise Reject(f"check {i}의 인용이 너무 짧습니다({MIN_QUOTE}자 이상): '{quote}'. 산출물 본문의 문장을 더 길게 인용하세요.")
            if not any(quote in b for b in bodies):
                raise Reject(f"check {i}의 인용이 산출물에 없습니다: '{quote}'. 산출물 본문에 그대로 있는 문장을 따옴표로 인용하거나, "
                             "본문에 넣지 않았다면 \"미반영: 이유\"로 적으세요.")
            if quote == texts[i] or quote.rstrip(".") == texts[i].rstrip("."):  # 규칙 문장을 본문에 써 넣고 그대로 인용한 것: 증거가 아니다
                self_quoted.append(i)
        if need:
            ev["check"] = {i: check[i] for i in need}
        if self_quoted:
            ev["self_quoted"] = self_quoted
        rebuilt = commit(d, index, wid, ev)
        write_atomic(wpath, json.dumps({"tool": tool, "session_id": sid, "seq": ev["seq"]}) + "\n")
        update_session(d, tool, sid, seen=(wid, ev["seq"]), saved_turn=(sess or {}).get("turn", 0))
        missing = own_missing_artifacts(d, events + [ev], rebuilt, (tool, sid))
    print(json.dumps({"ok": True, "work": wid, "saved": ev["id"], "seq": ev["seq"], "verified": True, "unreflected": unreflected,
                      "self_quoted": self_quoted, **({"artifacts_missing": missing} if missing else {}),
                      "ignored_duplicates": [x if isinstance(x, str) else x["text"] for x in ignored],
                      "decisions": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["decisions"]],
                      "constraints": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["constraints"]],
                      "waiting": rebuilt["waiting"], "next_action": rebuilt["next_action"], **off_flag(d),
                      **core_report(events), **hooks_report(d, tool, sid)}, ensure_ascii=False))


# --- 작업 선택 ---

def need_quote(args, usage, said="작업을 지정한"):
    if not str(args.quote or "").strip():
        raise Reject(f"사용자 원문이 필요합니다: {usage}. 사용자가 {said} 말을 그대로 --quote에 넣으세요.")


def cmd_version(args):
    """설치 확인용: 코어 버전과 원장 형식. .worklog 없이도 동작한다."""
    print(json.dumps({"version": VERSION, "format": FORMAT}))


def cmd_works(args):
    d = store(args.root)
    index = (load_index(d) if d.is_dir() else None) or {"works": {}}
    who, current = try_identity(args), None
    if who and d.is_dir():
        try:
            current = (load_session(d, *who) or {}).get("current_work")
        except SessionCorrupt:
            pass
    print(json.dumps({"ok": True, "current_work": current,
                      "works": [dict(id=i, **w) for i, w in sorted_works(index["works"])], **off_flag(d)}, ensure_ascii=False))


def cmd_use(args):
    if not args.arg:
        raise Reject('use <id> --quote "<사용자 원문>" 형식입니다.')
    tool, sid = identity(args)
    need_quote(args, f'use {args.arg} --quote "<사용자 원문>"')
    d = store(args.root)
    if not d.is_dir():
        raise Reject(f"없는 작업입니다: {args.arg}. 작업 목록: (없음)")
    with locked(d):
        w = entry(index_or_new(d), args.arg)
        # use는 show처럼 현황을 보여 주고 읽은 것으로 친다: use 직후 save가 "show 먼저"로 막히지 않는다
        text = read_work(d, args.arg, w["title"], (tool, sid), current_work=args.arg,
                         selected_turn=session_or_new(d, tool, sid)["turn"])
    print(f"[use] 현재 작업: {args.arg} · {w['title']} · {w['status']}\n" + off_note(d) + hooks_note(d, (tool, sid)) + text, end="")


def other_constraints(d, index, wid):
    """Active constraints of the other works, as "id N개" parts — a new work inherits none of them."""
    parts = []
    for other in sorted(index["works"]):
        if other == wid:
            continue
        try:
            n = len(fold(read_events(work_dir(d, other))[0])[0]["constraints"])
        except (Reject, OSError, ValueError):
            continue
        if n:
            parts.append(f"{other} {n}개")
    return parts


def cmd_new_work(args):
    title = NEW_WORK_PREFIX.sub("", str(args.arg or "")).strip()  # "새 작업: 제목"을 그대로 넣어도 제목만 남긴다
    if not title:
        raise Reject('new-work "<제목>" --quote "<사용자 원문>" 형식입니다.')
    tool, sid = identity(args)
    need_quote(args, f'new-work "{title}" --quote "<사용자 원문>"')
    d = store(args.root)
    d.mkdir(exist_ok=True)
    with locked(d):
        index = index_or_new(d)
        works = works_root(d)
        wid = make_id(title, set(index["works"]) | ({p.name for p in works.iterdir()} if works.is_dir() else set()))
        at = now()
        index["works"][wid] = {"title": title, "status": "ACTIVE", "created_at": at, "updated_at": at, "last_seq": 0}
        work_dir(d, wid).mkdir(parents=True)
        write_index(d, index)
        update_session(d, tool, sid, current_work=wid, selected_turn=session_or_new(d, tool, sid)["turn"])
        others = other_constraints(d, index, wid)
    result = {"ok": True, "id": wid, "title": title, "current_work": wid}
    if others:
        result["notice"] = ("다른 작업의 유효 제약은 이 작업에 적용되지 않습니다: " + ", ".join(others)
                            + ". 이어받을 결정·제약은 이 작업을 맡긴 프롬프트에 적힌 것만 다시 저장하세요. 프롬프트에 없으면 사용자에게 확인하세요.")
    print(json.dumps({**result, **off_flag(d), **hooks_report(d, tool, sid)}, ensure_ascii=False))


def set_status(args, status, summary):
    """archive/reopen: CHECKPOINT event with the status change + index status. No quote needed."""
    wid = args.arg
    tool, sid = identity(args)
    d = store(args.root)
    if not d.is_dir():
        raise Reject(f"없는 작업입니다: {wid}. 작업 목록: (없음)")
    with locked(d):
        index = index_or_new(d)
        if entry(index, wid)["status"] == status:
            raise Reject(f"작업 {wid}는 이미 {status}입니다.")
        events, prev = read_events(work_dir(d, wid))
        ev = new_event(events, prev, "CHECKPOINT", tool, sid, summary, None, [], {"status": status})
        commit(d, index, wid, ev)
        if session_or_new(d, tool, sid)["last_seen"].get(wid, 0) == len(events):  # 최신을 보던 세션은 자기 사건 뒤도 최신
            update_session(d, tool, sid, seen=(wid, ev["seq"]))
    print(json.dumps({"ok": True, "work": wid, "status": status, "saved": ev["id"], "seq": ev["seq"]}, ensure_ascii=False))


def cmd_archive(args):
    set_status(args, "COMPLETED", "작업 보관")


def cmd_reopen(args):
    set_status(args, "ACTIVE", "작업 재개")


# --- 읽기 ---

def current_work(d, who, index):
    """This session's current work id if it is still in the index, else None."""
    if not who:
        return None
    try:
        cur = (load_session(d, *who) or {}).get("current_work")
    except SessionCorrupt:
        return None
    return cur if cur in index["works"] else None


def cmd_show(args):
    d = store(args.root)
    index = load_index(d) if d.is_dir() else None
    if not index or not index["works"]:
        print(off_note(d) + 'Worklog 작업 없음. 사용자가 새 작업을 지정하면 new-work "<제목>" --quote "<사용자 원문>"으로 만든다.')
        return
    who = try_identity(args)
    wid = args.work or current_work(d, who, index)
    if not wid:
        print(off_note(d) + "현재 작업 없음. " + NO_WORK_GUIDE + "\n작업 목록:\n"
              + "\n".join(f"- {i} · {w.get('title')} · {w.get('status')} · {w.get('updated_at')}" for i, w in sorted_works(index["works"])))
        return
    title = entry(index, wid)["title"]
    with locked(d):  # 잠금 뒤에 읽어야 동시 저장 이후의 투영을 과거 seq로 되돌리지 않는다
        text = read_work(d, wid, title, who)
    print(off_note(d) + text, end="")


def read_work(d, wid, title, who, **session_changes):
    """Inside locked(d): one work's state text (projection repaired from the ledger if stale) and, when the
    session is known, mark it as seen (plus session_changes). Shared by show and use."""
    wd = work_dir(d, wid)
    events, _ = read_events(wd)
    state, _ = fold(events)
    note = ""
    if events and not all(projection_ok(wd, state, wid, title, events)):  # 하나라도 다르거나 없으면 둘 다 다시 만든다
        project(wd, state, wid, title)
        note = "(현재 상태가 원장과 달라 원장에서 다시 만들었다)\n"
    newer = core_report(events)
    if newer:
        note += f"[Worklog 코어 경고] {newer['warning_core']}\n"
    note += artifacts_note(own_missing_artifacts(d, events, state, who))
    if who:  # 세션을 모르는 사람의 show는 읽기만 한다
        update_session(d, *who, seen=(wid, len(events)), **session_changes)
    return note + (render(state, wid, title) if events else f"# Worklog 현재 상태 — {wid} · {title}\n기록 없음. 첫 save가 기록을 만든다.\n")


def check_work(d, wid, title):
    wd = work_dir(d, wid)
    events, _ = read_events(wd)
    state, _ = fold(events)
    ok_json, ok_md = projection_ok(wd, state, wid, title, events)
    return {"work": wid, "ok": ok_json and ok_md, "events": len(events), "status": state["status"],
            "state_json": ok_json, "state_md": ok_md, "artifacts": artifacts_check(d, state), **core_report(events)}


def cmd_verify(args):
    d = store(args.root)
    if not d.is_dir():
        result = verify_result(d, args, {"works": {}})
    else:
        with locked(d):  # index·원장·투영을 저장 도중이 아닌 한 시점에서 함께 읽는다
            result = verify_result(d, args, load_index(d) or {"works": {}})
    print(json.dumps(result, ensure_ascii=False))
    if not result["ok"]:
        sys.exit(1)


def verify_result(d, args, index):
    if not args.all:
        wid = args.work or current_work(d, try_identity(args), index)
        if not wid:
            raise Reject("현재 작업이 없습니다. verify --work <id> 또는 verify --all로 지정하세요.")
        r = check_work(d, wid, entry(index, wid)["title"])
        del r["status"]
        return r
    results, mismatched, warnings = [], [], []
    for wid, w in sorted(index["works"].items()):
        try:
            r = check_work(d, wid, w["title"])
            if (w["last_seq"], w["status"]) != (r["events"], r["status"]):
                mismatched.append(wid)
            writer = work_dir(d, wid) / "writer.json"
            if os.path.lexists(writer) and read_writer(writer) is None:
                warnings.append(f"{wid}: writer.json 읽기 불가")
        except Reject as e:
            r = {"work": wid, "ok": False, "error": str(e)}
        results.append(r)
    works = works_root(d)
    folders = {p.name for p in works.iterdir() if p.is_dir()} if works.is_dir() else set()
    idx = {"missing_folders": sorted(set(index["works"]) - folders), "unindexed_folders": sorted(folders - set(index["works"])),
           "mismatched": mismatched}
    idx["ok"] = not any(idx.values())
    result = {"ok": idx["ok"] and all(r["ok"] for r in results), "works": results, "index": idx, "warnings": warnings}
    who = try_identity(args)
    if who:  # 이 세션에서 Hook 3개가 실제로 돌았는지(세션 파일의 hooks_seen). 미작동이면 warning
        report = hooks_report(d, *who)
        if report:
            result["hooks"] = {"session": f"{who[0]}:{who[1]}", **report["hooks"]}
            for key in ("warning", "warning_install", "warning_worktree"):
                if key in report:
                    result["hooks"][key] = report[key]
    return result


# --- 켜고 끄기 (.worklog/off 표식, 원장 아님) ---

OFF_NOTE = "[Worklog OFF] 이 프로젝트의 Worklog가 꺼져 있다(.worklog/off). 켜려면 사용자가 요청한 뒤 `wl.py on`.\n"


def is_off(d):
    return os.path.lexists(d / "off")


def off_flag(d):
    """Top-level JSON warning for save·skip·new-work·works while off."""
    return {"off": True} if is_off(d) else {}


def off_note(d):
    """Text warning line for show·use while off."""
    return OFF_NOTE if is_off(d) else ""


def off_marker(d):
    """.worklog/off as a dict ({} when unreadable or a link — never followed), or None when Worklog is on."""
    path = d / "off"
    if not os.path.lexists(path):
        return None
    if path.is_symlink():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def installed(args):
    d = store(args.root)
    if not d.is_dir():
        raise Reject(f"Worklog가 설치되지 않았습니다({d} 없음). 켜거나 끌 대상이 없습니다.")
    return d


def cmd_off(args):
    """Turn Worklog off for the whole project. The user's words (--quote) are required so a model cannot turn it off
    by itself; the reason is optional. An existing marker is kept."""
    usage = 'off --quote "<사용자 원문>" [--reason "<이유>"]'
    if args.arg:
        raise Reject(f"이유는 --reason으로 넣습니다: {usage}")
    need_quote(args, usage, said="끄라고 한")
    d = installed(args)
    with locked(d):
        path = contained(d / "off", d)
        old = off_marker(d)
        if old is None:
            who = try_identity(args)
            marker = {"at": now(), "reason": str(args.reason or "").strip() or None,
                      "by": f"{who[0]}:{who[1]}" if who else None, "quote": args.quote}
            write_atomic(path, json.dumps(marker, ensure_ascii=False) + "\n")
    if old is not None:
        print(json.dumps({"ok": True, "off": True, "already": True, "at": old.get("at"), "reason": old.get("reason"),
                          "message": f"이미 꺼져 있습니다(시각: {old.get('at')}, 이유: {old.get('reason') or '없음'}). 기존 표식을 유지합니다."},
                         ensure_ascii=False))
        return
    print(json.dumps({"ok": True, "off": True, "at": marker["at"], "reason": marker["reason"],
                      "message": "Worklog를 껐습니다(이 프로젝트 전체). 꺼진 기간은 기록에 남지 않습니다. 켜려면 on."}, ensure_ascii=False))


def cmd_on(args):
    """Remove the marker and report how long Worklog was off. Already on is not an error."""
    d = installed(args)
    with locked(d):
        path = contained(d / "off", d)
        old = off_marker(d)
        if old is not None:
            path.unlink()
    if old is None:
        print(json.dumps({"ok": True, "off": False, "already": True, "message": "이미 켜져 있습니다."}, ensure_ascii=False))
        return
    try:
        seconds = max(0, int((datetime.datetime.now(datetime.timezone.utc)
                              - datetime.datetime.fromisoformat(str(old.get("at")).replace("Z", "+00:00"))).total_seconds()))
        span = f"{seconds}초" if seconds < 120 else f"{seconds // 60}분"
    except (ValueError, TypeError):
        seconds, span = None, "알 수 없음"
    print(json.dumps({"ok": True, "off": False, "off_since": old.get("at"), "off_seconds": seconds,
                      "message": f"Worklog를 켰습니다. 꺼져 있던 기간: {span}. 그동안 바뀐 것이 있으면 다음 save에 적는다."},
                     ensure_ascii=False))


# --- Hook ---

def hook_input(args):
    """Hook event from stdin → (store dir, (tool, session) or None, event).
    Connected = .worklog/ directory exists; otherwise store dir is None and every hook stays silent."""
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = {}
    if not isinstance(event, dict):
        event = {}
    cwd = event.get("cwd")
    d = store(cwd if isinstance(cwd, str) and cwd else args.root)
    if not d.is_dir():
        return None, None, event
    sid = event.get("session_id")
    if isinstance(sid, str) and sid:
        args.session = sid
    return d, try_identity(args), event


def list_line(d, wid, w):
    try:
        nxt = fold(read_events(work_dir(d, wid))[0])[0]["next_action"] or "(미정)"
    except (Reject, OSError, ValueError):
        nxt = "(읽기 실패)"
    nxt = nxt if len(nxt) <= 60 else nxt[:60] + "…"
    return f"- {wid} · {w.get('title')} · {w.get('status')} · {w.get('updated_at')} · 다음: {nxt}"


def injection(d, who):
    """SessionStart text → (status, body). Marks the current work as seen by this session."""
    index = load_index(d) or {"works": {}}
    works, out = index["works"], []
    pm = d / "project.md"
    if pm.is_file():
        text = pm.read_text(encoding="utf-8", errors="replace").strip()
        out += ["## 프로젝트 공통 (project.md)",
                text[:PROJECT_MAX] + (f"\n…({PROJECT_MAX:,}자에서 잘림)" if len(text) > PROJECT_MAX else "")]
    live = sorted(((i, w) for i, w in works.items() if w.get("status") in ("ACTIVE", "PAUSED")),
                  key=lambda x: x[1].get("updated_at") or "", reverse=True)
    out.append(f"## 작업 목록 (ACTIVE·PAUSED, 최근 갱신순 최대 {LIST_MAX}개 / 전체 {len(works)}개)")
    out += [list_line(d, i, w) for i, w in live[:LIST_MAX]] or ["- (없음)"]
    done = sorted(((i, w) for i, w in works.items() if w.get("status") == "COMPLETED"),
                  key=lambda x: x[1].get("updated_at") or "", reverse=True)
    if done:  # 끝난 작업도 "<id> 이어서"로 바로 이을 수 있으니 최근 것은 보여 준다
        out.append(f"- 그 외 COMPLETED {len(done)}개: " + ", ".join(f"{i} · {w.get('title')} ({(w.get('updated_at') or '')[:10]})"
                                                              for i, w in done[:DONE_MAX]) + (" …" if len(done) > DONE_MAX else ""))
    cur = None
    if who:
        with locked(d):
            cur = current_work(d, who, index)
            if cur:
                events, _ = read_events(work_dir(d, cur))
                update_session(d, *who, seen=(cur, len(events)))
            mark_hook(d, who, "SessionStart")
    if cur:
        title = works[cur]["title"]
        out.append(f"## 현재 작업: {cur} · {title}")
        if events:
            st = fold(events)[0]
            out += [x for x in (artifacts_note(own_missing_artifacts(d, events, st, who)).rstrip("\n"),) if x]
            out.append(render(st, cur, title).rstrip("\n"))
        else:
            out.append("기록 없음. 첫 save가 기록을 만든다.")
    else:
        out += ["## 현재 작업 없음", NO_WORK_GUIDE]
    return ("EMPTY" if not works else "PROVIDED" if cur else "NO_CURRENT_WORK"), "\n".join(out) + "\n"


def cmd_hook(args):
    """SessionStart hook: prints {"hookSpecificOutput": {..., "additionalContext": ...}} (format: injection()).
    Valid without a session ID; then no session file is touched and there is no current work."""
    d, who, _ = hook_input(args)
    if not d:
        return
    off = off_marker(d)
    if off is not None:  # 꺼짐: 한 줄만 주입하고 세션 파일은 만들거나 갱신하지 않는다
        line = (f"[Worklog {FORMAT} SessionStart | OFF | root={d.parent}] Worklog가 꺼져 있다(이유: {norm(off.get('reason') or '') or '없음'}, "
                f"시각: {norm(off.get('at') or '') or '알 수 없음'}). 사용자가 켜 달라고 하기 전까지 Worklog 절차를 적용하지 않는다.\n")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": line}}, ensure_ascii=False))
        return
    try:
        status, text = injection(d, who)
    except (Reject, OSError, ValueError) as e:
        text, status = f"Worklog 현재 상태를 읽지 못함: {e}. 파일을 바꾸기 전에 `wl.py show`로 확인한다.\n", "UNAVAILABLE"
    head = f"[Worklog {FORMAT} SessionStart | {status} | root={d.parent}]\n이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.\n"
    spawn_update_check()
    head += update_note()
    if who:
        stale = install_report(d, who[0])
        if stale:
            head += f"[Worklog 사본 경고] {stale['warning_install']}\n"
    if (d.parent / ".git").is_file():
        head += f"[Worklog worktree 경고] {WORKTREE_WARNING} 사용자에게 알린다.\n"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": head + text}},
                     ensure_ascii=False))


def cmd_turn_start(args):
    """UserPromptSubmit hook: turn += 1. No output. Does nothing while off."""
    d, who, _ = hook_input(args)
    if d and who and not is_off(d):
        with locked(d):
            s = session_or_new(d, *who)
            update_session(d, *who, turn=s["turn"] + 1, hooks_seen=dict(s["hooks_seen"], UserPromptSubmit=now()))


def cmd_stop_hook(args):
    """Stop hook: block once if this turn has no save, skip or work selection. Does nothing while off.
    When the turn ends (satisfied, or already blocked once: stop_hook_active) the turn counter advances here too, so a next
    turn that starts without UserPromptSubmit (`!` shell input, another session's notification) still needs its own save or skip."""
    d, who, event = hook_input(args)
    if not (d and who) or is_off(d):
        return
    try:
        with locked(d):
            s = load_session(d, *who) or new_session()
            done = s["turn"] in (s["saved_turn"], s["skipped_turn"], s["selected_turn"]) or event.get("stop_hook_active") is True
            update_session(d, *who, hooks_seen=dict(s["hooks_seen"], Stop=now()), **({"turn": s["turn"] + 1} if done else {}))
    except SessionCorrupt as e:
        if event.get("stop_hook_active") is not True:  # 한 번 막힌 뒤에는 다시 막지 않는다(무한 반복 방지)
            print(json.dumps({"decision": "block", "reason": f"Worklog: 세션 파일을 읽을 수 없습니다({e}). "
                              "save 또는 skip으로 다시 만든 뒤 마치세요."}, ensure_ascii=False))
        return
    if done:
        return
    q = shlex.quote
    skip = f'python3 -B {q(str(Path(__file__).resolve()))} skip "이유" --tool {q(who[0])} --session {q(who[1])} --root {q(str(d.parent))}'
    print(json.dumps({"decision": "block", "reason": "Worklog: 이번 턴에 save가 없습니다. 기록할 것이 있으면 save, "
                      f"읽기 전용 턴이거나 작업이 지정되지 않았으면 `{skip}`를 실행한 뒤 마치세요."}, ensure_ascii=False))


def cmd_skip(args):
    """Read-only turn: skipped_turn = turn. Writes nothing to the ledger."""
    if not str(args.arg or "").strip():
        raise Reject('skip에는 이유가 필요합니다: wl.py skip "읽기 전용: 질문에 답만 함"')
    d = store(args.root)
    tool, sid = identity(args)
    if not d.is_dir():
        print(json.dumps({"ok": True, "turn": 0}))
        return
    with locked(d):
        s = session_or_new(d, tool, sid)
        turn = s["turn"]
        update_session(d, tool, sid, skipped_turn=turn)
        missing, cur = [], s.get("current_work")
        if cur and work_dir(d, cur).is_dir():
            try:
                evs, _ = read_events(work_dir(d, cur))
                missing = own_missing_artifacts(d, evs, fold(evs)[0], (tool, sid))
            except (Reject, OSError, ValueError):
                pass
    print(json.dumps({"ok": True, "turn": turn, **({"artifacts_missing": missing} if missing else {}), **off_flag(d),
                      **hooks_report(d, tool, sid)}, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wl.py", description="Worklog 공용 코어 (형식 2)")
    commands = {"works": cmd_works, "use": cmd_use, "new-work": cmd_new_work, "show": cmd_show, "save": cmd_save,
                "skip": cmd_skip, "verify": cmd_verify, "archive": cmd_archive, "reopen": cmd_reopen,
                "off": cmd_off, "on": cmd_on, "hook": cmd_hook, "turn-start": cmd_turn_start, "stop-hook": cmd_stop_hook,
                "version": cmd_version, "update": cmd_update}
    ap.add_argument("command", choices=[*commands, "help"])
    ap.add_argument("arg", nargs="?", help="skip의 이유 / use·archive·reopen의 작업 id / new-work의 제목 / update의 check·rollback")
    ap.add_argument("--mode", choices=UPDATE_MODES, help="update: 갱신 알림 방식 설정(notify·off)")
    ap.add_argument("--root")
    ap.add_argument("--tool")
    ap.add_argument("--session")
    ap.add_argument("--quote", help="use·new-work: 사용자가 작업을 지정한 원문 / off: 사용자가 끄라고 한 원문")
    ap.add_argument("--reason", help="off: 끄는 이유(선택)")
    ap.add_argument("--work", help="show·verify: 대상 작업 id")
    ap.add_argument("--all", action="store_true", help="verify: 모든 작업 + index 일관성")
    args = ap.parse_intermixed_args(argv)  # 3.9 argparse도 `skip --tool claude "이유" --root …`처럼 섞인 순서를 받는다
    args.root = args.root or os.getcwd()
    if args.command == "help":
        print(f"worklog core {VERSION} (format {FORMAT})\n" + SAVE_HELP)
        return
    try:
        if args.command in ("archive", "reopen") and not args.arg:
            raise Reject(f"{args.command} <id> 형식입니다.")
        commands[args.command](args)
    except (Reject, OSError, ValueError) as e:  # traceback 대신 구조화된 거부
        error = str(e) if isinstance(e, Reject) else f"{type(e).__name__}: {e}. 사용자에게 보고하세요."
        if args.command in ("hook", "turn-start", "stop-hook"):  # Hook은 도구를 멈추지 않는다
            print(f"Worklog {args.command}: {error}", file=sys.stderr)
            return
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
