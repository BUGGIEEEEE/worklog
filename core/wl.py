#!/usr/bin/env python3
"""Worklog shared core: one save per turn, state rebuilt from an append-only event log.

Commands:  show | save | skip | verify | help | hook | turn-start | stop-hook
Storage:   <root>/.worklog/{events.jsonl, state.json, state.md, writer.json, sessions/<tool>_<session>.json}
Standard library only. Never runs business commands.
"""
import argparse, datetime, fcntl, hashlib, json, os, re, shlex, sys, uuid
from contextlib import contextmanager
from pathlib import Path

FORMAT = "worklog/1"
TYPES = ["REQUEST", "APPROVAL", "D_USER", "D_AGENT", "ASSUMPTION", "RESULT", "VERIFICATION",
         "BLOCKER", "CORRECTION", "CHECKPOINT", "HANDOFF", "CHANGE", "Q",
         "WRITER_ACQUIRED", "WRITER_RELEASED"]
USER_TYPES = {"REQUEST", "APPROVAL", "D_USER"}
REMOVE_TYPES = {"D_USER", "APPROVAL", "CORRECTION"}
STATUSES = ["ACTIVE", "PAUSED", "BLOCKED", "COMPLETED", "CANCELLED"]
TOOL_ENV = [("codex", "CODEX_THREAD_ID"), ("claude", "CLAUDE_CODE_SESSION_ID"), ("pi", "PI_SESSION_ID")]

SAVE_HELP = """save: 턴마다 한 번, stdin으로 JSON 하나를 넣는다.  예) python3 -B wl.py save <<'EOF' ... EOF
{
  "type": "REQUEST",                       # REQUEST APPROVAL D_USER D_AGENT ASSUMPTION RESULT VERIFICATION BLOCKER CORRECTION CHECKPOINT HANDOFF CHANGE Q
  "summary": "이번 턴에 일어난 일 한두 문장",
  "quote": "사용자 원문 일부(그대로)",      # REQUEST/APPROVAL/D_USER, 목표 설정, 제약 해제에 필수
  "goal": "최초 목표",                     # 처음 한 번만, 원문 그대로. 이후 값 변경은 decisions(replaces)로 — 결정이 목표 문장보다 우선
  "decisions": [{"text": "11분으로 변경(이유)", "replaces": "D1"}],   # replaces 생략 가능
  "constraints": ["다른 프로젝트 자료 조회 금지(사용자 변경 전까지)"],  # 계속 지킬 금지·범위만. 해제는 constraints_remove
                                           # "다음 요청까지 작성 보류"처럼 요청이 오면 끝나는 것은 waiting에
  "constraints_remove": {"C2": "해제 근거"},   # 사용자가 바꾼 경우만: type D_USER/APPROVAL/CORRECTION + quote. 같은 제약 재입력은 자동 무시
  "refs": [{"kind": "block", "id": "B03"}],   # 선택. 블록·계획 등 외부 ID(의미 미확정)
  "waiting": ["note-guide.md는 다음 요청까지 작성 보류"],  # 전체 교체. 생략하면 유지, []면 비움
  "next_action": "다음 행동",
  "status": "ACTIVE",                      # ACTIVE PAUSED BLOCKED COMPLETED CANCELLED
  "artifacts": [{"path": "note-guide.md"}],
  "check": {"D1": "'저녁 식사 후 11분'", "C1": "미반영: 알림은 만들지 않았고 본문에 넣을 내용이 아님"}
                                           # artifacts가 있으면 모든 유효 결정·제약 ID 필수. 값은 둘 중 하나:
                                           # ① 산출물 본문에 그대로 있는 문장(4자 이상)을 따옴표로 인용(첫 인용을 본문에서 대조, 공백 무시)
                                           # ② "미반영: <이유>" — 이유 필수. 통과하지만 결과의 unreflected에 표시된다
}
필드는 필요한 것만 넣는다. 거부되면 메시지대로 고쳐 다시 실행한다. 소스 코드를 읽을 필요는 없다.
"기록이 바뀌었습니다" 거부는 다른 세션이 저장했다는 뜻: show로 읽고 반영한 뒤 다시 저장한다.
읽기 전용 턴(저장할 것이 없음): python3 -B wl.py skip "이유" — 원장에는 아무것도 쓰지 않는다."""
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


