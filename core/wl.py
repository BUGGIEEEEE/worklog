#!/usr/bin/env python3
"""Worklog shared core (format 2): several works per project, one append-only event log per work.

Commands:  works | use | new-work | show | save | skip | verify | archive | reopen | reassign | rename | off | on | version | update | help
           | hook | turn-start | stop-hook
Storage:   <root>/.worklog/{index.json, project.md?, works/<id>/{events.jsonl, state.json, state.md, writer.json},
           sessions/<tool>_<session>.json, install.json?, .lock, off?}   (off = 이 프로젝트의 Worklog가 꺼짐. 원장 아님)
Connected: a folder whose .worklog/ exists (WL_HOME, ~/.worklog, only with index.json). The first new-work creates it
           (user-level install, 2.21.0) and the installer's --root mode creates it too; the hooks say NOT_CONNECTED elsewhere.
Root:      --root as given (hooks too); without it, commands use candidate_root(cwd) and hooks candidate_root(event cwd)
           (2.25.0): cwd when it is connected, else the nearest
           folder with .worklog/index.json up to the git top level, else the git top level, else (not git) cwd.
Standard library only. Never runs business commands.
"""
import argparse, datetime, fcntl, hashlib, json, os, re, shlex, subprocess, sys, time, uuid
from contextlib import contextmanager
from pathlib import Path

FORMAT = "worklog/2"
VERSION = "2.26.1"  # 코어·규칙 버전(CHANGELOG.md와 같아야 한다). FORMAT은 원장 구조 전용
TYPES = ["REQUEST", "APPROVAL", "D_USER", "D_AGENT", "ASSUMPTION", "RESULT", "VERIFICATION",
         "BLOCKER", "CORRECTION", "CHECKPOINT", "HANDOFF", "CHANGE", "Q",
         "WRITER_ACQUIRED", "WRITER_RELEASED"]
USER_TYPES = {"REQUEST", "APPROVAL", "D_USER"}
REMOVE_TYPES = {"D_USER", "APPROVAL", "CORRECTION"}
STATUSES = ["ACTIVE", "PAUSED", "BLOCKED", "COMPLETED", "CANCELLED"]
# Per-tool differences in one table (2.26.1). Order = the session-variable lookup order of identity(). A tool not listed (or
# none) behaves like claude: hook_tool(). Values only; the judgements (agy's turn count, Stop dedup) stay in the hook functions.
#   env            session id variable (pi: set by the Worklog extension, 2.24.0)
#   marks          duplicate-delivery marks: "hook_keys" (claude·codex·pi: SessionStart/UserPromptSubmit/Stop keys, 2.25.0) or
#                  "agy" (agy_pre/agy_stop, a turn started by the first PreInvocation, a second SessionStart before any turn, 2.24.2)
#   inject         SessionStart output: "additionalContext" (hookSpecificOutput) or "injectSteps" (agy hooks.json, 2.24.0)
#   stop_decision  the Stop hook's "decision" when it blocks
#   empty_reply    what a hook prints when it has nothing to say (agy's hooks.json wants a JSON object; the others print nothing)
#   cancel_reasons Stop terminationReason values that are never blocked (agy)
#   hook_warning   whether a session file with no hook record gets HOOK_WARNING (pi: hooks only with the user-level extension)
# The hook payload keys (cwd or agy's workspacePaths[0], session_id or agy's conversationId) are read the same way for every tool.
HOOK_TOOLS = {
    "codex": {"env": "CODEX_THREAD_ID", "marks": "hook_keys", "inject": "additionalContext", "stop_decision": "block",
              "empty_reply": None, "cancel_reasons": (), "hook_warning": True},
    "claude": {"env": "CLAUDE_CODE_SESSION_ID", "marks": "hook_keys", "inject": "additionalContext", "stop_decision": "block",
               "empty_reply": None, "cancel_reasons": (), "hook_warning": True},
    "agy": {"env": "ANTIGRAVITY_CONVERSATION_ID", "marks": "agy", "inject": "injectSteps", "stop_decision": "continue",
            "empty_reply": "{}", "cancel_reasons": ("USER_CANCELED", "ERROR"), "hook_warning": True},
    "pi": {"env": "PI_SESSION_ID", "marks": "hook_keys", "inject": "additionalContext", "stop_decision": "block",
           "empty_reply": None, "cancel_reasons": (), "hook_warning": False},
}
TOOL_ENV = [(name, t["env"]) for name, t in HOOK_TOOLS.items()]
WORK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ID_MAX = 40
PROJECT_MAX = 4000
LIST_MAX = 10
DONE_MAX = 3      # SessionStart 목록 뒤에 보여 주는 최근 COMPLETED 작업 수
UNSEEN_MAX = 20   # show·use·주입의 "못 본 사건" 절에 보이는 최대 사건 수(2.23.0, 가정값)
ART_MAX = 15      # state.md: 산출물이 이보다 많으면 폴더별 요약
NEW_WORK_PREFIX = re.compile(r"^\s*새\s*작업\s*[:：]\s*")
WORKTREE_WARNING = ("git worktree 안입니다. 여기서 저장한 기록은 본 저장소와 갈라져 병합 때 .worklog/works/*/events.jsonl이 충돌합니다. "
                    "기록은 본 저장소 세션에서 하고, 여기서 저장했다면 병합 전에 충돌을 사람이 정리하세요.")
HOOK_WARNING = ("Hook 미작동 의심: 이 세션 파일에 Hook 기록이 하나도 없습니다(SessionStart·UserPromptSubmit·Stop). Hook이 꺼져 있거나 "
                "신뢰되지 않았거나 세션 ID가 다릅니다. Codex는 /hooks에서 신뢰, Claude Code는 .claude/settings.local.json을 확인하고 사용자에게 보고하세요.")
STARTED = time.time()  # this process's start: a Stop hook that began before the previous Stop of its session finished is a duplicate (2.25.0)
SESSIONSTART_DUP = 5  # seconds: the same SessionStart source again within this is a duplicate registration (2.25.0)
NO_WORK_GUIDE = ("사용자에게 작업을 지정받을 때까지 저장하지 않는다. 지정이 없으면 한 번 묻고 skip으로 마친다. "
                 "작업이 하나뿐이고 \"이어서\"면 그 작업을 use한다.")
EMPTY_GUIDE = ("기존 작업이 없다. 첫 기록 대상 요청에서 묻지 않고 new-work로 새 작업을 만들고 그 턴에 save한다"
               "(제목은 사용자가 주면 그대로, 없으면 요청에서 정한다).")  # 2.25.0, auto=on. auto=off: NO_WORK_GUIDE
NOT_CONNECTED_HEAD = "Worklog에 연결되지 않은 폴더입니다({root}에 .worklog 없음)."  # show's first line (2.26.0); the line after it is not_connected_line()
NOT_CONNECTED = (NOT_CONNECTED_HEAD + " 사용자가 `새 작업: <제목>`이라 하면 "
                 "`new-work \"<제목>\" --quote \"<원문>\"`이 이 폴더를 연결합니다. 그 전에는 Worklog 절차(작업 지정 질문·save·skip)를 적용하지 않습니다.")
FIRST_CONNECT_NOTICE = "첫 연결 턴: Hook 세션 파일이 없어 hooks는 null(다음 턴부터 true/false)."  # 2.26.0 (D48)

SAVE_HELP = """save: 턴마다 한 번, stdin으로 JSON 하나를 넣는다.  예) python3 -B wl.py save <<'EOF' ... EOF
{
  "work": "habit-plan",                    # 선택. 생략하면 이 세션의 현재 작업(use/new-work로 정함)
  "type": "REQUEST",                       # REQUEST APPROVAL D_USER D_AGENT ASSUMPTION RESULT VERIFICATION BLOCKER CORRECTION CHECKPOINT HANDOFF CHANGE Q
  "summary": "이번 턴에 일어난 일 한두 문장",
  "quote": "사용자 원문 일부(그대로)",      # REQUEST/APPROVAL/D_USER, 목표 설정, 사용자 제약 해제에 필수
  "goal": "최초 목표",                     # 처음 한 번만. 생략하면 첫 save가 작업 제목을 목표로 쓴다. 이후 값 변경은 decisions(replaces)로
  "decisions": [{"text": "11분으로 변경(집중 유지)", "replaces": "D1"},
                {"text": "3·5·3분 배분(모델 제안)", "source": "model"}],
  "constraints": ["다른 프로젝트 자료 조회 금지(사용자 변경 전까지)"],
  "constraints_remove": {"C2": "해제 근거"},   # [사용자] 제약: type D_USER/APPROVAL/CORRECTION + quote. [모델] 제약: 사유만으로 해제. 같은 제약 재입력은 자동 무시
  "waiting": ["note-guide.md는 다음 요청까지 작성 보류", "확인 필요: 2화는 원작 282행부터라고 가정"],  # 전체 교체. 생략하면 유지, []면 비움. 확인 안 된 가정도 여기에
  "next_action": "다음 행동",
  "status": "ACTIVE",                      # ACTIVE PAUSED BLOCKED COMPLETED CANCELLED. 사용자가 작업이 끝났다고 말하기 전까지 COMPLETED로 바꾸지 않는다
  "artifacts": [{"path": "note-guide.md"}],
  "artifacts_moved": {"note-guide.md": "docs/note-guide.md"},  # 기록한 산출물 파일을 옮겼을 때 옛 경로 → 새 경로(새 경로 파일이 있어야 한다)
  "artifacts_gone": [{"path": "draft.md", "reason": "사용자가 지웠다고 확인"}],  # 기록한 산출물을 영구히 지웠을 때(사용자 확인 뒤). 누락 보고·verify missing에서 빠진다
  "check": {"D1": "'저녁 식사 후 11분'", "C1": "미반영: 알림은 만들지 않았고 본문에 넣을 내용이 아님"}
                                           # 텍스트 산출물이 있으면 모든 유효 결정·제약 ID 필수. 값은 둘 중 하나:
                                           # ① 규칙이 지켜졌음을 보여 주는 산출물 본문 구절(4자 이상)을 따옴표로 인용(본문에서 대조, 공백 무시)
                                           # ② "미반영: <이유>" — 작업 방식 제약이나 그림·압축 파일처럼 인용할 수 없는 것. 정상이며 결과의 unreflected에 표시
}
필드는 필요한 것만 넣는다.
"직전 사건과 같은 세션·같은 summary" 거부는 되감기(rewind) 뒤 재저장일 수 있다: show로 확인하고 이미 저장됐으면 skip, 새 내용이면 summary를 바꾼다.
결과의 artifacts_missing(또는 show의 "[Worklog 산출물 없음]"): 이 세션이 기록한 산출물이 실제 파일에 없다(되감기 코드 복원·이동·삭제). 같은 세션에는 한 번만 보인다.
명령: works(JSON 목록) · use <id> --quote · new-work "<제목>" --quote [--root <root>] [--force](id는 제목의 영문·숫자 슬러그, 한글만·숫자만이면 work·work-2) · show [--work <id>](현재 작업이 없으면 목록) · save · skip "이유"(원장에 쓰지 않음) · verify [--work <id> | --all] · archive/reopen <id>(COMPLETED/ACTIVE로) · reassign <잘못된 id> (<맞는 id> | --new "<제목>") --events E0003-E0005 --quote · rename <id> "<새 제목>" --quote · off --quote [--reason] · on"""
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


def is_wl_home(d):
    """d (a .worklog store) is the user's WL_HOME (~/.worklog: config, registry, user-level manifest)."""
    return Path(d).resolve() == WL_HOME.resolve()


def connected(d):
    """The store d is a connection: a directory that is not just WL_HOME (it counts only when it also holds works, i.e. the
    home folder itself is a Worklog project). Every "is this folder connected" check of the commands and hooks uses this."""
    return d.is_dir() and (not is_wl_home(d) or (d / "index.json").is_file())


def connected_here(p):
    """p/.worklog is a connection (see connected)."""
    return connected(p / ".worklog")


def has_works(p):
    """p/.worklog/index.json exists and p/.worklog is not WL_HOME (the upward search never joins the home folder's store)."""
    d = p / ".worklog"
    return (d / "index.json").is_file() and d.resolve() != WL_HOME.resolve()


def git_top(cwd):
    """The nearest folder at or above cwd with a .git entry (directory, or file in a worktree), or None."""
    for p in (cwd, *cwd.parents):
        if os.path.lexists(p / ".git"):
            return p
    return None


def root_info(cwd):
    """candidate_root (2.25.0) with its reasons: {root, cwd, git (top level or None), outside (a folder above the git top
    level whose Worklog records were not joined, or None)}. Rules (PLAN-auto-connect §6-2): cwd when it is connected
    (2.21.0 behaviour); inside git, the nearest folder up to the git top level with .worklog/index.json, else the git top
    level (no new store in a subfolder); not git: cwd (no upward search, so ~ or a temp folder above is never joined)."""
    cwd = Path(cwd).resolve()
    top = git_top(cwd)
    info = {"cwd": cwd, "git": top, "outside": None, "root": cwd}
    if connected_here(cwd) or top is None:
        return info
    path = (cwd, *cwd.parents)
    inside = path[1:path.index(top) + 1]
    info["root"] = next((p for p in inside if has_works(p)), top)
    info["outside"] = next((p for p in path[path.index(top) + 1:] if has_works(p)), None)
    return info


def candidate_root(cwd):
    return root_info(cwd)["root"]


def identity_how(args):
    """(tool, session id, how the tool was decided: "--tool 지정", "WL_TOOL" or "환경변수 <NAME>에서 추정"). 2.27.0 (U16): without
    --tool and WL_TOOL, two or more tool session variables at once (pi run inside Claude Code inherits CLAUDE_CODE_SESSION_ID)
    are refused instead of guessed — the first in TOOL_ENV order would read and write another tool's session file."""
    tool, sid = os.environ.get("WL_TOOL"), os.environ.get("WL_SESSION_ID")
    how = "WL_TOOL" if tool else None
    if getattr(args, "tool", None):
        tool, how = args.tool, "--tool 지정"
    if getattr(args, "session", None):
        sid = args.session
    if not (tool and sid):
        found = [(name, env) for name, env in TOOL_ENV if os.environ.get(env) and (not tool or tool == name)]
        if not tool and len(found) > 1:
            raise Reject(f"도구를 확정할 수 없습니다: {', '.join(f'{env}({name})' for name, env in found)}가 함께 있습니다. "
                         "--tool <codex|claude|agy|pi>를 지정하세요.")
        if found:
            name, env = found[0]
            tool, sid, how = name, sid or os.environ[env], how or f"환경변수 {env}에서 추정"
    if not (tool and sid):
        raise Reject("세션을 확인할 수 없습니다. --tool <codex|claude|agy|pi> --session <ID>를 지정하세요.")
    return tool, sid, how


def identity(args):
    return identity_how(args)[:2]


def call_note(tool, sid, how):
    """2.27.0 (U16): the end of a refusal that depends on this session's file — which session this call was judged to be."""
    return f" (이 호출: tool={tool} session={sid}, {how})"


def hook_tool(tool):
    """The HOOK_TOOLS row of a tool; any other name (or None) gets claude's row."""
    return HOOK_TOOLS.get(tool) or HOOK_TOOLS["claude"]


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


REASSIGNED_MAX = 20  # session "reassigned" marks kept (2.26.0)
SESSION_TURNS = ("turn", "saved_turn", "skipped_turn", "selected_turn", "blocked_turn")  # blocked_turn (2.24.0): the turn the Stop hook already blocked once


class SessionCorrupt(Exception):
    pass


def new_session():
    return {"current_work": None, "last_seen": {}, "hooks_seen": {}, "in_turn": False, "agy_pre": None, "agy_stop": None,
            "hook_keys": {}, "new_work_turn": None, "new_work_id": None, "reassigned": [], "missing_noted": [],
            **dict.fromkeys(SESSION_TURNS, 0)}  # in_turn (2.24.1): a model call of this turn has started. agy_pre/agy_stop (2.24.2): last PreInvocation/Stop event seen, so a hook registered twice (project + user hooks.json) acts once
    # hook_keys (2.25.0): the last SessionStart / UserPromptSubmit / Stop key of claude·codex hooks (a second identical call is a
    # duplicate registration and does nothing). new_work_turn (2.25.0): the turn of this session's last new-work.
    # new_work_id (2.26.0): the id that new-work was creating, written with new_work_turn before index.json (retry marker).
    # reassigned (2.26.0): ["<right id>:<refiled event id>@<turn>", …] (last REASSIGNED_MAX) written with current_work by
    # reassign's session step. missing_noted (2.27.0): ["path(Eid)", …] missing artifacts already reported to this session


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
    if not (isinstance(s["hook_keys"], dict) and all(isinstance(v, str) for v in s["hook_keys"].values())):
        s["hook_keys"] = {}  # 2.25.0 helper keys: a bad value only loses duplicate detection, it never makes the file corrupt
    if type(s["new_work_turn"]) is not int:
        s["new_work_turn"] = None
    if not isinstance(s["new_work_id"], str):
        s["new_work_id"] = None
    if not (isinstance(s["reassigned"], list) and all(isinstance(x, str) for x in s["reassigned"])):
        s["reassigned"] = []  # a bad value only loses the "user moved on" judgement of a reassign re-run
    if not (isinstance(s["missing_noted"], list) and all(isinstance(x, str) for x in s["missing_noted"])):
        s["missing_noted"] = []  # a bad value only reports a missing artifact once more
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


def mark_seen_if_current(d, tool, sid, wid, before, after):
    """A session that had read this work up to `before` has read its own event too (archive/reopen, reassign, rename)."""
    if session_or_new(d, tool, sid)["last_seen"].get(wid, 0) == before:
        update_session(d, tool, sid, seen=(wid, after))


def mark_hook(d, who, name):  # SessionStart also resets in_turn (2.24.1): a new or resumed session starts outside a turn
    """Inside locked(d): record that hook `name` ran for this session (self-diagnosis shown by save·skip·verify)."""
    seen = dict(session_or_new(d, *who)["hooks_seen"], **{name: now()})
    update_session(d, *who, hooks_seen=seen, **({"in_turn": False} if name == "SessionStart" else {}))


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


def manifest_entry(path, tool):
    """install.json[tool] as a dict, or None when the file, the entry or the JSON is missing or broken."""
    try:
        entry = json.loads(path.read_text(encoding="utf-8")).get(tool)
    except (OSError, ValueError, AttributeError):
        return None
    return entry if isinstance(entry, dict) else None