def session_path(d, tool, sid):
    return d / "sessions" / re.sub(r"[^A-Za-z0-9._-]", "_", f"{tool}_{sid}.json")


SESSION_KEYS = ("last_seen_seq", "turn", "saved_turn", "skipped_turn")


class SessionCorrupt(Exception):
    pass


@contextmanager
def locked(d):
    """The one .worklog/.lock: ledger appends and every session-file read→update→write happen inside it."""
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load_session(d, tool, sid):
    """Session side file (not part of the ledger). Missing keys are 0; None if absent; SessionCorrupt if unreadable."""
    path = session_path(d, tool, sid)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise SessionCorrupt(path)
    if not isinstance(data, dict):
        raise SessionCorrupt(path)
    s = {k: data.get(k, 0) for k in SESSION_KEYS}
    if any(type(v) is not int for v in s.values()):
        raise SessionCorrupt(path)
    return s


def session_or_new(d, tool, sid):
    try:
        return load_session(d, tool, sid) or dict.fromkeys(SESSION_KEYS, 0)
    except SessionCorrupt:
        return dict.fromkeys(SESSION_KEYS, 0)  # 손상 파일은 새로 만든다


def update_session(d, tool, sid, **changes):
    """Call inside locked(d)."""
    s = session_or_new(d, tool, sid)
    s.update(changes)
    path = session_path(d, tool, sid)
    path.parent.mkdir(exist_ok=True)
    write_atomic(path, json.dumps(s) + "\n")
    return s


def read_events(d):
    path = d / "events.jsonl"
    if not path.exists():
        return [], None
    events, prev = [], None
    for n, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            continue
        ev = json.loads(raw)
        if ev.get("prev") != prev or ev.get("seq") != len(events) + 1:
            raise Reject(f"events.jsonl {n}행의 연결(seq/prev)이 맞지 않습니다. 고치지 말고 사용자에게 보고하세요.")
        events.append(ev)
        prev = sha(raw)
    return events, prev


def empty_state():
    return {"format": FORMAT, "seq": 0, "goal": None, "status": "ACTIVE", "decisions": [],
            "constraints": [], "waiting": [], "next_action": None, "artifacts": [],
            "superseded": [], "removed_constraints": [], "updated_at": None, "updated_by": None}


def apply(state, ev):
    """Pure fold of one event into state. Raises Reject on invalid references."""
    s = json.loads(json.dumps(state))
    c, eid = ev.get("changes", {}), ev["id"]
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
        item = {"id": nid, "text": d["text"], "event": eid}
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
        s["constraints"].append({"id": f"C{ev['next_c']}", "text": text, "event": eid})
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


def render(s):
    by = s["updated_by"] or {}
    out = [f"# Worklog 현재 상태 (seq {s['seq']}, {s['updated_at']}, {by.get('tool')}:{by.get('session_id')})", "",
           f"최초 목표(원문): {s['goal'] or '(미정)'}",
           "※ 최초 목표의 값이 이후에 바뀌었다면 아래 '유효 결정'이 우선한다. replaces로 기록된 변경은 충돌이 아니다.",
           f"상태: {s['status']}", "", "## 유효 결정"]
    out += [f"- {d['id']}: {d['text']}" + (f" (대체: {d['replaces']})" if d.get("replaces") else "") for d in s["decisions"]] or ["- (없음)"]
    out += ["", "## 유지 제약 — 사용자가 바꾸기 전까지 유지"]
    out += [f"- {c['id']}: {c['text']}" for c in s["constraints"]] or ["- (없음)"]
    out += ["", "## 대기"] + ([f"- {w}" for w in s["waiting"]] or ["- (없음)"])
    out += ["", f"## 다음 행동", s["next_action"] or "(미정)"]
    if s["artifacts"]:
        out += ["", "## 산출물"] + [f"- {a['path']} sha256:{a['sha256'][:12]} ({a['event']})" for a in s["artifacts"]]
    if s["superseded"] or s["removed_constraints"]:
        out += ["", f"대체된 결정 {len(s['superseded'])}개·해제된 제약 {len(s['removed_constraints'])}개는 events.jsonl에 보존."]
    return "\n".join(out) + "\n"