def parse_version(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


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


def auto_mode():
    """WL_HOME/config.json "auto": "off" keeps the 2.24 behaviour in folders that are not connected (wait for `새 작업:`);
    anything else, or no key, is "on" (2.25.0, user decision). A project's .worklog/off still wins inside it."""
    return "off" if home_json("config.json").get("auto") == "off" else "on"


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


# --- 연결 (2.21.0: 사용자 범위 설치에서는 new-work가 만든 .worklog/가 연결 신호다. 설치기의 --root 모드도 같은 함수를 쓴다) ---

GITIGNORE_LINES = (".worklog/",)
GITIGNORE_OLD = (".worklog/sessions/", ".worklog/.lock")  # written by 2.11.0–2.17.x; replaced by GITIGNORE_LINES
IGNORES_WORKLOG = {".worklog", ".worklog/", "/.worklog", "/.worklog/"}


def gitignore_text(path):
    """New .gitignore content: the old Worklog lines dropped and `.worklog/` appended unless .worklog is already ignored.
    None when nothing changes (or the file is unreadable as text)."""
    try:
        current = path.read_text() if path.exists() else ""
    except (OSError, UnicodeDecodeError):
        return None
    kept = [line for line in current.splitlines(keepends=True) if line.strip() not in GITIGNORE_OLD]
    body = "".join(kept)
    if not ({line.strip() for line in kept} & IGNORES_WORKLOG):
        body = body if (not body or body.endswith("\n")) else body + "\n"
        body += "".join(line + "\n" for line in GITIGNORE_LINES)
    return None if body == current else body


def register_install(root, tool):
    """Append {root: [tool, ...]} to WL_HOME/installs.json so uninstall_project.py --all-projects can find this project.
    Best effort: an unwritable home never fails the caller (returns None)."""
    registry = WL_HOME / "installs.json"
    try:
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        tools = data.get(str(root))
        tools = [t for t in tools if isinstance(t, str)] if isinstance(tools, list) else []
        if tool not in tools:
            tools.append(tool)
        data[str(root)] = tools
        WL_HOME.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return str(registry)
    except OSError:
        return None


def mark_connected(d, tool):
    """install.json[tool] = {version, connected_at, scope: "user"} unless the tool already has an entry (a project-level
    install keeps its rules_src_sha). True when written."""
    path = d / "install.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if isinstance(data.get(tool), dict):
        return False
    data[tool] = {"version": VERSION, "connected_at": now(), "scope": "user"}
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return True


def connect(root, tool):
    """What the installer's --root mode did for a project, done by new-work when it has just created .worklog/ (user-scope
    install): the `.worklog/` line in .gitignore of a git project (no backup: one appended line), the registry entry and
    the manifest entry. Best effort — (changed paths, notes about what failed)."""
    changed, notes = [], []
    if (root / ".git").exists():
        gi = root / ".gitignore"
        try:
            if gi.is_symlink():
                raise OSError("심볼릭 링크")
            text = gitignore_text(gi)
            if text is not None:
                write_atomic(gi, text)
                changed.append(str(gi))
        except OSError as e:
            notes.append(f".gitignore에 .worklog/ 줄을 더하지 못함({e}). 기록이 커밋되지 않게 직접 추가하세요.")
    registry = register_install(root, tool)
    if registry:
        changed.append(registry)
    else:
        notes.append(f"{WL_HOME / 'installs.json'}에 등록하지 못함(제거기 --all-projects 목록에 빠짐).")
    try:  # the home folder as a project: its .worklog is WL_HOME, whose install.json is the user-level manifest (left alone)
        if not is_wl_home(root / ".worklog") and mark_connected(root / ".worklog", tool):
            changed.append(str(root / ".worklog" / "install.json"))
    except OSError as e:
        notes.append(f"install.json을 쓰지 못함({e}).")
    return changed, notes


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


def note_once(d, who, missing):
    """Inside locked(d), 2.27.0 (U12 A): the entries of `missing` ("path(Eid)") not yet reported to this session, recorded in its
    missing_noted so show·use·SessionStart·save·skip report each one once per session. A file that comes back and goes again is
    not reported again in that session (simple rule); verify still checks every artifact."""
    if not (who and missing):
        return []
    s = session_or_new(d, *who)
    new = [m for m in missing if m not in s["missing_noted"]]
    if new:
        update_session(d, *who, missing_noted=s["missing_noted"] + new)
    return new


def artifacts_note(missing):
    """Text line for show·use·SessionStart (output only, never in state.md)."""
    return (f"[Worklog 산출물 없음] {ARTIFACTS_MISSING}: {', '.join(missing)}. 되감기(rewind) 코드 복원이나 이동·삭제가 원인일 수 있다. "
            "사용자에게 한 번 알린다(이 세션에는 다시 보이지 않는다). 옮겼거나 지웠다고 확인하면 save의 artifacts_moved·artifacts_gone으로 적는다.\n") if missing else ""


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


# --- 진단 (save·skip·show·use 결과와 SessionStart 주입의 경고: 설치 사본·코어 버전·worktree·Hook) ---

def install_report(d, tool):
    """{"warning_install": ...} when the manifest says this tool's rules copy was made from a different adapters/rules.md.
    A project-level install (.worklog/install.json entry with rules_src_sha) is compared there; a folder that was only
    connected by new-work (entry with scope "user") or has no entry is compared with the user-level manifest
    WL_HOME/install.json (2.21.0). Anything missing or broken means no warning and no error."""
    # 2.26.0: the home folder as a project has WL_HOME as its store, whose install.json is the user-level manifest: user scope
    entry = None if is_wl_home(d) else manifest_entry(d / "install.json", tool)
    user = entry is None or entry.get("scope") == "user"
    if user:
        entry = manifest_entry(WL_HOME / "install.json", tool)
        if entry is None:
            return {}
    recorded, current = entry.get("rules_src_sha"), rules_src_sha()
    if not (isinstance(recorded, str) and current) or recorded == current:
        return {}
    where = "--user" if user else f"--root {shlex.quote(str(d.parent))}"
    return {"warning_install": f"규칙 사본이 설치 당시(v{entry.get('version') or '?'})와 다릅니다(코어 {VERSION}). "
                               f"python3 -B {shlex.quote(str(INSTALLER))} --tool {tool} {where} 를 다시 실행하세요."}


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


def worktree_report(d):
    """{"warning_worktree": ...} when the project root is a git worktree (.git is a file, not a directory): its ledger diverges from the main checkout."""
    return {"warning_worktree": WORKTREE_WARNING} if (d.parent / ".git").is_file() else {}


def hooks_report(d, tool, sid):
    """{"hooks": {...}} for JSON results, plus "warning" when this session has no hook record at all (none of the three ran:
    not trusted, not installed, or another session id) and "warning_worktree" inside a git worktree. Pi has no hooks, so only
    the worktree warning is reported for it. A missing UserPromptSubmit alone is not a warning: a turn started by `!` shell
    input or by another session's notification does not fire it (observed 2026-10-15), while SessionStart and Stop still run."""
    try:
        s = load_session(d, tool, sid) or new_session()
    except SessionCorrupt:
        s = new_session()
    seen = s["hooks_seen"]
    if set(seen) == {"connect"}:  # 2.26.0 (D48): first connection turn, no hook has had a session file to mark yet → unknown, not false
        out = {"hooks": dict.fromkeys(("session_start", "turn_start", "stop")), "notice": FIRST_CONNECT_NOTICE}
    else:
        out = {"hooks": {"session_start": "SessionStart" in seen, "turn_start": "UserPromptSubmit" in seen, "stop": "Stop" in seen}}
    if not seen and hook_tool(tool)["hook_warning"]:  # "connect" (new-work created .worklog/ in this session, 2.21.0): the hooks ran before there was a session file to mark.
        out["warning"] = HOOK_WARNING  # pi: hooks exist only with the user-level extension (2.24.0); a project-level install has none, so no warning
    out.update(install_report(d, tool))
    out.update(worktree_report(d))
    return out


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


def title_slug(title):
    """Title → ASCII slug (a-z, 0-9, '-', ≤40), '' when nothing ASCII is left (make_id's base before the 'work' fallback)."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:ID_MAX].strip("-")


def make_id(title, taken):
    """Title → ASCII slug (a-z, 0-9, '-', ≤40); 'work' when nothing ASCII or only digits is left ("던전디펜스 1화" → "1" is
    not a usable id); '-2', '-3' on collision."""
    base = title_slug(title)
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
    for did, why in (c.get("decisions_remove") or {}).items():  # 2.25.0: only reassign writes it (a misfiled decision leaves this work)
        if did not in ids:
            raise Reject(f"decisions_remove {did}: 유효 결정에 없는 ID입니다. 현재: {sorted(ids)}")
        s["decisions"] = [x for x in s["decisions"] if x["id"] != did]
        s["superseded"].append({"id": did, "by_event": eid, "reason": why})
        ids.discard(did)
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
    for text in c.get("constraints", []):  # a {"text", "source"} item (2.25.0, reassign only) keeps the source it had in the other work
        text, src = (text["text"], text.get("source") or source) if isinstance(text, dict) else (text, source)
        s["constraints"].append({"id": f"C{ev['next_c']}", "text": text, "event": eid, "source": src})
        ev["next_c"] += 1
    for key in ("waiting", "next_action", "status"):
        if key in c:
            s[key] = c[key]
    moved = c.get("artifacts_moved") or {}
    if moved:  # 2.26.0: {"<old path>": {"path", "sha256"}}, the whole mapping at once on the list before the move (order-free)
        moves_problem({old: new["path"] for old, new in moved.items()}, [x["path"] for x in s["artifacts"]])
        s["artifacts"] = [dict(moved[x["path"]], event=eid) if x["path"] in moved else x for x in s["artifacts"]]
    gone = {g["path"] for g in c.get("artifacts_gone") or []}
    if gone:  # 2.27.0 (U12 B′): files the user confirmed deleted leave the list, so missing checks and verify skip them
        absent = sorted(gone - {x["path"] for x in s["artifacts"]})
        if absent:
            raise Reject(f"artifacts_gone: 산출물 목록에 없는 경로입니다: {absent}")
        s["artifacts"] = [x for x in s["artifacts"] if x["path"] not in gone]
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
    is_map = lambda d: str(d["text"]).lstrip().startswith("Map:")  # 2.23.0: "무엇을 먼저 보라"는 안내 결정. 범위가 아니므로 현재 범위 줄에서는 뺀다
    scope = [d for d in s["decisions"] if not is_map(d)]
    if scope:
        last = scope[-1]
        out.append(f"현재 범위(최신 결정): {last['id']}: {last['text']}")
    out += ["※ 최초 목표의 값이 이후에 바뀌었다면 아래 '유효 결정'이 우선한다. replaces로 기록된 변경은 충돌이 아니다.",
            f"상태: {s['status']}", ""]
    line = lambda d: f"- {d['id']}: {d['text']}" + (f" (대체: {d['replaces']})" if d.get("replaces") else "") + tag(d)
    maps = [d for d in s["decisions"] if is_map(d)]
    if maps:  # 2.23.0: Map 결정은 결정 목록 위에도 따로 보인다. 목록에서 빼지 않으며, 없으면 절도 없다(기존 state.md와 바이트 동일)
        out += ["## 안내 — 먼저 볼 것(Map: 결정)"] + [line(d) for d in maps] + [""]
    out += ["## 유효 결정 — [사용자]는 사용자 발언, [모델]은 모델 판단"]
    out += [line(d) for d in s["decisions"]] or ["- (없음)"]
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
                        "waiting", "next_action", "status", "artifacts", "artifacts_moved", "artifacts_gone", "check", "refs", "takeover",
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
    moved_in = p.get("artifacts_moved")
    if moved_in is not None and (not isinstance(moved_in, dict) or not all(isinstance(k, str) and k and isinstance(v, str) and v
                                                                           for k, v in moved_in.items())):
        raise Reject('artifacts_moved는 {"옛 경로": "새 경로"}처럼 문자열 값을 가진 객체여야 합니다.')
    gone_in = p.get("artifacts_gone")
    if gone_in is not None and (not isinstance(gone_in, list) or any(not isinstance(g, dict) or set(g) - {"path", "reason"}
                                                                    or not isinstance(g.get("path"), str) or not g["path"]
                                                                    or not isinstance(g.get("reason", ""), str) for g in gone_in)):
        raise Reject('artifacts_gone은 [{"path": "기록된 경로", "reason": "지운 이유 한 구절"}] 형식이어야 합니다.')
    empty = [g["path"] for g in gone_in or [] if not str(g.get("reason") or "").strip()]
    if empty:
        raise Reject(f"artifacts_gone: reason이 비어 있습니다: {empty}. 사용자가 지웠다고 확인한 내용을 한 구절로 적으세요.")
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


def moves_problem(mapping, paths):
    """Reject an artifacts_moved mapping {old: new} that cannot be applied at once to the recorded paths: an old path that is
    not recorded, a new path equal to its old one, two moves to one path, a new path that is a recorded artifact which is not
    moved itself (it would be dropped), or a cycle (a→b, b→a: a swap is two moves through a third name, not one save)."""
    have = set(paths)
    for old, new in mapping.items():
        if old not in have:
            raise Reject(f"artifacts_moved: 산출물 목록에 없는 경로입니다: {old}. 현재: {sorted(have)}")
        if old == new:
            raise Reject(f"artifacts_moved: 옛 경로와 새 경로가 같습니다: {old}")
    targets = list(mapping.values())
    dup = sorted({t for t in targets if targets.count(t) > 1})
    if dup:
        raise Reject(f"artifacts_moved: 새 경로가 겹칩니다: {dup}")
    kept = sorted(t for t in targets if t in have and t not in mapping)
    if kept:
        raise Reject(f"artifacts_moved: 새 경로가 옮기지 않는 기존 산출물과 같습니다: {kept}")
    for start in mapping:
        cur, seen = start, set()
        while cur in mapping and cur not in seen:
            seen.add(cur)
            cur = mapping[cur]
        if cur == start:
            raise Reject(f"artifacts_moved: 이동이 순환합니다({start}에서 시작). 맞바꾸기는 한 save에 넣지 않는다.")


def moved_artifacts(p, root, state):
    """save input artifacts_moved {"old": "new"} → changes.artifacts_moved {"old": {"path": new, "sha256": hash of the new file}}
    (2.26.0). The old path must be a recorded artifact and the new file must exist; no check quote is asked for a move."""
    mapping, out = p.get("artifacts_moved") or {}, {}
    moves_problem(mapping, [x["path"] for x in state["artifacts"]])
    for old, new in mapping.items():
        path = (Path(root) / new).resolve()
        if not path.is_file():
            raise Reject(f"artifacts_moved: 새 경로의 파일이 없습니다: {new}")
        out[old] = {"path": new, "sha256": sha(path.read_bytes())}
    return out


def gone_artifacts(p, state):
    """save input artifacts_gone [{"path", "reason"}] → changes.artifacts_gone (2.27.0, U12 B′): recorded files the user confirmed
    deleted for good. The path must be a recorded artifact and appear once; a path this save also records or moves is refused.
    The file may still be on disk (the user's word is the evidence)."""
    gone = [{"path": g["path"], "reason": g["reason"].strip()} for g in p.get("artifacts_gone") or []]
    have = [x["path"] for x in state["artifacts"]]
    for g in gone:
        if g["path"] not in have:
            raise Reject(f"artifacts_gone: 산출물 목록에 없는 경로입니다: {g['path']}. 현재: {sorted(have)}")
    paths = [g["path"] for g in gone]
    dup = sorted({x for x in paths if paths.count(x) > 1})
    if dup:
        raise Reject(f"artifacts_gone: 같은 경로가 두 번 있습니다: {dup}")
    moved = p.get("artifacts_moved") or {}
    both = sorted(set(paths) & (set(moved) | set(moved.values()) | {a["path"] for a in p.get("artifacts", [])}))
    if both:
        raise Reject(f"artifacts_gone: 같은 save의 artifacts·artifacts_moved에도 있는 경로입니다: {both}")
    return gone


def gone_list(events, state):
    """verify (2.27.0): ["path(Eid)"] of artifacts recorded as gone (Eid = the event that recorded it), except a path recorded
    again afterwards."""
    live, out = {a["path"] for a in state["artifacts"]}, {}
    for ev in events:
        for g in (ev.get("changes") or {}).get("artifacts_gone") or []:
            out[g["path"]] = f"{g['path']}({ev['id']})"
    return [v for path, v in out.items() if path not in live]


def drop_repeats(changes, state):
    """save (2.26.1, from cmd_save): strip source tags from changes["constraints"]/["decisions"] (F6: the core adds them), refuse
    an empty text, and drop items whose text the state already has (or an earlier item of this save has; a decision with
    replaces is kept). Changes `changes` (and its decision items) in place and returns the dropped items. No disk, no lock."""
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
    return ignored


def check_quotes(p, arts, bodies, state):
    """save (2.26.1, from cmd_save): match p["check"] against the artifacts. state = the state after this save; arts/bodies from
    validate(). Text artifacts: every valid decision·constraint needs a quote from a body or "미반영: <이유>"; non-text only:
    check is optional and takes only 미반영. Returns (need: the checked ids, unreflected, self_quoted) or raises Reject (same
    texts and order as before). No disk, no lock."""
    unreflected, self_quoted = [], []
    rules = state["decisions"] + state["constraints"]
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
    return need, unreflected, self_quoted


def cmd_save(args):
    root = Path(args.root).resolve()
    tool, sid, how = identity_how(args)
    raw = sys.stdin.read()
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Reject(f"JSON 해석 실패: {e}. `wl.py help` 참고.")
    d = store(root)
    if not connected(d):
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
            raise Reject(f"show 먼저 실행하세요(작업 {wid}). 이 세션은 아직 이 작업의 현재 기록을 읽지 않았습니다." + call_note(tool, sid, how))
        if seen is not None and seen < len(events):
            raise Reject(f"기록이 바뀌었습니다(seq {seen}→{len(events)}). show 후 다시 저장하세요." + call_note(tool, sid, how))
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
        ignored = drop_repeats(changes, state)
        if arts:
            changes["artifacts"] = arts
        moved = moved_artifacts(p, root, state)
        if moved:
            changes["artifacts_moved"] = moved
        gone = gone_artifacts(p, state)
        if gone:
            changes["artifacts_gone"] = gone
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
        need, unreflected, self_quoted = check_quotes(p, arts, bodies, new_state)
        check = p.get("check") or {}
        if need:
            ev["check"] = {i: check[i] for i in need}
        if self_quoted:
            ev["self_quoted"] = self_quoted
        rebuilt = commit(d, index, wid, ev)
        write_atomic(wpath, json.dumps({"tool": tool, "session_id": sid, "seq": ev["seq"]}) + "\n")
        update_session(d, tool, sid, seen=(wid, ev["seq"]), saved_turn=(sess or {}).get("turn", 0))
        missing = note_once(d, (tool, sid), own_missing_artifacts(d, events + [ev], rebuilt, (tool, sid)))
    print(json.dumps({"ok": True, "work": wid, "saved": ev["id"], "seq": ev["seq"], "verified": True, "unreflected": unreflected,
                      "self_quoted": self_quoted, **({"artifacts_missing": missing} if missing else {}),
                      "ignored_duplicates": [x if isinstance(x, str) else x["text"] for x in ignored],
                      "decisions": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["decisions"]],
                      "constraints": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["constraints"]],
                      "waiting": rebuilt["waiting"], "next_action": rebuilt["next_action"], **off_flag(d),
                      **core_report(events), **hooks_report(d, tool, sid)}, ensure_ascii=False))


def cmd_skip(args):
    """Read-only turn: skipped_turn = turn. Writes nothing to the ledger."""
    if not str(args.arg or "").strip():
        raise Reject('skip에는 이유가 필요합니다: wl.py skip "읽기 전용: 질문에 답만 함"')
    d = store(args.root)
    tool, sid = identity(args)
    if not connected(d):
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
                missing = note_once(d, (tool, sid), own_missing_artifacts(d, evs, fold(evs)[0], (tool, sid)))
            except (Reject, OSError, ValueError):
                pass
    print(json.dumps({"ok": True, "turn": turn, **({"artifacts_missing": missing} if missing else {}), **off_flag(d),
                      **hooks_report(d, tool, sid)}, ensure_ascii=False))


# --- 작업 선택 ---

def need_quote(args, usage, said="작업을 지정한"):
    if not str(args.quote or "").strip():
        raise Reject(f"사용자 원문이 필요합니다: {usage}. 사용자가 {said} 말을 그대로 --quote에 넣으세요.")


def cmd_version(args):
    """설치 확인용: 코어 버전과 원장 형식. .worklog 없이도 동작한다."""
    print(json.dumps({"version": VERSION, "format": FORMAT}))


def cmd_works(args):
    d = store(args.root)
    index = (load_index(d) if connected(d) else None) or {"works": {}}
    who, current = try_identity(args), None
    if who and connected(d):
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
    if not connected(d):
        raise Reject(not_connected_text(args, d, "use"))
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


def new_work_refusal(sess, index, force):
    """Inside locked(d): refuse a second new work of one session in one turn (new-work, and reassign --new since 2.27.0).
    It is usually a retry after an unclear result, and would make "<id>-2" (2.25.0). 2.26.0: turn 0 too (the first connection
    turn is the one that matters most), and the marker new_work_turn/new_work_id is written before index.json: a retry after a
    failed index write is let through (the id is not in the index), a retry after a failed session write is refused (the work exists)."""
    made = sess["new_work_id"]
    if sess["new_work_turn"] == sess["turn"] and (made is None or made in index["works"]) and not force:
        made = made or sess["current_work"]
        raise Reject(f"이 세션은 이번 턴에 이미 new-work로 작업 {made}를 만들었습니다. 재시도라면 works로 확인하고 그 작업을 그대로 쓰세요"
                     f"(현재 작업이 {made}가 아니면 use {made} --quote). 정말 하나 더 만들려면 --force를 붙이세요.")


def create_work(d, index, who, sess, title, **session_changes):
    """Inside locked(d): a new index entry and an empty work folder (no event: the first save or reassign writes the ledger).
    The session's retry marker (new_work_turn, new_work_id, plus session_changes) is written before index.json. Returns the id.
    Shared by new-work and reassign --new (2.27.0)."""
    made = sess["new_work_id"]
    works = works_root(d)
    taken = set(index["works"]) | ({p.name for p in works.iterdir()} if works.is_dir() else set())
    if made and made not in index["works"] and (works / made).is_dir() and not any((works / made).iterdir()):
        taken.discard(made)  # the empty folder an earlier attempt of this turn made before its index write failed: reuse the id
    wid = make_id(title, taken)
    update_session(d, *who, new_work_turn=sess["turn"], new_work_id=wid, **session_changes)
    at = now()
    index["works"][wid] = {"title": title, "status": "ACTIVE", "created_at": at, "updated_at": at, "last_seq": 0}
    work_dir(d, wid).mkdir(parents=True, exist_ok=True)
    write_index(d, index)
    return wid


def others_notice(others):
    """new-work's (and reassign --new's) notice part: the other works' constraints do not apply to the new one."""
    return ("다른 작업의 유효 제약은 이 작업에 적용되지 않습니다: " + ", ".join(others)
            + ". 이어받을 결정·제약은 이 작업을 맡긴 프롬프트에 적힌 것만 다시 저장하세요. 프롬프트에 없으면 사용자에게 확인하세요.")


def cmd_new_work(args):
    title = NEW_WORK_PREFIX.sub("", str(args.arg or "")).strip()  # "새 작업: 제목"을 그대로 넣어도 제목만 남긴다
    if not title:
        raise Reject('new-work "<제목>" --quote "<사용자 원문>" 형식입니다.')
    tool, sid = identity(args)
    need_quote(args, f'new-work "{title}" --quote "<사용자 원문>"')
    d = store(args.root)
    fresh = not connected(d)  # 2.21.0: 폴더를 처음 만드는 new-work가 이 프로젝트를 연결한다
    d.mkdir(exist_ok=True)
    with locked(d):
        sess = session_or_new(d, tool, sid)
        index = index_or_new(d)
        new_work_refusal(sess, index, getattr(args, "force", False))
        # fresh: the hooks of this session ran while the folder was not connected and could not leave a record, so the
        # "Hook 미작동 의심" warning would be wrong here; "connect" in hooks_seen stands for them until a hook records itself.
        wid = create_work(d, index, (tool, sid), sess, title, **({"hooks_seen": {"connect": now()}} if fresh else {}))
        update_session(d, tool, sid, current_work=wid, selected_turn=sess["turn"])
        others = other_constraints(d, index, wid)
    result = {"ok": True, "id": wid, "title": title, "current_work": wid}
    if fresh:
        changed, notes = connect(d.parent, tool)
        result.update(connected=True, connected_changed=changed, connected_notes=notes)
    notices = []
    if others:
        notices.append(others_notice(others))
    above = next((p for p in d.parent.parents if (p / ".worklog" / "index.json").is_file()), None)  # works there, not ~/.worklog (WL_HOME) or an empty connection
    if above:  # 상위 폴더에 이미 기록이 있으면 하위에 따로 기록하는 것이 맞는지 확인한다(기록이 갈라진다)
        notices.append(f"상위 폴더 {above}에 Worklog가 있습니다. 이 하위 폴더에 따로 기록하려는 것이 맞는지 사용자에게 확인하세요.")
    report = hooks_report(d, tool, sid)
    report.pop("notice", None)  # 2.26.0: new-work's notice means "constraints of other works do not apply" (the rules ask the user
    # then); the first-connection notice goes with the turn's save·skip results only, hooks stay null here
    if notices:
        result["notice"] = " ".join(notices)
    print(json.dumps({**result, **off_flag(d), **report}, ensure_ascii=False))