def write_atomic(path, text):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def project(d, state):
    write_atomic(d / "state.json", json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    write_atomic(d / "state.md", render(state))


def validate(p, root, state):
    if not isinstance(p, dict):
        raise Reject("입력은 JSON 객체여야 합니다. `wl.py help` 참고.")
    unknown = set(p) - {"type", "summary", "quote", "goal", "decisions", "constraints", "constraints_remove",
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
    needs_quote = p["type"] in USER_TYPES or p.get("goal") or p.get("constraints_remove") or p.get("takeover")
    if needs_quote and not str(p.get("quote") or "").strip():
        raise Reject("이 저장에는 사용자 원문 일부 quote가 필요합니다.")
    if p.get("constraints_remove") and p["type"] not in REMOVE_TYPES:
        raise Reject(f"제약 해제는 사용자가 바꾼 경우에만 합니다. type을 {sorted(REMOVE_TYPES)} 중 하나로, quote에 해제를 말한 사용자 원문을 넣으세요. "
                     "같은 제약이 다시 들어오는 것은 자동으로 무시되므로 해제할 필요가 없습니다.")
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
    if not all(x for x in p.get("constraints", [])):
        raise Reject("constraints에 빈 문자열이 있습니다.")
    arts, bodies = [], []
    for a in arts_in:
        path = (Path(root) / a.get("path", "")).resolve()
        if not path.is_file():
            raise Reject(f"산출물 파일이 없습니다: {a.get('path')}")
        data = path.read_bytes()  # 한 번만 읽어 해시와 check 대조에 같은 바이트를 쓴다
        arts.append({"path": a["path"], "sha256": sha(data)})
        bodies.append(norm(data.decode("utf-8", "replace")))
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
    d.mkdir(exist_ok=True)
    with locked(d):
        events, prev = read_events(d)
        state, counters = fold(events)
        arts, bodies = validate(p, root, state)
        # 신선도: 이 세션이 마지막으로 본 seq 뒤에 다른 저장이 있으면 거부(읽기 전 쓰기 방지)
        try:
            sess = load_session(d, tool, sid)
        except SessionCorrupt:
            sess = None  # 손상: 무엇을 읽었는지 알 수 없으므로 없는 것으로 보고, 성공 시 새로 만든다
        if sess is None and events:
            raise Reject("show 먼저 실행하세요. 이 세션은 아직 현재 기록을 읽지 않았습니다.")
        if sess and sess["last_seen_seq"] < len(events):
            raise Reject(f"기록이 바뀌었습니다(seq {sess['last_seen_seq']}→{len(events)}). show 후 다시 저장하세요.")
        # writer.json은 마지막 작성자 정보. takeover는 선택(사용자가 명시적으로 넘길 때 기록)
        wpath = d / "writer.json"
        writer = json.loads(wpath.read_text()) if wpath.exists() else None
        acquired = {"from": writer, "reason": p["takeover"]} if p.get("takeover") else None
        changes = {k: p[k] for k in ("goal", "decisions", "constraints", "constraints_remove", "waiting",
                                     "next_action", "status") if k in p}
        ignored = []
        if "constraints" in changes:
            have = {norm(x["text"]) for x in state["constraints"]}
            keep = []
            for t in changes["constraints"]:
                (ignored if norm(t) in have else keep).append(t)
                have.add(norm(t))
            changes["constraints"] = keep
        if "decisions" in changes:
            have = {norm(x["text"]) for x in state["decisions"]}
            keep = []
            for item in changes["decisions"]:
                (ignored if not item.get("replaces") and norm(item["text"]) in have else keep).append(item)
                have.add(norm(item["text"]))
            changes["decisions"] = keep
        if arts:
            changes["artifacts"] = arts
        ev = {"v": 1, "seq": len(events) + 1, "id": f"E{len(events) + 1:04d}", "type": p["type"], "at": now(),
              "tool": tool, "session_id": sid, "summary": p["summary"], "quote": p.get("quote"),
              "refs": p.get("refs", []), "changes": changes, "prev": prev}
        for k in ("occurred_at", "source"):
            if k in p:
                ev[k] = p[k]
        if acquired:
            ev["writer_acquired"] = acquired
        try:  # 상태 계산·렌더링 실패는 원장 추가 전에 거부로 바꾼다
            new_state = apply(state, dict(ev, **counters))
            render(new_state)
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            raise Reject(f"상태를 만들 수 없는 입력입니다({type(e).__name__}: {e}). `wl.py help` 참고.")
        unreflected = []
        if arts:  # 산출물: 모든 유효 결정·제약이 본문에 인용으로 있거나 "미반영: 이유"여야 한다
            need = [x["id"] for x in new_state["decisions"] + new_state["constraints"]]
            check = p.get("check") or {}
            missing = [i for i in need if not str(check.get(i) or "").strip()]
            if missing:
                raise Reject(f"산출물 대조 누락: {missing}. 각 결정·제약마다 산출물 본문의 인용('...') 또는 \"미반영: 이유\"를 check에 적으세요. "
                             f"현재 목록: " + "; ".join(f"{x['id']}={x['text']}" for x in new_state["decisions"] + new_state["constraints"]))
            for i in need:
                value = norm(check[i])
                if value.startswith("미반영:"):
                    if not value[len("미반영:"):].strip():
                        raise Reject(f"check {i}의 미반영 이유가 비어 있습니다. \"미반영: <이유>\"로 적으세요.")
                    unreflected.append(i)
                    continue
                m = QUOTE.search(value)
                quote = norm(next(g for g in m.groups() if g) if m else value)
                if len(quote) < MIN_QUOTE:
                    raise Reject(f"check {i}의 인용이 너무 짧습니다({MIN_QUOTE}자 이상): '{quote}'. 산출물 본문의 문장을 더 길게 인용하세요.")
                if not any(quote in b for b in bodies):
                    raise Reject(f"check {i}의 인용이 산출물에 없습니다: '{quote}'. 산출물 본문에 그대로 있는 문장을 따옴표로 인용하거나, "
                                 "본문에 넣지 않았다면 \"미반영: 이유\"로 적으세요.")
            ev["check"] = {i: check[i] for i in need}
        line = json.dumps(ev, ensure_ascii=False, separators=(",", ":")).encode()
        with open(d / "events.jsonl", "ab") as f:
            f.write(line + b"\n")
            f.flush()
            os.fsync(f.fileno())
        # 저장 → 재읽기 → 상태 갱신 → 대조
        reread, _ = read_events(d)
        if reread[-1] != json.loads(line):
            raise Reject("저장한 사건을 다시 읽은 값이 다릅니다. 사용자에게 보고하세요.")
        rebuilt, _ = fold(reread)
        project(d, rebuilt)
        if json.loads((d / "state.json").read_text()) != rebuilt or rebuilt["seq"] != ev["seq"]:
            raise Reject("현재 상태 파일 대조 실패(원장은 저장됨). `wl.py show`로 복원하세요.")
        write_atomic(wpath, json.dumps({"tool": tool, "session_id": sid, "seq": ev["seq"]}) + "\n")
        turn = (sess or {}).get("turn", 0)
        update_session(d, tool, sid, last_seen_seq=ev["seq"], saved_turn=turn)
    print(json.dumps({"ok": True, "saved": ev["id"], "seq": ev["seq"], "verified": True, "unreflected": unreflected,
                      "ignored_duplicates": [x if isinstance(x, str) else x["text"] for x in ignored],
                      "decisions": [f"{x['id']}: {x['text']}" for x in rebuilt["decisions"]],
                      "constraints": [f"{x['id']}: {x['text']}" for x in rebuilt["constraints"]],
                      "waiting": rebuilt["waiting"], "next_action": rebuilt["next_action"]}, ensure_ascii=False))


def cmd_show(args):
    d = store(args.root)
    if not (d / "events.jsonl").exists():
        print("Worklog 기록 없음(.worklog/events.jsonl). 첫 save가 기록을 만든다.")
        return
    note = ""
    with locked(d):  # 잠금 뒤에 읽어야 동시 저장 이후의 투영을 과거 seq로 되돌리지 않는다
        events, _ = read_events(d)
        state, _ = fold(events)
        try:  # state.json·state.md 중 하나라도 다르거나 없으면 둘 다 다시 만든다
            if (json.loads((d / "state.json").read_text()) != state
                    or (d / "state.md").read_text(encoding="utf-8") != render(state)):
                raise ValueError
        except (OSError, ValueError):
            project(d, state)
            note = "(현재 상태가 원장과 달라 원장에서 다시 만들었다)\n"
        try:
            update_session(d, *identity(args), last_seen_seq=len(events))
        except Reject:
            pass  # 세션을 모르는 사람의 show는 읽기만 한다
    print(note + render(state), end="")


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
    try:
        who = identity(args)
    except Reject:
        who = None
    return d, who, event


def cmd_hook(args):
    """SessionStart hook: prints {"hookSpecificOutput": {..., "additionalContext": state.md}} and marks the state as seen.
    The injection is valid without a session ID; then no session file is touched."""
    d, who, _ = hook_input(args)
    if not d:
        return
    try:
        with locked(d):
            events, _ = read_events(d)
            if who:
                update_session(d, *who, last_seen_seq=len(events))
        text = (render(fold(events)[0]) if events else "Worklog 기록 없음. 첫 save가 기록을 만든다.\n")
        status = "PROVIDED" if events else "EMPTY"
    except (Reject, OSError, ValueError) as e:
        text, status = f"Worklog 현재 상태를 읽지 못함: {e}. 파일을 바꾸기 전에 `wl.py show`로 확인한다.\n", "UNAVAILABLE"
    root = d.parent
    head = f"[Worklog {FORMAT} SessionStart | {status} | root={root}]\n이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.\n"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": head + text}},
                     ensure_ascii=False))