def set_status(args, status, summary):
    """archive/reopen: CHECKPOINT event with the status change + index status. No quote needed."""
    wid = args.arg
    tool, sid = identity(args)
    d = store(args.root)
    if not connected(d):
        raise Reject(f"없는 작업입니다: {wid}. 작업 목록: (없음)")
    with locked(d):
        index = index_or_new(d)
        if entry(index, wid)["status"] == status:
            raise Reject(f"작업 {wid}는 이미 {status}입니다.")
        events, prev = read_events(work_dir(d, wid))
        ev = new_event(events, prev, "CHECKPOINT", tool, sid, summary, None, [], {"status": status})
        commit(d, index, wid, ev)
        mark_seen_if_current(d, tool, sid, wid, len(events), ev["seq"])  # 최신을 보던 세션은 자기 사건 뒤도 최신
    print(json.dumps({"ok": True, "work": wid, "status": status, "saved": ev["id"], "seq": ev["seq"]}, ensure_ascii=False))


def cmd_archive(args):
    set_status(args, "COMPLETED", "작업 보관")


def cmd_reopen(args):
    set_status(args, "ACTIVE", "작업 재개")


# --- 잘못 고른 작업의 정정 (2.25.0). 원장은 작업별 추가 전용: 사건을 옮기지 않고 양쪽에 서로를 가리키는 CORRECTION을 남긴다 ---
# 바깥 의존 함수(27, 2.27.0): commit connected create_work entry fold identity index_or_new locked mark_seen_if_current need_quote new_event new_work_refusal norm not_connected_text other_constraints others_notice project projection_ok read_events session_or_new sha store tag title_slug update_session work_dir write_index (+ 상수 NEW_WORK_PREFIX·REASSIGNED_MAX, Reject)
# 이 구역은 `import wl`·형제 파일 분리를 전제하지 않는다(분리는 보류, 2026-10-22 결정). 위 목록은 경계 표시이며 옮길 때의 비용 기준이다.

EVENT_ID = re.compile(r"E(\d{1,6})")


def event_ids(spec, events):
    """"E0003-E0005", "E0003,E0005" or "E0003" → those ids of this work, in ledger order (each must exist)."""
    have, out = {e["id"] for e in events}, []
    for part in str(spec or "").replace(" ", "").split(","):
        lo, _, hi = part.partition("-")
        a, b = EVENT_ID.fullmatch(lo), EVENT_ID.fullmatch(hi or lo)
        if not (a and b) or int(a.group(1)) > int(b.group(1)):
            raise Reject(f"--events 형식: E0003-E0005 또는 E0003,E0007 (받은 값: {spec!r})")
        out += [f"E{n:04d}" for n in range(int(a.group(1)), int(b.group(1)) + 1)]
    missing = [i for i in out if i not in have]
    if missing:
        raise Reject(f"작업에 없는 사건: {missing}. show의 사건 목록에서 범위를 고르세요.")
    return sorted(set(out))


def ref_ids(e, kind, work=None):
    """The ids of event e's refs of this kind; a ref that names a work must name `work` (misfiled refs name none)."""
    return {r.get("id") for r in e.get("refs") or [] if isinstance(r, dict) and r.get("kind") == kind and r.get("work", work) == work}


REASSIGN_STEPS = ("refiled", "refiled_state", "misfiled", "misfiled_state", "session")


def reassign_progress(d, wrong, right, ids, who):
    """Inside locked(d), 2.26.0: which steps of `reassign wrong right --events ids` are on disk, read fresh. refiled = the right
    work's CORRECTION whose refiled_from refs are exactly these events; refiled_state = that work's state.json·state.md and index
    entry match its ledger; misfiled = the wrong work's CORRECTION with exactly these misfiled refs and a refiled_to the right work;
    misfiled_state = the same for the wrong work; session = this session's current work is the right work and it has seen the
    refiled event, or (reassigned mark) this session's session step was done and the user selected a work at that turn or later.
    misfiled also needs its refiled_to (or a later `[misfiled → right] 대상 정정` event's) to name the refiled event: a 2.25.0
    partial run predicted that id (F05). Also returns the events and the link a's marks give now."""
    index = index_or_new(d)
    (wevents, wprev), (revents, rprev) = read_events(work_dir(d, wrong)), read_events(work_dir(d, right))
    ev_b = next((e for e in revents if e.get("type") == "CORRECTION" and sorted(ref_ids(e, "refiled_from", wrong)) == ids), None)
    ev_a = next((e for e in wevents if e.get("type") == "CORRECTION" and sorted(ref_ids(e, "misfiled")) == ids
                 and ref_ids(e, "refiled_to", right)), None)
    link = None
    if ev_a:  # the latest correction of ev_a's target wins (2.26.0 F05), else ev_a's own refiled_to
        fixes = [e for e in wevents if ev_a["id"] in ref_ids(e, "corrects") and ref_ids(e, "refiled_to", right)]
        link = next(iter(ref_ids(fixes[-1] if fixes else ev_a, "refiled_to", right)), None)
    s = session_or_new(d, *who)
    turns = [t for m, _, t in (x.rpartition("@") for x in s["reassigned"]) if ev_b and m == f"{right}:{ev_b['id']}" and t.isdigit()]
    moved_on = bool(turns) and s["selected_turn"] >= int(turns[-1])

    def state_ok(wid, events):
        w, st = index["works"][wid], fold(events)[0]
        return all(projection_ok(work_dir(d, wid), st, wid, w["title"], events)) and (w["last_seq"], w["status"]) == (len(events), st["status"])
    steps = {"refiled": bool(ev_b), "refiled_state": bool(ev_b) and state_ok(right, revents),
             "misfiled": bool(ev_a and ev_b) and link == ev_b["id"], "misfiled_state": bool(ev_a) and state_ok(wrong, wevents),
             "session": bool(ev_b) and ((s["current_work"] == right and s["last_seen"].get(right, 0) >= ev_b["seq"]) or moved_on)}
    return {"steps": steps, "index": index, "refiled": ev_b, "misfiled": ev_a, "wrong": (wevents, wprev), "right": (revents, rprev)}


def repair_state(d, index, wid):
    """Inside locked(d): rebuild one work's projection and index entry from its ledger (reassign recovery, 2.26.0)."""
    events, _ = read_events(work_dir(d, wid))
    st = fold(events)[0]
    project(work_dir(d, wid), st, wid, index["works"][wid]["title"])
    index["works"][wid].update(last_seq=len(events), status=st["status"], **({"updated_at": events[-1]["at"]} if events else {}))
    write_index(d, index)


UPGRADE_WHY = "출처 승격: 같은 글자의 사용자 항목을 옮겨 옴(reassign)"


def refile_changes(rstate, decs, cons):
    """F07 (2.26.0): what the right work gets for the wrong work's decisions and constraints, judged by text and source. Not there
    → added with its source. Same text and source, or an incoming model item over an existing user one → skipped (already_there).
    An incoming user item over an existing model one → that model item is removed (decisions_remove / constraints_remove) and the
    text added again as user (upgraded), so the fold says user. Returns (changes, already_there, upgraded)."""
    changes, already, upgraded = {}, [], []
    for key, items, remove_key in (("decisions", decs, "decisions_remove"), ("constraints", cons, "constraints_remove")):
        have, add, remove, merged = {}, [], {}, {}
        for x in rstate[key]:
            have.setdefault(norm(x["text"]), x)
        for x in items:  # 2.26.0 (F07): one item per text in the selection, a user one over a model one whatever the order
            k = norm(x["text"])
            if k not in merged or (x.get("source") == "user" and merged[k].get("source") != "user"):
                merged[k] = x
        for x in merged.values():
            item = dict(text=x["text"], **({"source": x["source"]} if x.get("source") else {}))
            old = have.get(norm(x["text"]))
            if old is not None and not (x.get("source") == "user" and old.get("source") == "model" and old.get("id")):
                already.append(x["text"])
                continue
            if old is not None:
                remove[old["id"]] = UPGRADE_WHY
                upgraded.append(x["text"])
            add.append(item)
        if remove:
            changes[remove_key] = remove
        if add:
            changes[key] = add
    return changes, already, upgraded


def new_target_resume(d, index, title, wrong, ids):
    """reassign --new re-run (2.27.0): the work an earlier run of the same command created — an index work other than `wrong`
    with this title whose ledger is empty or holds only CORRECTIONs refiled from `wrong` with exactly these events. None if none."""
    for wid, w in sorted(index["works"].items()):
        if wid != wrong and w["title"] == title and all(
                e.get("type") == "CORRECTION" and sorted(ref_ids(e, "refiled_from", wrong)) == ids for e in read_events(work_dir(d, wid))[0]):
            return wid
    return None


def cmd_reassign(args):
    """reassign <wrong> <right> --events E0003-E0005 --quote (2.26.0 order): ⒜ CORRECTION in the right work that records the
    decisions and constraints those events added (new D/C ids, their source kept or upgraded, artifacts rehashed, original quotes
    in refs, refs point only at the wrong work's existing events), ⒝ CORRECTION in the wrong work that removes them, its refiled_to
    naming the id ⒜ really got, ⒞ the right work becomes this session's current work. One .lock. A failure anywhere is reported as
    partial with the steps that are done; the same command run again finds the steps on disk and does only the missing ones.
    2.27.0 (U15): `--new "<title>"` in place of <right> first creates the right work like new-work (same id rule, same same-turn
    refusal and marker, same notice; ⒜ carries goal = title) inside the same lock; a re-run finds that work by its title."""
    wrong, right = args.arg, getattr(args, "arg2", None)
    new = getattr(args, "new", None)
    title = NEW_WORK_PREFIX.sub("", str(new or "")).strip() if new is not None else None
    usage = 'reassign <잘못된 id> <맞는 id> --events E0003-E0005 --quote "<사용자 원문>"(맞는 작업이 아직 없으면 <맞는 id> 대신 --new "<제목>")'
    if new is not None and right:
        raise Reject(f"<맞는 id>({right})와 --new를 함께 쓸 수 없습니다. {usage}")
    if new is not None and not title:
        raise Reject(f"--new의 제목이 비어 있습니다. {usage}")
    if not (wrong and (right or title) and getattr(args, "events", None)):
        raise Reject(f"{usage} 형식입니다.")
    if wrong == right:
        raise Reject("잘못된 작업과 맞는 작업이 같습니다.")
    tool, sid = identity(args)
    need_quote(args, usage, said="잘못 골랐다고 한")
    d = store(args.root)
    if not connected(d):
        raise Reject(not_connected_text(args, d, "reassign"))
    who, result, failed, after, created = (tool, sid), None, None, None, None
    with locked(d):
        index = index_or_new(d)
        entry(index, wrong)
        wevents, _ = read_events(work_dir(d, wrong))
        ids = event_ids(args.events, wevents)
        if title:  # --new (2.27.0): an earlier run's work, else checks now and creation after the double-refile checks below
            right = new_target_resume(d, index, title, wrong, ids)
            if not right:
                slug = title_slug(title)
                if slug and not slug.replace("-", "").isdigit() and slug in index["works"]:
                    raise Reject(f"--new 제목의 작업 id {slug}가 이미 있습니다(제목: {index['works'][slug]['title']}). 그 작업으로 옮기려면 "
                                 f"reassign {wrong} {slug} --events {args.events} --quote \"<원문>\", 새 작업이 맞으면 다른 제목을 쓰세요.")
                sess = session_or_new(d, tool, sid)
                new_work_refusal(sess, index, getattr(args, "force", False))
        else:
            entry(index, right)
        span = ids[0] if len(ids) == 1 else (f"{ids[0]}-{ids[-1]}" if len(ids) == int(ids[-1][1:]) - int(ids[0][1:]) + 1 else ", ".join(ids))
        sel = set(ids)
        # An event already refiled to another work is not refiled again (its rules left this work then). 2.26.0: judged from
        # every work's refiled_from refs (written first), and from the wrong work's own misfiled marks (2.25.0 ledgers).
        for other in sorted(set(index["works"]) - {wrong, right}):
            try:
                oevents = read_events(work_dir(d, other))[0]
            except Reject as e:  # 2.26.0 (N02): a ledger that cannot be read is not an empty history
                raise Reject(f"작업 {other}의 원장을 읽을 수 없어 이미 옮긴 사건인지 확인할 수 없습니다({e}). 아무것도 쓰지 않았습니다. "
                             "고치지 말고 사용자에게 보고하세요.")
            for e in oevents:
                hit = ref_ids(e, "refiled_from", wrong) & sel if e.get("type") == "CORRECTION" else set()
                if hit:
                    raise Reject(f"이미 {other}로 옮긴 사건입니다: {', '.join(sorted(hit))}({other} {e['id']}). show --work {other}로 확인하세요.")
        for e in wevents:
            hit = ref_ids(e, "misfiled") & sel if e.get("type") == "CORRECTION" else set()
            other = next((r.get("work") for r in e.get("refs") or [] if isinstance(r, dict) and r.get("kind") == "refiled_to"
                          and r.get("work") != right), None)
            if hit and other:
                raise Reject(f"이미 {other}로 옮긴 사건입니다: {', '.join(sorted(hit))}({wrong} {e['id']}). show --work {other}로 확인하세요.")
        if title and not right:
            right = created = create_work(d, index, who, sess, title)
        pr = reassign_progress(d, wrong, right, ids, who)
        steps, index, ev_b, ev_a = pr["steps"], pr["index"], pr["refiled"], pr["misfiled"]
        (wevents, wprev), (revents, rprev) = pr["wrong"], pr["right"]
        if all(steps.values()):
            raise Reject(f"이미 옮겼습니다: {wrong} {ev_a['id']} ↔ {right} {ev_b['id']}. show --work {right}로 확인하세요.")
        before, _ = fold(wevents[:ev_a["seq"] - 1] if ev_a else wevents)  # what those events had put in the wrong work
        decs = [x for x in before["decisions"] if x["event"] in sel]
        cons = [x for x in before["constraints"] if x["event"] in sel]
        arts = [x for x in before["artifacts"] if x["event"] in sel]
        corrected = None
        try:
            if not ev_b:  # ⒜ the right work first
                changes = refile_changes(fold(revents)[0], decs, cons)[0]
                if title and not revents:  # --new: the new work's first event sets its goal like a first save would
                    changes["goal"] = title
                new_a = [{"path": a["path"], "sha256": sha((d.parent / a["path"]).read_bytes())} for a in arts if (d.parent / a["path"]).is_file()]
                if new_a:
                    changes["artifacts"] = new_a
                by_id = {e["id"]: e for e in wevents}
                refs = [dict({"kind": "refiled_from", "work": wrong, "id": i}, **({"quote": by_id[i]["quote"]} if isinstance(by_id[i].get("quote"), str) else {}))
                        for i in ids] + ([{"kind": "correction", "work": wrong, "id": ev_a["id"]}] if ev_a else [])  # ev_a: a 2.25.0 partial run
                ev_b = new_event(revents, rprev, "CORRECTION", tool, sid, f"[refiled ← {wrong}] {span}", args.quote, refs, changes)
                commit(d, index, right, ev_b)
            elif not steps["refiled_state"]:
                repair_state(d, index, right)
            if not ev_a:  # ⒝ the wrong work, pointing at the id ⒜ really got
                why = f"{right}로 옮김(reassign)"
                changes = {k: v for k, v in (("decisions_remove", {x["id"]: why for x in decs}),
                                             ("constraints_remove", {x["id"]: why for x in cons})) if v}
                refs = [{"kind": "misfiled", "id": i} for i in ids] + [{"kind": "refiled_to", "work": right, "id": ev_b["id"]}]
                ev_a = new_event(wevents, wprev, "CORRECTION", tool, sid, f"[misfiled → {right}] {span}", args.quote, refs, changes)
                commit(d, index, wrong, ev_a)
                mark_seen_if_current(d, tool, sid, wrong, len(wevents), ev_a["seq"])
            elif not reassign_progress(d, wrong, right, ids, who)["steps"]["misfiled"]:
                # F05: a 2.25.0 partial run's mark names a predicted id that is not the refiled event. The ledger stays as it is;
                # one more CORRECTION in the wrong work names the real one (refs: corrects + refiled_to, no state change)
                wevents, wprev = read_events(work_dir(d, wrong))
                refs = [{"kind": "corrects", "id": ev_a["id"]}, {"kind": "refiled_to", "work": right, "id": ev_b["id"]}]
                corrected = new_event(wevents, wprev, "CORRECTION", tool, sid, f"[misfiled → {right}] 대상 정정 {ev_a['id']}", args.quote, refs, {})
                commit(d, index, wrong, corrected)
                mark_seen_if_current(d, tool, sid, wrong, len(wevents), corrected["seq"])
            elif not steps["misfiled_state"]:
                repair_state(d, index, wrong)
            if not steps["session"]:  # ⒞
                s = session_or_new(d, tool, sid)
                update_session(d, tool, sid, seen=(right, max(s["last_seen"].get(right, 0), ev_b["seq"])), current_work=right,
                               selected_turn=s["turn"], reassigned=(s["reassigned"] + [f"{right}:{ev_b['id']}@{s['turn']}"])[-REASSIGNED_MAX:])
        except (Reject, OSError, ValueError) as e:
            failed = f"{type(e).__name__}: {e}" if not isinstance(e, Reject) else str(e)
            try:
                after = reassign_progress(d, wrong, right, ids, who)
            except (Reject, OSError, ValueError):
                after = None
        else:
            revents = read_events(work_dir(d, right))[0]
            _, already, upgraded = refile_changes(fold(revents[:ev_b["seq"] - 1])[0], decs, cons)
            moved_paths = [a["path"] for a in (ev_b.get("changes") or {}).get("artifacts", [])]
            gone = [a["path"] for a in arts if a["path"] not in moved_paths]
            rebuilt = fold(revents)[0]
            resumed = [k for k in REASSIGN_STEPS if steps[k]]
            result = {"ok": True, "from": wrong, "to": right, "events": ids, "misfiled": ev_a["id"], "refiled": ev_b["id"],
                      "moved": {"decisions": [x["id"] for x in decs], "constraints": [x["id"] for x in cons], "artifacts": moved_paths},
                      **({"artifacts_missing": gone} if gone else {}),
                      **({"already_there": already} if already else {}),  # same text already active in the right work: not added twice
                      **({"upgraded": upgraded} if upgraded else {}),     # 2.26.0: a model item there became the user item moved here
                      **({"resumed": resumed} if resumed else {}),        # 2.26.0: steps an earlier run had done (this run did the rest)
                      **({"corrected_ref": True, "ref_correction": corrected["id"]} if corrected else {}),  # 2.26.0 (F05)
                      **({"created": created} if created else {}),  # 2.27.0: --new made this work in this run
                      "current_work": right,
                      "decisions": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["decisions"]],
                      "constraints": [f"{x['id']}: {x['text']}{tag(x)}" for x in rebuilt["constraints"]]}
            others = other_constraints(d, index, right) if title else []
            if others:  # 2.27.0: the same notice as new-work
                result["notice"] = others_notice(others)
    if failed:
        done = [k for k in REASSIGN_STEPS if after["steps"][k]] if after else None
        b_id = (after["refiled"] or {}).get("id") if after else None
        a_id = (after["misfiled"] or {}).get("id") if after else None
        print(json.dumps({"ok": False, "partial": True, "done": done, "refiled": b_id, "misfiled": a_id, "error": failed,
                          **({"created": created} if created else {}),
                          "next": "원인을 고친 뒤 같은 reassign 명령을 다시 실행한다(끝난 단계는 건너뛰고 빠진 단계만 한다).",
                          "message": f"reassign이 중간에 멈췄습니다(끝난 단계: {', '.join(done) if done else ('없음' if done is not None else '확인 못함')}). "
                                     "원인을 고친 뒤 같은 reassign 명령을 다시 실행하면 빠진 단계만 합니다."}, ensure_ascii=False))
        sys.exit(2)
    print(json.dumps(result, ensure_ascii=False))


def cmd_rename(args):
    """rename <id> "<new title>" --quote: index title only (the id and the ledger lines stay), plus one CHANGE event."""
    wid, title = args.arg, NEW_WORK_PREFIX.sub("", str(getattr(args, "arg2", None) or "")).strip()
    usage = 'rename <id> "<새 제목>" --quote "<사용자 원문>"'
    if not (wid and title):
        raise Reject(f"{usage} 형식입니다.")
    tool, sid = identity(args)
    need_quote(args, usage, said="제목을 바꾸라고 한")
    d = store(args.root)
    if not connected(d):
        raise Reject(not_connected_text(args, d, "rename"))
    with locked(d):
        index = index_or_new(d)
        w = entry(index, wid)
        old = w["title"]
        if old == title:
            raise Reject(f"작업 {wid}의 제목이 이미 '{title}'입니다.")
        events, prev = read_events(work_dir(d, wid))
        w["title"] = title  # commit writes the index and state.md (its heading shows the title)
        ev = new_event(events, prev, "CHANGE", tool, sid, f"제목 변경: {old} → {title}", args.quote, [], {})
        commit(d, index, wid, ev)
        mark_seen_if_current(d, tool, sid, wid, len(events), ev["seq"])
    print(json.dumps({"ok": True, "work": wid, "title": title, "old_title": old, "saved": ev["id"], "seq": ev["seq"]}, ensure_ascii=False))


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