def cmd_turn_start(args):
    """UserPromptSubmit hook: turn += 1. No output."""
    d, who, _ = hook_input(args)
    if d and who:
        with locked(d):
            update_session(d, *who, turn=session_or_new(d, *who)["turn"] + 1)


def cmd_stop_hook(args):
    """Stop hook: block once if this turn has neither save nor skip."""
    d, who, event = hook_input(args)
    if not (d and who) or event.get("stop_hook_active") is True:
        return
    try:
        s = load_session(d, *who) or dict.fromkeys(SESSION_KEYS, 0)
    except SessionCorrupt as e:
        print(json.dumps({"decision": "block", "reason": f"Worklog: 세션 파일을 읽을 수 없습니다({e}). "
                          "save 또는 skip으로 다시 만든 뒤 마치세요."}, ensure_ascii=False))
        return
    if s["turn"] in (s["saved_turn"], s["skipped_turn"]):
        return
    q = shlex.quote
    skip = f'python3 -B {q(str(Path(__file__).resolve()))} skip "이유" --tool {q(who[0])} --session {q(who[1])} --root {q(str(d.parent))}'
    print(json.dumps({"decision": "block", "reason": "Worklog: 이번 턴에 save가 없습니다. 기록할 것이 있으면 save, "
                      f"읽기 전용 턴이면 `{skip}`를 실행한 뒤 마치세요."}, ensure_ascii=False))