def not_connected_text(args, d, event):
    """2.26.0: what show prints and use·rename·reassign·on·off refuse with in a folder that is not connected: the plain first
    line, then the hook's NOT_CONNECTED line (same function, `event` in place of SessionStart)."""
    info = root_info(os.getcwd()) if not getattr(args, "root_explicit", False) else None
    if not info or info["root"] != d.parent:
        info = {"root": d.parent, "cwd": d.parent, "git": git_top(d.parent), "outside": None}
    return NOT_CONNECTED_HEAD.format(root=d.parent) + "\n" + not_connected_line(info, False, event).rstrip("\n")


def no_work_guide(index):
    """The "## 현재 작업 없음" text of the SessionStart injection: EMPTY with auto=on → create without asking, else NO_WORK_GUIDE."""
    return EMPTY_GUIDE if not index["works"] and auto_mode() == "on" else NO_WORK_GUIDE


def cmd_show(args):
    d = store(args.root)
    if not connected(d):  # 2.26.0: the hook's NOT_CONNECTED line (root·auto·git and what to do), after the plain first line
        print(not_connected_text(args, d, "show"))
        return
    index = load_index(d)
    if not index or not index["works"]:  # 2.26.0: the SessionStart EMPTY text (auto=on: create without asking; off: wait)
        print(off_note(d) + "Worklog 작업 없음. " + no_work_guide(index or {"works": {}}))
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


def unseen_section(d, who, wid, events):
    """2.23.0: the events this session has not seen yet (after its last_seen seq for this work), as one text block, '' when none or
    the session is unknown. Lets a delegating session tell a sub-session's events apart without reading the ledger file."""
    if not who or not events:
        return ""
    try:
        seen = ((load_session(d, *who) or {}).get("last_seen") or {}).get(wid) or 0
    except SessionCorrupt:
        seen = 0
    unseen = events[seen:]
    if not unseen:
        return ""
    lines = [f"## 이 세션이 아직 못 본 사건 (seq {seen + 1}~{len(events)})"]
    for e in unseen[-UNSEEN_MAX:]:
        summary = norm(e.get("summary") or "")
        lines.append(f"- {e.get('id')} · {e.get('tool')}:{str(e.get('session_id') or '')[:8]} · {e.get('type')} · "
                     + (summary if len(summary) <= 80 else summary[:80] + "…"))
    if len(unseen) > UNSEEN_MAX:
        lines.append(f"- …외 {len(unseen) - UNSEEN_MAX}건(오래된 것부터 생략)")
    return "\n".join(lines) + "\n"


def read_work(d, wid, title, who, **session_changes):
    """Inside locked(d): one work's state text (projection repaired from the ledger if stale) and, when the
    session is known, the events it has not seen yet (2.23.0) and mark it as seen (plus session_changes). Shared by show and use."""
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
    note += artifacts_note(note_once(d, who, own_missing_artifacts(d, events, state, who)))
    unseen = unseen_section(d, who, wid, events)  # 갱신 전에 계산한다
    if who:  # 세션을 모르는 사람의 show는 읽기만 한다
        update_session(d, *who, seen=(wid, len(events)), **session_changes)
    return note + (render(state, wid, title) if events else f"# Worklog 현재 상태 — {wid} · {title}\n기록 없음. 첫 save가 기록을 만든다.\n") + unseen


def check_work(d, wid, title):
    wd = work_dir(d, wid)
    events, _ = read_events(wd)
    state, _ = fold(events)
    ok_json, ok_md = projection_ok(wd, state, wid, title, events)
    arts, gone = artifacts_check(d, state), gone_list(events, state)
    if gone:  # 2.27.0: shown apart from missing, only when there is one (older results unchanged)
        arts["gone"] = gone
    return {"work": wid, "ok": ok_json and ok_md, "events": len(events), "status": state["status"],
            "state_json": ok_json, "state_md": ok_md, "artifacts": arts, **core_report(events)}


def cmd_verify(args):
    d = store(args.root)
    if not connected(d):
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
            for key in ("warning", "warning_install", "warning_worktree", "notice"):
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
    if not connected(d):
        raise Reject(not_connected_text(args, d, getattr(args, "command", "on/off")) + " 켜거나 끌 대상이 없습니다.")
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
    """Hook event from stdin → (store dir, (tool, session) or None, event). args.root is an explicit --root as given, else
    candidate_root of the event's cwd (2.25.0; an event without cwd keeps the process cwd's candidate), args.root_info its
    reasons. Connected = connected(store) (WL_HOME without index.json is not); otherwise store dir is None: SessionStart
    says so in one line and the other two hooks stay silent."""
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = {}
    if not isinstance(event, dict):
        event = {}
    cwd = event.get("cwd")
    if not cwd and isinstance(event.get("workspacePaths"), list) and event["workspacePaths"]:  # agy (Antigravity CLI) hooks.json payload (2.24.0)
        cwd = event["workspacePaths"][0]
    if isinstance(cwd, str) and cwd and not getattr(args, "root_explicit", False):
        args.root_info = root_info(cwd)
    else:  # an explicit --root is used as given (2.25.0, like the other commands); no cwd: the process cwd's candidate
        given = Path(args.root).resolve()
        args.root_info = {"root": given, "cwd": given, "git": git_top(given), "outside": None}
    d = store(args.root_info["root"])
    args.root = str(d.parent)
    if not connected(d):
        return None, None, event
    sid = event.get("session_id") or event.get("conversationId")  # conversationId: agy
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
    cur, unseen, missing = None, "", []
    if who:
        with locked(d):
            cur = current_work(d, who, index)
            if cur:
                events, _ = read_events(work_dir(d, cur))
                unseen = unseen_section(d, who, cur, events)
                missing = note_once(d, who, own_missing_artifacts(d, events, fold(events)[0], who))  # 2.27.0: inside the lock
                update_session(d, *who, seen=(cur, len(events)))
            mark_hook(d, who, "SessionStart")
    if cur:
        title = works[cur]["title"]
        out.append(f"## 현재 작업: {cur} · {title}")
        if events:
            st = fold(events)[0]
            out += [x for x in (artifacts_note(missing).rstrip("\n"),) if x]
            out.append(render(st, cur, title).rstrip("\n"))
            if unseen:
                out.append(unseen.rstrip("\n"))
        else:
            out.append("기록 없음. 첫 save가 기록을 만든다.")
    else:
        out += ["## 현재 작업 없음", no_work_guide(index)]
    return ("EMPTY" if not works else "PROVIDED" if cur else "NO_CURRENT_WORK"), "\n".join(out) + "\n"


def hook_output(tool, text):
    """The SessionStart injection in the tool's own hook output format: Claude Code and Codex (and the pi extension, which
    reads the same shape) take hookSpecificOutput.additionalContext; agy's hooks.json takes injectSteps (2.24.0). HOOK_TOOLS "inject"."""
    if hook_tool(tool)["inject"] == "injectSteps":
        return json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": text}}]}, ensure_ascii=False)
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}, ensure_ascii=False)


def not_connected_line(info, fork, event="SessionStart"):
    """The one NOT_CONNECTED line (2.25.0): root = candidate_root, auto = the user's config, git = whether cwd is in a git
    work tree, then what to do (auto=on: connect on the first request worth recording; auto=off: the 2.24 text). A root
    whose store is WL_HOME (the home folder) gets the auto=off text whatever auto says: it is never connected by itself.
    info = root_info(); event = "SessionStart" for the hook, "show" for the show command (2.26.0, same text)."""
    auto = auto_mode()
    home = is_wl_home(store(info["root"]))
    head = (f"[Worklog {FORMAT} {event} | NOT_CONNECTED | root={info['root']} | auto={auto} | git={'yes' if info['git'] else 'no'}"
            + (" | FORK" if fork else "") + "] ")
    if auto == "off" or home:
        body = ("이 폴더는 Worklog에 연결되지 않았다. 사용자가 \"새 작업: <제목>\"이라 하기 전까지 Worklog 절차(작업 지정 질문·save·skip·show)를 "
                "적용하지 않는다." + (" 홈 폴더는 자동 연결하지 않는다." if home else ""))
    else:
        body = (f"이 폴더는 Worklog에 연결되지 않았다. 첫 기록 대상 요청(사용자가 결과를 원하는 요청. 인사·도구 조작·한 줄 확인은 아님)에서 "
                f"묻지 않고 new-work \"<제목>\" --quote \"<요청 원문>\" --root {shlex.quote(str(info['root']))}로 연결하고 그 턴에 save한다. "
                "그 전에는 Worklog 절차(작업 지정 질문·save·skip·show)를 적용하지 않는다.")
    if info["root"] != info["cwd"]:
        body += f" root는 세션 폴더 {info['cwd']}가 아니라 " + ("가장 가까운 상위 Worklog 기록 폴더다." if has_works(info["root"]) else "git 최상위 폴더다.")
    if info["outside"]:
        body += f" 상위 폴더 {info['outside']}의 Worklog 기록은 git 경계 밖이라 쓰지 않는다(합류는 사용자가 --root로 정한다)."
    return head + body + "\n"


def turn_mark(s):
    """What a turn changes in a session file: the turn counter and the last UserPromptSubmit / Stop times (2.26.0)."""
    return f"{s['turn']}|{s['hooks_seen'].get('UserPromptSubmit', '')}|{s['hooks_seen'].get('Stop', '')}"


def sessionstart_duplicate(d, who, event):
    """Inside locked(d), claude·codex (2.25.0): True when this SessionStart repeats the session's last one (same source within
    SESSIONSTART_DUP seconds: the hook is registered twice, e.g. user + project settings) and no turn happened in between
    (2.26.0: turn counter, UserPromptSubmit and Stop as the first one saw them, key SessionStartTurn — a prompt or a Stop between
    them makes the second a real resume, injected again). Otherwise records this one's keys.
    An event without `source` is never a duplicate (and records nothing)."""
    src = event.get("source")
    if not (isinstance(src, str) and src):
        return False
    s = session_or_new(d, *who)
    last_src, _, at = s["hook_keys"].get("SessionStart", "").rpartition("@")
    try:
        if last_src == src and 0 <= time.time() - float(at) < SESSIONSTART_DUP and s["hook_keys"].get("SessionStartTurn") == turn_mark(s):
            return True
    except ValueError:
        pass
    update_session(d, *who, hook_keys=dict(s["hook_keys"], SessionStart=f"{src}@{time.time():.3f}", SessionStartTurn=turn_mark(s)))
    return False