def cmd_skip(args):
    """Read-only turn: skipped_turn = turn. Writes nothing to the ledger."""
    if not str(args.reason or "").strip():
        raise Reject('skip에는 이유가 필요합니다: wl.py skip "읽기 전용: 질문에 답만 함"')
    d = store(args.root)
    tool, sid = identity(args)
    if not d.is_dir():
        print(json.dumps({"ok": True, "turn": 0}))
        return
    with locked(d):
        turn = session_or_new(d, tool, sid)["turn"]
        update_session(d, tool, sid, skipped_turn=turn)
    print(json.dumps({"ok": True, "turn": turn}))


def cmd_verify(args):
    d = store(args.root)
    events, _ = read_events(d)
    state, _ = fold(events)
    ok_json = (d / "state.json").exists() and json.loads((d / "state.json").read_text()) == state
    ok_md = (d / "state.md").exists() and (d / "state.md").read_text() == render(state)
    print(json.dumps({"ok": ok_json and ok_md, "events": len(events), "state_json": ok_json, "state_md": ok_md}))
    if not (ok_json and ok_md):
        sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wl.py", description="Worklog 공용 코어")
    commands = {"show": cmd_show, "save": cmd_save, "skip": cmd_skip, "verify": cmd_verify, "hook": cmd_hook,
                "turn-start": cmd_turn_start, "stop-hook": cmd_stop_hook}
    ap.add_argument("command", choices=[*commands, "help"])
    ap.add_argument("reason", nargs="?", help="skip의 이유")
    ap.add_argument("--root")
    ap.add_argument("--tool")
    ap.add_argument("--session")
    args = ap.parse_args(argv)
    args.root = args.root or os.getcwd()
    if args.command == "help":
        print(SAVE_HELP)
        return
    try:
        commands[args.command](args)
    except Reject as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