def agy_sessionstart_repeat(d, who):
    """agy (2.24.2, HOOK_TOOLS marks "agy"): True for a second SessionStart from a duplicate registration before any turn
    (this session already saw a SessionStart and its turn is still 0) → nothing to add. Reads without the lock."""
    try:
        s0 = load_session(d, *who)
    except SessionCorrupt:
        s0 = None
    return bool(s0 and "SessionStart" in s0["hooks_seen"] and s0["turn"] == 0)


def cmd_hook(args):
    """SessionStart hook: prints {"hookSpecificOutput": {..., "additionalContext": ...}} (format: injection(); agy: injectSteps).
    Valid without a session ID; then no session file is touched and there is no current work.
    Not connected (no .worklog/ at candidate_root): one NOT_CONNECTED line, no session file, no update check (2.21.0) —
    without it the rules' "no injection → show" path would make the model ask for a work in every folder once the hooks are
    user-level. source "fork" (2.25.0) adds `| FORK` to the header: a side branch of a conversation (its own session id, so
    its own session file without a current work); the rules keep it from saving until the user names a work."""
    d, who, event = hook_input(args)
    fork = event.get("source") == "fork"
    tool = hook_tool(args.tool)
    if not d:
        print(hook_output(args.tool, not_connected_line(args.root_info, fork)))
        return
    if tool["marks"] == "agy" and who and agy_sessionstart_repeat(d, who):
        print(tool["empty_reply"])
        return
    off = off_marker(d)
    if off is not None:  # 꺼짐: 한 줄만 주입하고 세션 파일은 만들거나 갱신하지 않는다
        line = (f"[Worklog {FORMAT} SessionStart | OFF | root={d.parent}] Worklog가 꺼져 있다(이유: {norm(off.get('reason') or '') or '없음'}, "
                f"시각: {norm(off.get('at') or '') or '알 수 없음'}). 사용자가 켜 달라고 하기 전까지 Worklog 절차를 적용하지 않는다.\n")
        print(hook_output(args.tool, line))
        return
    if who and tool["marks"] == "hook_keys":
        with locked(d):
            if sessionstart_duplicate(d, who, event):
                return  # the first call of the pair already injected
    try:
        status, text = injection(d, who)
    except (Reject, OSError, ValueError) as e:
        text, status = f"Worklog 현재 상태를 읽지 못함: {e}. 파일을 바꾸기 전에 `wl.py show`로 확인한다.\n", "UNAVAILABLE"
    head = f"[Worklog {FORMAT} SessionStart | {status} | root={d.parent}" + (" | FORK" if fork else "") + "]\n이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.\n"
    spawn_update_check()
    head += update_note()
    if who:
        stale = install_report(d, who[0])
        if stale:
            head += f"[Worklog 사본 경고] {stale['warning_install']}\n"
    if (d.parent / ".git").is_file():
        head += f"[Worklog worktree 경고] {WORKTREE_WARNING} 사용자에게 알린다.\n"
    print(hook_output(args.tool, head + text))


def cmd_turn_start(args):
    """UserPromptSubmit hook: turn += 1. No output (agy: `{}`). Does nothing while off.
    agy's PreInvocation fires before every model call, and in auto mode invocationNum restarts after each tool call (2.24.1:
    a turn counted per tool call put save and Stop out of step and looped). So for agy the first PreInvocation after a Stop
    (or SessionStart) starts the turn and the rest of that turn is ignored: session in_turn."""
    d, who, event = hook_input(args)
    tool = hook_tool(args.tool)
    agy = tool["marks"] == "agy"  # agy marks: agy_pre + in_turn; hook_keys: the prompt's own id
    if d and who and not is_off(d):
        with locked(d):
            s = session_or_new(d, *who)
            key = f"{event.get('invocationNum')}/{event.get('initialNumSteps')}" if agy else None
            # claude·codex (2.25.0): the prompt's own id (Codex sends turn_id; prompt_id if a tool sends one). No id → counted as before
            pid = None if agy else next((v for v in (event.get("prompt_id"), event.get("turn_id")) if isinstance(v, str) and v), None)
            if agy and key == s.get("agy_pre"):  # the same PreInvocation delivered again by a second hook registration (2.24.2)
                pass
            elif pid and s["hook_keys"].get("UserPromptSubmit") == pid:  # the same prompt delivered again by a second registration
                pass
            elif not (agy and s.get("in_turn")):
                update_session(d, *who, turn=s["turn"] + 1, in_turn=True, hooks_seen=dict(s["hooks_seen"], UserPromptSubmit=now()),
                               **({"agy_pre": key} if agy else {}), **({"hook_keys": dict(s["hook_keys"], UserPromptSubmit=pid)} if pid else {}))
            elif agy:
                update_session(d, *who, agy_pre=key)
    if tool["empty_reply"] is not None:
        print(tool["empty_reply"])


def cmd_stop_hook(args):
    """Stop hook: block once if this turn has no save, skip or work selection. Does nothing while off.
    When the turn ends (satisfied, or already blocked once: stop_hook_active) the turn counter advances here too, so a next
    turn that starts without UserPromptSubmit (`!` shell input, another session's notification) still needs its own save or skip."""
    d, who, event = hook_input(args)
    tool = hook_tool(args.tool)
    agy = tool["marks"] == "agy"  # agy marks: agy_stop/agy_pre + blocked_turn covers the re-entry turn; hook_keys: Stop key

    def answer(block, reason=None):  # Claude/Codex/pi: block → {"decision": "block"}, else nothing; agy: {"decision": "continue"} or {}
        if block:
            print(json.dumps({"decision": tool["stop_decision"], "reason": reason}, ensure_ascii=False))
        elif tool["empty_reply"] is not None:
            print(tool["empty_reply"])

    if not (d and who) or is_off(d) or event.get("terminationReason") in tool["cancel_reasons"]:
        answer(False)
        return
    try:
        with locked(d):
            s = load_session(d, *who) or new_session()
            if agy and event.get("executionNum") is not None and s.get("agy_stop") == event.get("executionNum"):
                answer(False)  # the same Stop delivered again by a second hook registration (2.24.2): already judged
                return
            if agy:
                s["agy_stop"] = event.get("executionNum")
            active = event.get("stop_hook_active") is True
            last_turn, _, last = s["hook_keys"].get("Stop", "").partition("@")
            try:  # claude·codex (2.25.0): started before the session's previous Stop had finished, at the turn that Stop left, with
                # the same stop_hook_active: the same Stop run by a second registration (they run in parallel). Already judged
                if not agy and last_turn == f"{s['turn']}/{int(active)}" and STARTED < float(last):
                    answer(False)
                    return
            except ValueError:
                pass
            # Blocked once already: stop_hook_active (Claude Code, Codex) or this core's own mark (2.24.0: agy and pi hooks carry no such
            # flag). agy re-enters the loop with a new PreInvocation, which starts turn+1 (2.24.1), so the mark covers that turn too.
            once = event.get("stop_hook_active") is True or s["blocked_turn"] == s["turn"] \
                or (agy and s["blocked_turn"] and s["turn"] - s["blocked_turn"] == 1)
            done = s["turn"] in (s["saved_turn"], s["skipped_turn"], s["selected_turn"]) or once
            after = s["turn"] + 1 if done else s["turn"]
            update_session(d, *who, in_turn=False, hooks_seen=dict(s["hooks_seen"], Stop=now()), **({"agy_stop": s["agy_stop"], "agy_pre": None} if agy else {}),
                           **({"turn": after} if done else {"blocked_turn": s["turn"]}),
                           **({} if agy else {"hook_keys": dict(s["hook_keys"], Stop=f"{after}/{int(active)}@{time.time():.6f}")}))
    except SessionCorrupt as e:
        if event.get("stop_hook_active") is not True:  # 한 번 막힌 뒤에는 다시 막지 않는다(무한 반복 방지)
            answer(True, f"Worklog: 세션 파일을 읽을 수 없습니다({e}). save 또는 skip으로 다시 만든 뒤 마치세요.")
        else:
            answer(False)
        return
    if done:
        answer(False)
        return
    q = shlex.quote
    skip = f'python3 -B {q(str(Path(__file__).resolve()))} skip "이유" --tool {q(who[0])} --session {q(who[1])} --root {q(str(d.parent))}'
    answer(True, "Worklog: 이번 턴에 save가 없습니다. 기록할 것이 있으면 save, "
                 f"읽기 전용 턴이거나 작업이 지정되지 않았으면 `{skip}`를 실행한 뒤 마치세요.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wl.py", description="Worklog 공용 코어 (형식 2)")
    commands = {"works": cmd_works, "use": cmd_use, "new-work": cmd_new_work, "show": cmd_show, "save": cmd_save,
                "skip": cmd_skip, "verify": cmd_verify, "archive": cmd_archive, "reopen": cmd_reopen,
                "reassign": cmd_reassign, "rename": cmd_rename,
                "off": cmd_off, "on": cmd_on, "hook": cmd_hook, "turn-start": cmd_turn_start, "stop-hook": cmd_stop_hook,
                "version": cmd_version, "update": cmd_update}
    ap.add_argument("command", choices=[*commands, "help"])
    ap.add_argument("arg", nargs="?", help="skip의 이유 / use·archive·reopen·rename의 작업 id / reassign의 잘못된 작업 id / new-work의 제목 / update의 check·rollback")
    ap.add_argument("arg2", nargs="?", help="reassign의 맞는 작업 id / rename의 새 제목")
    ap.add_argument("--mode", choices=UPDATE_MODES, help="update: 갱신 알림 방식 설정(notify·off)")
    ap.add_argument("--root")
    ap.add_argument("--tool")
    ap.add_argument("--session")
    ap.add_argument("--quote", help="use·new-work·reassign·rename: 사용자가 작업을 지정하거나 고치라고 한 원문 / off: 사용자가 끄라고 한 원문")
    ap.add_argument("--reason", help="off: 끄는 이유(선택)")
    ap.add_argument("--work", help="show·verify: 대상 작업 id")
    ap.add_argument("--all", action="store_true", help="verify: 모든 작업 + index 일관성")
    ap.add_argument("--events", help="reassign: 옮길 사건 범위(E0003-E0005 또는 E0003,E0007)")
    ap.add_argument("--force", action="store_true", help="new-work·reassign --new: 같은 턴의 두 번째 새 작업 거부를 풀어 하나 더 만든다")
    ap.add_argument("--new", help="reassign: 맞는 작업이 아직 없을 때 <맞는 id> 대신 새 작업 제목(새 작업을 만들며 옮긴다)")
    args = ap.parse_intermixed_args(argv)  # 3.9 argparse도 `skip --tool claude "이유" --root …`처럼 섞인 순서를 받는다
    args.root_explicit = bool(args.root)  # hooks: an explicit --root wins over the event's cwd (2.25.0)
    args.root = args.root or str(candidate_root(os.getcwd()))  # 2.25.0: --root wins; otherwise the git top level / nearest records
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
