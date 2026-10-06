import fcntl, importlib.util, io, json, os, shlex, shutil, subprocess, sys, tempfile, time, unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

WL = Path(__file__).resolve().parents[1] / "core" / "wl.py"
INST = Path(__file__).resolve().parents[1] / "tools" / "install_project.py"
MIG = Path(__file__).resolve().parents[1] / "tools" / "migrate_v1_to_v2.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_V2 = FIXTURES / "sample-v2"  # wl.py로 만든 형식 2 샘플(작업 2개, 가상 내용)
V1_LEDGER = FIXTURES / "sample-events.jsonl"  # 형식 1 원장 샘플(사건 3건). 이전 도구 시험에만 쓴다


def load_wl():
    spec = importlib.util.spec_from_file_location("wl", WL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.endswith("SESSION_ID") and k not in ("CODEX_THREAD_ID", "WL_TOOL")}


def run(root, cmd, payload=None, session="s1", tool="codex", extra=()):
    env = dict(clean_env(), WL_TOOL=tool, WL_SESSION_ID=session)
    p = subprocess.run([sys.executable, "-B", str(WL), cmd, *extra, "--root", str(root)], input=json.dumps(payload) if payload else "",
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def hook(root, cmd, session="s1", tool="claude", env=None, raw=None, extra=(), **event):
    """Hook as the tool runs it: no --root, event JSON on stdin (cwd, session_id, ...)."""
    event = dict({"cwd": str(root), "session_id": session}, **event)
    p = subprocess.run([sys.executable, "-B", str(WL), cmd, "--tool", tool, *extra], input=json.dumps(event) if raw is None else raw,
                       capture_output=True, text=True, env=dict(clean_env(), **(env or {})), cwd=tempfile.gettempdir())
    return p.returncode, p.stdout


def session_file(root, name="claude_s1"):
    return root / ".worklog" / "sessions" / f"{name}.json"


def new_work(root, title="t", session="s1", tool="codex", quote="새 작업"):
    return run(root, "new-work", session=session, tool=tool, extra=[title, "--quote", quote])


def use(root, wid="t", session="s1", tool="codex", quote="이어서"):
    return run(root, "use", session=session, tool=tool, extra=[wid, "--quote", quote])


class CoreTest(unittest.TestCase):
    """형식 1 시험을 형식 2로 옮긴 것: 작업 하나(`t`)를 new-work로 만든 뒤 같은 동작."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.wd = self.root / ".worklog/works/t"

    def start(self, root=None, session="s1", tool="codex"):
        r, out = new_work(root or self.root, "t", session=session, tool=tool)
        self.assertEqual((r, json.loads(out)["id"]), (0, "t"), out)

    def test_scenario(self):
        self.start()
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "계획", "quote": "7분", "goal": "하루 돌아보기",
                                         "decisions": [{"text": "수요일 저녁 식사 후 종이 노트 7분"}],
                                         "constraints": ["알림 등록 금지", "다른 프로젝트 자료 조회 금지"],
                                         "waiting": ["note-guide.md 다음 요청까지 보류"], "next_action": "대기"})
        self.assertEqual(r, 0, out)
        r, out = run(self.root, "save", {"type": "D_USER", "summary": "11분", "quote": "11분으로",
                                         "decisions": [{"text": "11분", "replaces": "D1"}]})
        self.assertEqual(r, 0, out)
        s = json.loads((self.wd / "state.json").read_text())
        self.assertEqual([d["id"] for d in s["decisions"]], ["D2"])
        self.assertEqual(len(s["constraints"]), 2)  # 제약은 언급 없이도 유지
        (self.root / "note-guide.md").write_text("수요일 저녁 식사 후 종이 노트에\n11분 동안 적는다. 알림은 따로 만들지 않는다.")
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "안내문", "artifacts": [{"path": "note-guide.md"}],
                                         "check": {"D2": "'11분'"}, "waiting": []})
        self.assertEqual(r, 2)
        self.assertIn("C1", out)  # 누락 제약 지목
        self.assertEqual(len((self.wd / "events.jsonl").read_text().splitlines()), 2)  # 거부 시 미저장
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "안내문", "artifacts": [{"path": "note-guide.md"}],
                                         "check": {"D2": "'노트에 11분 동안'", "C1": "본문: '알림은 따로 만들지 않는다'",
                                                   "C2": "미반영: 자료 조회를 하지 않았고 본문에 넣을 내용이 아님"},
                                         "waiting": []})
        self.assertEqual(r, 0, out)
        r, out = run(self.root, "verify")
        self.assertEqual(r, 0, out)

    def test_goal_once_and_quote(self):
        self.start()
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x"})[0], 2)  # quote 없음
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "goal": "g"})[0], 0)
        self.assertEqual(run(self.root, "save", {"type": "D_USER", "summary": "x", "quote": "q", "goal": "g2"})[0], 2)

    def test_writer(self):  # 세션 독점 없음: 다른 세션도 show 후 저장. takeover는 선택 기록
        self.start(session="a")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="a")
        use(self.root, session="b", tool="claude")
        run(self.root, "show", session="b", tool="claude")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        self.assertEqual(json.loads((self.wd / "writer.json").read_text()),
                         {"tool": "claude", "session_id": "b", "seq": 2})
        run(self.root, "show", session="a")
        r, out = run(self.root, "save", {"type": "WRITER_ACQUIRED", "summary": "인수", "takeover": "사용자 승인",
                                         "quote": "코덱스가 이어서 해"}, session="a")
        self.assertEqual(r, 0, out)
        ev = json.loads((self.wd / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["writer_acquired"]["from"]["session_id"], "b")

    def test_stale_projection_rebuilt(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["c"]})
        (self.wd / "state.json").write_text("{}")
        self.assertEqual(run(self.root, "verify")[0], 1)
        r, out = run(self.root, "show")
        self.assertIn("다시 만들었다", out)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_tampered_chain(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"})
        p = self.wd / "events.jsonl"
        lines = p.read_text().splitlines()
        p.write_text(lines[0].replace('"x"', '"X"') + "\n" + lines[1] + "\n")
        r, out = run(self.root, "show")
        self.assertEqual(r, 2)

    def test_duplicates_ignored_and_removal_rule(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["알림 금지"],
                                "decisions": [{"text": "11분"}]})
        r, out = run(self.root, "save", {"type": "CHANGE", "summary": "y", "constraints": [" 알림  금지", "게시 금지"],
                                         "decisions": [{"text": "11분"}]})
        self.assertEqual(r, 0, out)
        self.assertEqual(len(json.loads(out)["ignored_duplicates"]), 2)
        s = json.loads((self.wd / "state.json").read_text())
        self.assertEqual([c["id"] for c in s["constraints"]], ["C1", "C2"])
        self.assertEqual(len(s["decisions"]), 1)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "z", "quote": "대조해", "constraints_remove": {"C1": "중복"}})
        self.assertEqual(r, 2)
        r, out = run(self.root, "save", {"type": "D_USER", "summary": "z", "quote": "알림 금지는 풀어", "constraints_remove": {"C1": "사용자 해제"}})
        self.assertEqual(r, 0, out)

    def test_refs_and_import_fields(self):
        self.start()
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "refs": ["B03"]})[0], 2)
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "refs": [{"kind": "block", "id": "B03"}],
                                         "occurred_at": "2026-08-11T13:54:43Z", "source": {"path": "a.jsonl", "line": 1}})
        self.assertEqual(r, 0, out)
        ev = json.loads((self.wd / "events.jsonl").read_text())
        self.assertEqual(ev["occurred_at"], "2026-08-11T13:54:43Z")
        self.assertEqual(ev["refs"][0]["id"], "B03")

    def test_hook_output(self):
        self.assertEqual(run(self.root, "hook"), (0, ""))  # 미연결 폴더: 빈 출력
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]})
        ctx = json.loads(run(self.root, "hook")[1])["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "SessionStart")
        self.assertIn("C1: 게시 금지", ctx["additionalContext"])

    def test_sample_v2_folds(self):  # 저장된 형식 2 원장 사본(tests/fixtures/sample-v2, 작업 2개)이 그대로 읽힌다
        shutil.copytree(SAMPLE_V2 / ".worklog", self.root / ".worklog")
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual(r, 0, out)
        self.assertEqual([(w["work"], w["events"], w["status"]) for w in json.loads(out)["works"]],
                         [("garden-plan", 2, "ACTIVE"), ("reading-log", 3, "PAUSED")])
        self.assertIn("NO_CURRENT_WORK", json.loads(run(self.root, "hook")[1])["hookSpecificOutput"]["additionalContext"])
        garden = (self.root / ".worklog/works/garden-plan/events.jsonl").read_bytes()
        out = use(self.root, "reading-log", quote="reading-log 이어서")[1]
        self.assertIn("D2: Log for 15 minutes after dinner (대체: D1)", out)
        self.assertIn("C2: Keep the guide under one page", out)
        self.assertIn("상태: PAUSED", out)
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"})
        self.assertEqual((r, json.loads(out)["seq"]), (0, 4), out)
        self.assertEqual((self.root / ".worklog/works/garden-plan/events.jsonl").read_bytes(), garden)  # 다른 작업 불변
        self.assertEqual(run(self.root, "verify", extra=["--all"])[0], 0)

    def test_concurrent_tools_single_writer(self):
        import concurrent.futures as cf
        self.start()
        jobs = [("codex", f"c{i}") for i in range(4)] + [("claude", f"k{i}") for i in range(4)]
        def go(t):  # work 필드로 작업을 명시한 저장
            return run(self.root, "save", {"work": "t", "type": "REQUEST", "summary": t[1], "quote": "q"}, session=t[1], tool=t[0])[0]
        with cf.ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(go, jobs))
        self.assertEqual(codes.count(0), 1)  # 잠금으로 직렬화: 첫 저장만 성공, 나머지는 기록을 읽지 않아 거부
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_freshness(self):
        self.start(session="a")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="a")
        r, out = run(self.root, "save", {"work": "t", "type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 2)  # 읽지 않은 세션
        self.assertIn("show 먼저", out)
        r, out = use(self.root, session="b", tool="claude")  # use는 현황을 보여 주고 읽은 것으로 친다
        self.assertEqual(r, 0, out)
        self.assertIn("(seq 1,", out)
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a2"}, session="a")[0], 0)  # seq 2
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 2)
        self.assertIn("기록이 바뀌었습니다(seq 1→2)", out)
        self.assertEqual(len((self.wd / "events.jsonl").read_text().splitlines()), 2)
        run(self.root, "show", session="b", tool="claude")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        use(self.root, session="c", tool="claude")  # c는 seq 3까지 읽음
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a4"}, session="a")[0], 2)  # a는 seq 2까지
        run(self.root, "show", session="a")
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a4"}, session="a")[0], 0)  # seq 4
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "z"}, session="c", tool="claude")[0], 2)
        hook(self.root, "hook", session="c")  # SessionStart도 현재 작업을 읽은 것으로 친다
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "z"}, session="c", tool="claude")[0], 0)
        self.assertEqual(run(self.root, "verify", extra=["--work", "t"])[0], 0)

    def test_check_quotes(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "11분"}],
                                "constraints": ["알림 금지"]})
        (self.root / "a.md").write_text("저녁 식사 후\n  11분   동안 적는다.")
        (self.root / "b.md").write_text("알림은 만들지 않는다.")
        arts = [{"path": "a.md"}, {"path": "b.md"}]
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": arts,
                                         "check": {"D1": "본문 인용 '7분 동안'", "C1": "'알림은 만들지 않는다'"}})
        self.assertEqual(r, 2)
        self.assertIn("check D1의 인용이 산출물에 없습니다: '7분 동안'", json.loads(out)["error"])
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": arts,
                                         "check": {"D1": "11분으로 반영함", "C1": "미반영: 알림은 만들지 않음"}})
        self.assertEqual(r, 2)  # 인용 없으면 값 전체를 대조
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": arts,
                                         "check": {"D1": 'D1 반영: "식사 후 11분 동안"', "C1": "미반영: 알림은 만들지 않음"}})
        self.assertEqual(r, 0, out)  # 공백 정규화, 큰따옴표
        self.assertEqual(json.loads(out)["unreflected"], ["C1"])
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": arts,
                                         "check": {"D1": "'11분 동안'", "C1": "'알림은 만들지 않는다'"}})
        self.assertEqual(r, 0, out)  # 두 번째 산출물에만 있는 인용도 통과
        self.assertEqual(json.loads(out)["unreflected"], [])

    def test_stop_hook_turns(self):
        self.start(tool="claude")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude")
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))
        r, out = hook(self.root, "stop-hook")
        self.assertEqual(r, 0)
        block = json.loads(out)
        self.assertEqual(block["decision"], "block")
        self.assertIn("skip", block["reason"])
        self.assertEqual(hook(self.root, "stop-hook", stop_hook_active=True), (0, ""))  # 반복 방지
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude")[0], 0)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        hook(self.root, "turn-start")
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.assertEqual(run(self.root, "skip", tool="claude")[0], 2)  # 이유 필수
        r, out = run(self.root, "skip", tool="claude", extra=["읽기 전용: 질문에 답만 함"])
        self.assertEqual((r, json.loads(out)), (0, {"ok": True, "turn": 2}))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(len((self.wd / "events.jsonl").read_text().splitlines()), 2)  # skip은 원장에 안 씀
        self.assertEqual(json.loads(hook(self.root, "stop-hook", session="other")[1] or "{}"), {})  # 턴 시작 없는 세션은 통과

    def test_hooks_silent_without_worklog(self):
        for cmd in ("hook", "turn-start", "stop-hook"):
            self.assertEqual(hook(self.root, cmd), (0, ""), cmd)
        self.assertFalse((self.root / ".worklog").exists())

    # --- 회귀 시험 ---
    def test_fix1_session_updates_locked(self):
        import concurrent.futures as cf
        self.start(tool="claude")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude")
        jobs = ["turn-start"] * 12 + ["hook"] * 6
        with cf.ThreadPoolExecutor(18) as ex:
            codes = [r for r, _ in ex.map(lambda c: hook(self.root, c), jobs)]
        self.assertEqual(codes, [0] * 18)
        s = json.loads(session_file(self.root).read_text())
        self.assertEqual((s["turn"], s["last_seen"], s["current_work"]), (12, {"t": 1}, "t"))  # 갱신 손실 없음
        self.assertEqual(list(self.root.glob(".worklog/**/*.tmp")), [])  # 고유 임시 파일, 남김 없음

    def test_fix2_show_rereads_under_lock(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"})
        ledger = self.wd / "events.jsonl"
        full = ledger.read_bytes()
        ledger.write_bytes(full.splitlines(keepends=True)[0])  # show가 볼 seq 1
        (self.wd / "state.json").write_text("{}")  # 복구 필요
        with open(self.root / ".worklog/.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            env = dict(clean_env(), WL_TOOL="codex", WL_SESSION_ID="s1")
            p = subprocess.Popen([sys.executable, "-B", str(WL), "show", "--root", str(self.root)],
                                 stdout=subprocess.PIPE, text=True, env=env)
            time.sleep(0.5)
            ledger.write_bytes(full)  # 잠금 중 다른 save가 seq 2를 추가한 상황
        out, _ = p.communicate(timeout=30)
        self.assertIn("seq 2", out)
        self.assertEqual(json.loads((self.wd / "state.json").read_text())["seq"], 2)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_fix3_artifact_read_once(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "11분"}]})
        art = self.root / "a.md"
        art.write_text("7분 동안 적는다.")
        real, reads = Path.read_bytes, []
        def fake(path):  # 두 번째 읽기부터 내용이 바뀌는 산출물
            if path.name != "a.md":
                return real(path)
            reads.append(1)
            return "7분 동안 적는다.".encode() if len(reads) == 1 else "11분 동안 적는다.".encode()
        wl = load_wl()
        payload = {"type": "RESULT", "summary": "s", "artifacts": [{"path": "a.md"}], "check": {"D1": "'11분 동안 적는다'"}}
        with mock.patch.object(Path, "read_bytes", fake), mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(wl.Reject) as cm:
                wl.cmd_save(Namespace(root=str(self.root), tool="codex", session="s1"))
        self.assertIn("인용이 산출물에 없습니다", str(cm.exception))
        self.assertEqual(len(reads), 1)

    def test_fix4_corrupt_session_file(self):
        self.start(tool="claude")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude")
        hook(self.root, "turn-start")
        for bad in ("{broken", "[]", '{"turn": "2"}', '{"turn": true}'):
            session_file(self.root).write_text(bad)
            r, out = hook(self.root, "stop-hook")
            self.assertEqual(r, 0, bad)
            self.assertEqual(json.loads(out)["decision"], "block", bad)
            self.assertIn("세션 파일을 읽을 수 없습니다", json.loads(out)["reason"])
            self.assertEqual(hook(self.root, "stop-hook", stop_hook_active=True), (0, ""))
        r, out = run(self.root, "skip", tool="claude", extra=["읽기 전용"])  # skip이 새로 만든다
        self.assertEqual(r, 0, out)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        session_file(self.root).write_text("{broken")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude")
        self.assertEqual(r, 2)  # 현재 작업도 잃었으므로 작업 지정 요구
        self.assertIn("현재 작업이 없습니다", out)
        r, out = run(self.root, "save", {"work": "t", "type": "CHECKPOINT", "summary": "y"}, tool="claude")
        self.assertEqual(r, 2)  # 무엇을 읽었는지 모르므로 show 먼저
        self.assertIn("show 먼저", out)
        session_file(self.root).write_text("{broken")
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))  # 예외 없이 새로 만든다
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 1)
        use(self.root, tool="claude")
        run(self.root, "show", tool="claude")
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude")[0], 0)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))

    def test_fix5_sessionstart_without_session_id(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"],
                                "next_action": "게시 전 검토"})
        r, out = hook(self.root, "hook", raw=json.dumps({"cwd": str(self.root)}))
        self.assertEqual(r, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("| NO_CURRENT_WORK |", ctx)  # 세션을 모르면 현재 작업도 없다: 목록만
        self.assertIn("- t · t · ACTIVE · ", ctx)
        self.assertIn("다음: 게시 전 검토", ctx)
        self.assertEqual([p.name for p in (self.root / ".worklog/sessions").iterdir()], ["codex_s1.json"])  # 새 세션 파일 없음
        for cmd in ("turn-start", "stop-hook"):
            self.assertEqual(hook(self.root, cmd, raw=json.dumps({"cwd": str(self.root)})), (0, ""))

    def test_fix6_7_check_reason_and_quotes(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "11분"}],
                                "constraints": ["알림 금지"]})
        (self.root / "a.md").write_text("저녁 식사 후\n11분 동안 적는다. 알림은 만들지 않는다.")
        def save(d1, c1):
            return run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": "a.md"}],
                                           "check": {"D1": d1, "C1": c1}})
        r, out = save("'11분 동안 적는다'", "미반영:   ")
        self.assertEqual(r, 2)
        self.assertIn("C1의 미반영 이유가 비어", out)
        r, out = save("'11분'", "'알림은 만들지'")
        self.assertEqual(r, 2)
        self.assertIn("D1의 인용이 너무 짧습니다(4자 이상)", out)
        r, out = save("본문: '저녁 식사 후\n  11분 동안'", "미반영: 알림 등록 안내는 범위 밖")  # 여러 줄 인용
        self.assertEqual(r, 0, out)
        self.assertEqual(json.loads(out)["unreflected"], ["C1"])

    def test_fix8_tool_picks_its_native_env(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        env = {"CODEX_THREAD_ID": "outer", "CLAUDE_CODE_SESSION_ID": "inner"}
        hook(self.root, "turn-start", raw="{}", extra=["--root", str(self.root)], env=env)
        self.assertEqual(json.loads(session_file(self.root, "claude_inner").read_text())["turn"], 1)
        self.assertFalse(session_file(self.root, "codex_outer").exists())
        r, out = hook(self.root, "skip", raw="", extra=["이유", "--root", str(self.root)], env=env)
        self.assertEqual((r, json.loads(out)["turn"]), (0, 1))

    def test_fix9_bad_stdin(self):
        self.start(tool="claude")
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude")
        for raw in ("[1]", "not json", json.dumps({"cwd": 123, "session_id": 5})):
            for cmd in ("hook", "turn-start", "stop-hook"):
                r, out = hook(self.root, cmd, raw=raw, extra=["--root", str(self.root)])
                self.assertEqual(r, 0, (raw, cmd))
        hook(self.root, "turn-start")
        r, out = hook(self.root, "stop-hook", stop_hook_active="false")  # 문자열은 참이 아님
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_fix10_worklog_dir_is_connection(self):
        (self.root / ".worklog").mkdir()
        r, out = hook(self.root, "hook")
        self.assertIn("[Worklog worklog/2 SessionStart | EMPTY |", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 1)
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.assertEqual(run(self.root, "skip", tool="claude", extra=["읽기 전용"])[0], 0)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        hook(self.root, "turn-start")
        self.start(session="new", tool="claude")
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="new", tool="claude")
        self.assertEqual(r, 0, out)  # 원장이 없으면 show 먼저 규칙 없음
        self.assertTrue((self.wd / "events.jsonl").exists())

    def test_installer_claude(self):
        inst = Path(__file__).resolve().parents[1] / "tools" / "install_project.py"
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        for _ in range(2):  # 두 번 실행해도 블록은 하나
            subprocess.run([sys.executable, "-B", str(inst), "--tool", "claude", "--root", str(self.root)], check=True, capture_output=True)
        text = (self.root / "CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# 기존 내용"))
        self.assertEqual(text.count("worklog-shared:begin"), 1)
        hooks = json.loads((self.root / ".claude/settings.local.json").read_text())["hooks"]["SessionStart"]
        self.assertEqual(len(hooks), 1)
        cmd = hooks[0]["hooks"][0]["command"]
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="x", tool="claude")
        self.assertEqual(r, 2)  # 설치 직후에는 작업이 없어 저장이 거부된다
        self.assertIn("현재 작업이 없습니다", json.loads(out)["error"])
        self.start(session="x", tool="claude")
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]},
                     session="x", tool="claude")
        self.assertEqual(r, 0, out)
        p = subprocess.run(cmd, shell=True, input=json.dumps({"cwd": str(self.root), "source": "compact", "session_id": "x"}),
                           capture_output=True, text=True)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("| PROVIDED |", out["additionalContext"])  # 설치된 Hook이 기록 있는 현재 작업을 주입
        self.assertIn("C1: 게시 금지", out["additionalContext"])
        self.assertTrue((self.root / ".claude/skills/worklog/SKILL.md").exists())
        backups = list(self.root.glob("CLAUDE.md.bak-worklog-*"))
        self.assertEqual(len(backups), 1)  # 날짜·시각 붙은 백업, 두 번째 실행은 변경 없음
        self.assertEqual(backups[0].read_text(), "# 기존 내용\n")

    # --- 배포 전 검토 회귀 시험 ---
    def install(self, *extra, inst=INST):
        p = subprocess.run([sys.executable, "-B", str(inst), "--tool", "claude", "--root", str(self.root), *extra],
                           capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_installer_refuses_link_outside_root(self):
        outside = Path(tempfile.mkdtemp()) / "outside.md"
        outside.write_text("밖의 파일\n")
        (self.root / "CLAUDE.md").symlink_to(outside)
        r, out = self.install()
        self.assertEqual(r, 2, out)
        self.assertIn("--root 밖을 가리키는 링크", json.loads(out)["error"])
        self.assertEqual(outside.read_text(), "밖의 파일\n")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["CLAUDE.md"])  # 다른 파일도 쓰지 않음
        (self.root / "CLAUDE.md").unlink()
        (self.root / ".claude").symlink_to(outside.parent, target_is_directory=True)  # 부모 디렉터리 링크
        r, out = self.install()
        self.assertEqual(r, 2, out)
        self.assertEqual(sorted(p.name for p in outside.parent.iterdir()), ["outside.md"])
        self.assertFalse((self.root / "CLAUDE.md").exists())

    def test_installer_keeps_unrelated_hooks(self):
        sp = self.root / ".claude/settings.local.json"
        sp.parent.mkdir()
        old = f'python3 -B "{WL}" stop-hook --tool claude'  # 과거 큰따옴표 형식 설치본
        sp.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python3 /helpers/owl.py --check"},
            {"type": "command", "command": old},
            {"type": "command", "command": "echo keep-me"}]}]}}))
        self.assertEqual(self.install()[0], 0)
        cmds = [h["command"] for g in json.loads(sp.read_text())["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(cmds[:2], ["python3 /helpers/owl.py --check", "echo keep-me"])
        self.assertEqual(len(cmds), 3)  # 과거 Worklog Hook은 새 명령 하나로 교체
        self.assertTrue(cmds[2].endswith(" stop-hook --tool claude"))
        self.assertNotIn(old, cmds)

    def test_installer_quotes_special_path(self):
        repo = Path(tempfile.mkdtemp()) / "clone-$WL_ABSENT 'q'"
        for part in ("core", "tools", "adapters"):
            shutil.copytree(INST.parents[1] / part, repo / part)
        r, out = self.install(inst=repo / "tools" / "install_project.py")
        self.assertEqual(r, 0, out)
        cmd = json.loads((self.root / ".claude/settings.local.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        p = subprocess.run(cmd, shell=True, input=json.dumps({"cwd": str(self.root), "session_id": "x"}),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("EMPTY", json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"])
        self.assertIn(shlex.quote(str(repo.resolve() / "core" / "wl.py")), (self.root / "CLAUDE.md").read_text())  # 지침 명령도 인용

    def test_installer_bad_settings_changes_nothing(self):
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        sp = self.root / ".claude/settings.local.json"
        sp.parent.mkdir()
        for bad in ("{broken", "[]", '{"hooks": {"Stop": "x"}}'):
            sp.write_text(bad)
            r, out = self.install()
            self.assertEqual(r, 2, bad)
            self.assertIn("error", json.loads(out))
            self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 기존 내용\n")
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".claude", "CLAUDE.md"])  # 백업·.worklog 없음
            self.assertEqual([p.name for p in sp.parent.iterdir()], ["settings.local.json"])

    def install_at(self, when, *extra):
        """Installer main() in-process with a fixed backup timestamp → (exit code, stdout)."""
        spec = importlib.util.spec_from_file_location("install_project", INST)
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)
        out, code = io.StringIO(), 0
        argv = ["install_project.py", "--tool", "claude", "--root", str(self.root), *extra]
        with mock.patch.object(inst, "stamp", return_value=when), mock.patch.object(sys, "argv", argv), \
                mock.patch("sys.stdout", out):
            try:
                inst.main()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_installer_moved_repo_replaces_hooks(self):
        base = Path(tempfile.mkdtemp())
        old, new = base / "old-place", base / "new place"
        for part in ("core", "tools", "adapters"):
            shutil.copytree(INST.parents[1] / part, old / part)
        sp = self.root / ".claude/settings.local.json"
        sp.parent.mkdir()
        sp.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python3 /helpers/owl.py --check"},
            {"type": "command", "command": 'python3 -B "/gone/elsewhere/core/wl.py" stop-hook --tool claude'}]}]}}))
        self.assertEqual(self.install(inst=old / "tools/install_project.py")[0], 0)
        shutil.move(old, new)  # 저장소 이동 뒤 새 위치에서 재설치
        self.assertEqual(self.install(inst=new / "tools/install_project.py")[0], 0)
        hooks = json.loads(sp.read_text())["hooks"]
        for event in ("SessionStart", "UserPromptSubmit", "Stop"):
            cmds = [h["command"] for g in hooks[event] for h in g["hooks"] if "core/wl.py" in h["command"]]
            self.assertEqual(len(cmds), 1, (event, cmds))
            self.assertIn(shlex.quote(str(new.resolve() / "core" / "wl.py")), cmds[0])
        self.assertIn("python3 /helpers/owl.py --check", [h["command"] for g in hooks["Stop"] for h in g["hooks"]])

    def test_installer_refuses_backup_link(self):
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        outside = Path(tempfile.mkdtemp()) / "backup-outside.md"
        outside.write_text("Outside unchanged\n")
        (self.root / "CLAUDE.md.bak-worklog-20300102-030405").symlink_to(outside)
        r, out = self.install_at("20300102-030405")
        self.assertEqual(r, 2, out)
        self.assertIn("--root 밖을 가리키는 링크", json.loads(out)["error"])
        self.assertEqual(outside.read_text(), "Outside unchanged\n")
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 기존 내용\n")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["CLAUDE.md", "CLAUDE.md.bak-worklog-20300102-030405"])

    def test_installer_refuses_worklog_link(self):
        outside = Path(tempfile.mkdtemp())
        (self.root / "real").mkdir()
        for target in (outside, self.root / "real"):  # 밖이든 안이든 .worklog 링크는 거부
            (self.root / ".worklog").symlink_to(target, target_is_directory=True)
            r, out = self.install()
            self.assertEqual(r, 2, out)
            self.assertIn(".worklog", json.loads(out)["error"])
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".worklog", "real"])
            (self.root / ".worklog").unlink()
        self.assertEqual(list(outside.iterdir()), [])

    def test_installer_backup_same_second_kept(self):
        (self.root / "CLAUDE.md").write_text("v1\n")
        self.assertEqual(self.install_at("20300102-030405")[0], 0)
        (self.root / "CLAUDE.md").write_text("v2\n")
        self.assertEqual(self.install_at("20300102-030405")[0], 0)
        b = self.root / "CLAUDE.md.bak-worklog-20300102-030405"
        self.assertEqual(b.read_text(), "v1\n")  # 덮어쓰지 않음
        self.assertEqual(b.with_name(b.name + "-1").read_text(), "v2\n")

    def test_save_rejects_bad_types(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "11분"}]})
        ledger = self.wd / "events.jsonl"
        before = ledger.read_bytes()
        (self.root / "a.md").write_text("11분 동안 적는다.")
        bad = [{"constraints": "AB"}, {"next_action": 42}, {"waiting": "x"}, {"constraints": [1]}, {"goal": 3},
               {"decisions": [{"text": 1}]}, {"decisions": [{"text": "y", "replaces": 1}]}, {"summary": 5},
               {"constraints_remove": ["C1"]}, {"artifacts": ["a.md"]},
               {"artifacts": [{"path": "a.md"}], "check": {"D1": 5}}]
        for extra in bad:
            with self.subTest(extra=extra):
                r, out = run(self.root, "save", dict({"type": "CHECKPOINT", "summary": "y"}, **extra))
                self.assertEqual(r, 2, out)
                self.assertFalse(json.loads(out)["ok"])
                self.assertEqual(ledger.read_bytes(), before)  # 원장 무변경
        self.assertEqual(run(self.root, "show")[0], 0)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_save_renders_before_append(self):
        self.start()
        wl = load_wl()
        payload = {"type": "REQUEST", "summary": "x", "quote": "q"}
        with mock.patch.object(wl, "render", side_effect=TypeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(wl.Reject) as cm:
                wl.cmd_save(Namespace(root=str(self.root), tool="codex", session="s1"))
        self.assertIn("상태를 만들 수 없는 입력", str(cm.exception))
        self.assertFalse((self.wd / "events.jsonl").exists())

    def test_show_rebuilds_state_md(self):
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]})
        md = self.wd / "state.md"
        for damage in (lambda: md.write_text("wrong state"), md.unlink):
            damage()
            self.assertEqual(run(self.root, "verify")[0], 1)
            r, out = run(self.root, "show")
            self.assertIn("다시 만들었다", out)
            self.assertEqual(run(self.root, "verify")[0], 0)


class Base(unittest.TestCase):
    """형식 2 시험 공용 도구(시험 없음)."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.d = self.root / ".worklog"

    def ok(self, result):
        r, out = result
        self.assertEqual(r, 0, out)
        return json.loads(out)

    def refused(self, result, text):
        r, out = result
        self.assertEqual(r, 2, out)
        self.assertIn(text, json.loads(out)["error"])

    def used(self, result, wid):
        r, out = result
        self.assertEqual(r, 0, out)
        self.assertTrue(out.startswith(f"[use] 현재 작업: {wid} · "), out)  # 성공하면 JSON 대신 현황을 출력
        return out

    def index(self):
        return json.loads((self.d / "index.json").read_text())

    def ctx(self, **kw):
        r, out = hook(self.root, "hook", **kw)
        self.assertEqual(r, 0, out)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def migrate(self, *extra):
        p = subprocess.run([sys.executable, "-B", str(MIG), "--project", str(self.root), *extra], capture_output=True, text=True)
        return p.returncode, p.stdout

    def make_v1(self):
        """형식 1과 같은 사건 줄을 가진 원장을 .worklog 최상위에 만든다(다른 폴더에서 저장 후 옮김)."""
        src = Path(tempfile.mkdtemp())
        new_work(src, "t")
        run(src, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "goal": "요약 검토", "constraints": ["게시 금지"]})
        run(src, "save", {"type": "D_USER", "summary": "y", "quote": "q", "decisions": [{"text": "3장까지"}], "status": "PAUSED"})
        self.d.mkdir()
        for name in ("events.jsonl", "writer.json"):
            (self.d / name).write_bytes((src / ".worklog/works/t" / name).read_bytes())
        (self.d / "state.json").write_text('{"format": "worklog/1"}')
        (self.d / "state.md").write_text("old\n")
        (self.d / "sessions").mkdir()
        (self.d / "sessions/codex_old.json").write_text('{"last_seen_seq": 2, "turn": 3}')
        return (self.d / "events.jsonl").read_bytes()

    def snapshot(self):
        return {str(p.relative_to(self.d)): p.read_bytes() for p in sorted(self.d.rglob("*")) if p.is_file()}


class WorksTest(Base):
    """형식 2: 작업 여러 개·사용자 지정·index·이전 도구."""
    def test_two_works_list_and_select(self):
        self.assertEqual(self.ok(new_work(self.root, "Habit Plan"))["id"], "habit-plan")
        self.assertEqual(self.ok(new_work(self.root, "Recipe Note"))["id"], "recipe-note")  # 현재 작업 = recipe-note
        self.assertEqual(sorted(p.name for p in (self.d / "works").iterdir()), ["habit-plan", "recipe-note"])
        self.assertEqual(list((self.d / "works/habit-plan").iterdir()), [])  # 빈 폴더(원장 없음)
        time.sleep(1.1)  # 시각은 초 단위: 갱신순을 구분하려면 다른 초여야 한다
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "r", "quote": "q", "goal": "레시피 정리"}))
        works = self.ok(run(self.root, "works"))
        self.assertEqual(works["current_work"], "recipe-note")
        self.assertEqual([(w["id"], w["status"], w["last_seq"]) for w in works["works"]],
                         [("recipe-note", "ACTIVE", 1), ("habit-plan", "ACTIVE", 0)])  # 같은 상태 안에서 최근 갱신순
        recipe = (self.d / "works/recipe-note/events.jsonl").read_bytes()
        self.assertIn("기록 없음", self.used(use(self.root, "habit-plan", quote="habit-plan 이어서"), "habit-plan"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "h", "quote": "q", "goal": "습관 만들기"}))
        self.assertEqual((self.d / "works/recipe-note/events.jsonl").read_bytes(), recipe)  # 다른 작업 원장 불변
        self.assertIn("# Worklog 현재 상태 — habit-plan · Habit Plan (seq 1", run(self.root, "show")[1])
        self.assertEqual(json.loads((self.d / "works/habit-plan/state.json").read_text())["format"], "worklog/2")
        r, out = run(self.root, "show", session="s2")  # 현재 작업이 없는 세션: 목록만, exit 0
        self.assertEqual(r, 0)
        self.assertIn("현재 작업 없음", out)
        self.assertIn("- recipe-note · Recipe Note · ACTIVE", out)
        self.assertIn("레시피 정리", run(self.root, "show", session="s2", extra=["--work", "recipe-note"])[1])
        self.assertEqual(self.ok(run(self.root, "verify"))["work"], "habit-plan")

    def test_save_refused_without_current_work(self):
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        self.assertIn("현재 작업이 없습니다", json.loads(out)["error"])
        self.assertFalse(self.d.exists())  # 미연결 폴더에 아무것도 만들지 않음
        new_work(self.root, "Habit Plan")
        self.refused(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="s2"),
                  '현재 작업이 없습니다. 사용자가 지정한 작업으로 use <id> --quote 또는 new-work "제목" --quote 후 저장하세요. '
                  "작업 목록: habit-plan · Habit Plan · ACTIVE")
        self.assertFalse((self.d / "works/habit-plan/events.jsonl").exists())
        self.refused(run(self.root, "save", {"work": "nope", "type": "CHECKPOINT", "summary": "x"}, session="s2"), "없는 작업입니다: nope")
        self.refused(run(self.root, "save", {"work": "../x", "type": "CHECKPOINT", "summary": "x"}, session="s2"), "없는 작업입니다")
        self.assertEqual(self.ok(run(self.root, "save", {"work": "habit-plan", "type": "CHECKPOINT", "summary": "x"},
                                     session="s2"))["work"], "habit-plan")  # work 필드로 명시하면 저장
        self.assertEqual(self.index()["works"]["habit-plan"]["last_seq"], 1)
        self.refused(run(self.root, "verify", session="s2"), "verify --work <id> 또는 verify --all")

    def test_use_and_new_work_need_quote(self):
        self.refused(run(self.root, "new-work", extra=["Habit Plan"]), "사용자 원문이 필요합니다")
        self.refused(new_work(self.root, "Habit Plan", quote="  "), "사용자 원문이 필요합니다")
        self.refused(new_work(self.root, " ", quote="q"), "new-work")
        self.assertFalse(self.d.exists())
        self.ok(new_work(self.root, "Habit Plan", session="a"))
        self.refused(run(self.root, "use", extra=["habit-plan"]), "사용자 원문이 필요합니다")
        self.refused(use(self.root, "habit-plan", quote=""), "사용자 원문이 필요합니다")
        self.refused(use(self.root, "nope"), "없는 작업입니다: nope. 작업 목록: habit-plan · Habit Plan · ACTIVE")
        self.refused(run(self.root, "use", extra=["--quote", "q"]), "use <id>")
        self.assertFalse(session_file(self.root, "codex_s1").exists())  # 거부된 use는 세션을 바꾸지 않음

    def test_slug_ids(self):
        titles = ["Habit Plan", "habit  plan!", "Habit Plan", "습관 계획", "습관 계획 둘", "Café — Notes", "x" * 60, "x" * 60]
        ids = [self.ok(new_work(self.root, t))["id"] for t in titles]
        self.assertEqual(ids, ["habit-plan", "habit-plan-2", "habit-plan-3", "work", "work-2", "caf-notes",
                               "x" * 40, "x" * 38 + "-2"])
        self.assertEqual(self.index()["works"]["work"]["title"], "습관 계획")  # 한글 제목은 index에
        self.assertEqual(set(self.index()["works"]), set(ids))

    def test_index_concurrent_new_work(self):
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(8) as ex:
            outs = list(ex.map(lambda i: new_work(self.root, "Same Title", session=f"c{i}"), range(8)))
        ids = [self.ok(o)["id"] for o in outs]
        self.assertEqual(sorted(ids), sorted(["same-title"] + [f"same-title-{n}" for n in range(2, 9)]))
        self.assertEqual(set(self.index()["works"]), set(ids))  # 갱신 손실 없음
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["index"]["ok"], True)
        self.assertEqual(list(self.d.glob("**/*.tmp")), [])

    def test_freshness_per_work(self):
        new_work(self.root, "A", session="x")
        new_work(self.root, "B", session="x")  # x의 현재 작업 = b
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "b1", "quote": "q"}, session="x"))
        use(self.root, "a", session="x")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a1", "quote": "q"}, session="x"))
        self.refused(run(self.root, "save", {"work": "b", "type": "CHECKPOINT", "summary": "y"}, session="y"), "show 먼저")
        self.assertIn("(seq 1,", self.used(use(self.root, "b", session="y"), "b"))  # use가 읽은 것으로 친다
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "b2"}, session="y"))  # b seq 2
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a2"}, session="x"))  # a는 바뀌지 않았으므로 통과
        self.refused(run(self.root, "save", {"work": "b", "type": "CHECKPOINT", "summary": "b?"}, session="x"),
                  "기록이 바뀌었습니다(seq 1→2)")
        run(self.root, "show", session="x", extra=["--work", "b"])
        self.ok(run(self.root, "save", {"work": "b", "type": "CHECKPOINT", "summary": "b3"}, session="x"))
        s = json.loads(session_file(self.root, "codex_x").read_text())
        self.assertEqual((s["current_work"], s["last_seen"]), ("a", {"a": 2, "b": 3}))

    def test_verify_all(self):
        new_work(self.root, "A")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a", "quote": "q"}))
        new_work(self.root, "B")  # 사건 없는 작업도 일관
        out = self.ok(run(self.root, "verify", extra=["--all"]))
        self.assertEqual(([w["work"] for w in out["works"]], out["index"]["ok"]), (["a", "b"], True))
        (self.d / "works/ghost").mkdir()
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual((r, json.loads(out)["index"]["unindexed_folders"]), (1, ["ghost"]))
        (self.d / "works/ghost").rmdir()
        (self.d / "works/a/state.json").write_text("{}")
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual((r, [w["ok"] for w in json.loads(out)["works"]]), (1, [False, True]))
        run(self.root, "show", extra=["--work", "a"])  # 투영 복구
        idx = self.index()
        idx["works"]["a"]["last_seq"] = 5
        (self.d / "index.json").write_text(json.dumps(idx))
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual((r, json.loads(out)["index"]["mismatched"]), (1, ["a"]))
        idx["works"]["a"]["last_seq"] = 1
        (self.d / "index.json").write_text(json.dumps(idx))
        shutil.rmtree(self.d / "works/b")
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual((r, json.loads(out)["index"]["missing_folders"]), (1, ["b"]))
        (self.d / "works/b").mkdir()
        self.ok(run(self.root, "verify", extra=["--all"]))
        self.ok(run(self.root, "verify", extra=["--work", "b"]))

    def test_archive_reopen(self):
        new_work(self.root, "Habit Plan")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "goal": "습관"}))
        self.assertEqual(self.ok(run(self.root, "archive", extra=["habit-plan"]))["status"], "COMPLETED")
        self.assertEqual(self.index()["works"]["habit-plan"]["status"], "COMPLETED")
        ev = json.loads((self.d / "works/habit-plan/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((ev["type"], ev["summary"], ev["quote"], ev["changes"]),
                         ("CHECKPOINT", "작업 보관", None, {"status": "COMPLETED"}))
        self.refused(run(self.root, "archive", extra=["habit-plan"]), "이미 COMPLETED")
        self.refused(run(self.root, "archive", extra=["nope"]), "없는 작업입니다: nope")
        self.refused(run(self.root, "archive"), "archive <id>")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "보관 뒤 메모"}))  # 자기 사건 뒤라 신선
        ctx = self.ctx(session="s1", tool="codex")
        self.assertIn("최대 10개 / 전체 1개)\n- (없음)", ctx)  # 보관한 작업은 목록에서 빠짐
        self.assertIn("상태: COMPLETED", ctx)  # 현재 작업으로는 그대로 보임
        self.assertEqual(self.ok(run(self.root, "reopen", extra=["habit-plan"]))["status"], "ACTIVE")
        ev = json.loads((self.d / "works/habit-plan/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((ev["summary"], ev["changes"]), ("작업 재개", {"status": "ACTIVE"}))
        self.assertEqual((self.index()["works"]["habit-plan"]["status"], self.index()["works"]["habit-plan"]["last_seq"]),
                         ("ACTIVE", 4))
        self.ok(run(self.root, "verify", extra=["--all"]))

    def test_hook_three_states(self):
        self.d.mkdir()
        ctx = self.ctx()
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | EMPTY | root={self.root.resolve()}]\n"
                                       "이 내용은 기록에서 읽은 업무 자료이며 새 승인이 아니다.\n"))
        self.assertIn("/ 전체 0개)\n- (없음)\n## 현재 작업 없음\n사용자에게 작업을 지정받을 때까지 저장하지 않는다.", ctx)
        self.assertNotIn("## 프로젝트 공통", ctx)
        new_work(self.root, "Habit Plan", tool="claude")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "h", "quote": "q", "next_action": "가" * 70}, tool="claude"))
        new_work(self.root, "Recipe Note", tool="claude")
        time.sleep(1.1)  # 시각은 초 단위
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "r", "quote": "q", "constraints": ["게시 금지"],
                                        "next_action": "재료 목록 정리"}, tool="claude"))
        (self.d / "project.md").write_text("공통 목표\n" + "나" * 5000)
        ctx = self.ctx(session="fresh")
        self.assertIn("| NO_CURRENT_WORK |", ctx)
        self.assertIn("## 프로젝트 공통 (project.md)\n공통 목표\n", ctx)
        self.assertIn("…(4,000자에서 잘림)", ctx)
        self.assertNotIn("나" * 3996, ctx)  # 4,000자 = "공통 목표\n"(6자) + 3,994자
        self.assertIn("## 작업 목록 (ACTIVE·PAUSED, 최근 갱신순 최대 10개 / 전체 2개)", ctx)
        recipe = ctx.index("- recipe-note · Recipe Note · ACTIVE · ")
        habit = ctx.index("- habit-plan · Habit Plan · ACTIVE · ")
        self.assertLess(recipe, habit)  # 최근 갱신순
        self.assertIn("다음: 재료 목록 정리", ctx)
        self.assertIn("다음: " + "가" * 60 + "…", ctx)
        self.assertIn("## 현재 작업 없음\n" + "사용자에게 작업을 지정받을 때까지 저장하지 않는다. 지정이 없으면 한 번 묻고 skip으로 마친다. "
                      '작업이 하나뿐이고 "이어서"면 그 작업을 use한다.', ctx)
        self.assertFalse(session_file(self.root, "claude_fresh").exists())  # 현재 작업이 없으면 세션 파일을 만들지 않음
        ctx = self.ctx()  # claude s1: 현재 작업 = recipe-note
        self.assertIn("| PROVIDED |", ctx)
        self.assertIn("## 현재 작업: recipe-note · Recipe Note\n# Worklog 현재 상태 — recipe-note · Recipe Note (seq 1", ctx)
        self.assertIn("C1: 게시 금지", ctx)
        new_work(self.root, "Empty One", tool="claude")
        self.assertIn("## 현재 작업: empty-one · Empty One\n기록 없음.", self.ctx())

    def test_hook_refuses_v1_ledger(self):
        self.d.mkdir()
        (self.d / "events.jsonl").write_text("")
        self.assertIn("| UNAVAILABLE |", self.ctx())
        self.assertIn("migrate_v1_to_v2.py", self.ctx())
        self.refused(new_work(self.root, "x"), "형식 1 기록")
        self.assertFalse((self.d / "index.json").exists())

    def test_stop_hook_selected_turn(self):
        new_work(self.root, "Habit Plan", tool="claude")
        hook(self.root, "turn-start")
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.used(use(self.root, "habit-plan", tool="claude"), "habit-plan")  # 이번 턴에 작업을 선택함
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        hook(self.root, "turn-start")
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.ok(new_work(self.root, "Recipe Note", tool="claude"))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(json.loads(session_file(self.root).read_text())["selected_turn"], 2)

    def test_migrate_dry_run_apply_rerun(self):
        ledger = self.make_v1()
        before = self.snapshot()
        r, out = self.migrate("--work-id", "summary-v3-review", "--title", "요약 v3 검토")
        self.assertEqual(r, 0, out)
        plan = json.loads(out)
        self.assertEqual((plan["mode"], plan["events"], plan["sessions_deleted"]), ("dry-run", 2, ["codex_old.json"]))
        self.assertIn("events.jsonl → works/summary-v3-review/events.jsonl", plan["moves"])
        self.assertEqual(self.snapshot(), before)  # dry-run은 아무것도 쓰지 않음(.lock 포함)
        r, out = self.migrate("--work-id", "summary-v3-review", "--title", "요약 v3 검토", "--apply")
        self.assertEqual(r, 0, out)
        rep = json.loads(out)
        self.assertEqual((rep["mode"], rep["hashes_match"], rep["line_hashes_match"], rep["state_format"]),
                         ("apply", True, True, "worklog/2"))
        wd = self.d / "works/summary-v3-review"
        self.assertEqual((wd / "events.jsonl").read_bytes(), ledger)  # 바이트 불변
        self.assertEqual(sorted(p.name for p in wd.iterdir()), ["events.jsonl", "state.json", "state.md", "writer.json"])
        self.assertFalse((self.d / "events.jsonl").exists())
        self.assertEqual(list((self.d / "sessions").iterdir()), [])
        w = self.index()["works"]["summary-v3-review"]
        self.assertEqual((w["title"], w["status"], w["last_seq"]), ("요약 v3 검토", "PAUSED", 2))
        self.assertEqual(self.migrate("--work-id", "summary-v3-review", "--apply")[0], 2)
        r, out = self.migrate("--work-id", "other")
        self.assertIn("이미 형식 2", json.loads(out)["error"])
        self.ok(run(self.root, "verify", extra=["--all"]))
        self.assertIn("D1: 3장까지", self.used(use(self.root, "summary-v3-review"), "summary-v3-review"))
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "이전 뒤 첫 저장"}))
        self.assertTrue((wd / "events.jsonl").read_bytes().startswith(ledger))  # 이전 뒤에도 기존 사건 해시 불변
        self.ok(run(self.root, "verify", extra=["--all"]))

    def test_migrate_refusals(self):
        r, out = self.migrate("--work-id", "x")
        self.assertIn("실제 디렉터리가 아닙니다", json.loads(out)["error"])
        self.d.mkdir()
        r, out = self.migrate("--work-id", "x")
        self.assertIn("형식 1 원장이 없습니다", json.loads(out)["error"])
        self.d.rmdir()
        self.make_v1()
        before = self.snapshot()
        for bad in ("Bad_ID", "a" * 41, "x-", "../x"):
            r, out = self.migrate("--work-id", bad, "--apply")
            self.assertIn("--work-id는", json.loads(out)["error"], bad)
        self.assertEqual(self.snapshot(), before)
        lines = (self.d / "events.jsonl").read_text().splitlines()
        (self.d / "events.jsonl").write_text(lines[1] + "\n")  # 연결이 끊긴 원장은 옮기지 않음
        r, out = self.migrate("--work-id", "x", "--apply")
        self.assertIn("연결(seq/prev)", json.loads(out)["error"])
        self.assertFalse((self.d / "works").exists())
        self.assertFalse((self.d / "index.json").exists())
        self.assertTrue((self.d / "sessions/codex_old.json").exists())

    def test_migrate_sample_v1_log(self):  # 저장된 형식 1 원장 사본이 바이트 그대로 works/<id>/로 옮겨진다
        src = V1_LEDGER
        self.d.mkdir()
        (self.d / "events.jsonl").write_bytes(src.read_bytes())
        r, out = self.migrate("--work-id", "reading-log", "--apply")
        self.assertEqual((r, json.loads(out)["hashes_match"]), (0, True), out)
        self.assertEqual((self.d / "works/reading-log/events.jsonl").read_bytes(), src.read_bytes())
        self.ok(run(self.root, "verify", extra=["--all"]))
        self.assertEqual(self.index()["works"]["reading-log"]["status"], "PAUSED")


class FixTest(Base):
    """배포 전 검토 회귀 시험(링크·타입·index·writer·동시 실행, use 현황 출력)."""
    def outside(self):
        out = Path(tempfile.mkdtemp())  # 프로젝트 밖(같은 임시 영역의 형제)
        (out / "sentinel.json").write_text('{"keep": true}')
        return out

    def no_traceback(self, args, **kw):
        p = subprocess.run([sys.executable, "-B", str(WL), *args, "--root", str(self.root)], capture_output=True, text=True,
                           env=dict(clean_env(), WL_TOOL="codex", WL_SESSION_ID=kw.get("session", "s1")), input=kw.get("stdin", ""))
        self.assertNotIn("Traceback", p.stderr)
        return p.returncode, p.stdout

    def test_c1_works_link_refused(self):
        out = self.outside()
        self.d.mkdir()
        (self.d / "works").symlink_to(out, target_is_directory=True)
        self.refused(new_work(self.root, "A"), "심볼릭 링크")
        (self.d / "works").unlink()
        new_work(self.root, "A")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a"}))
        shutil.rmtree(self.d / "works")
        (self.d / "works").symlink_to(out, target_is_directory=True)  # 만든 뒤 바꿔치기
        for cmd, payload, extra in (("save", {"type": "CHECKPOINT", "summary": "x"}, ()), ("show", None, ()),
                                    ("verify", None, ("--all",)), ("archive", None, ("a",))):
            with self.subTest(cmd=cmd):
                self.refused(run(self.root, cmd, payload, extra=extra), "심볼릭 링크")
        (self.d / "works").unlink()
        (self.d / "works").mkdir()
        (self.d / "works/a").symlink_to(out, target_is_directory=True)  # 작업 폴더만 링크
        self.refused(run(self.root, "save", {"type": "CHECKPOINT", "summary": "x"}), "심볼릭 링크")
        self.refused(use(self.root, "a"), "심볼릭 링크")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["sentinel.json"])  # 밖에는 아무것도 생기지 않음
        self.assertIn("UNAVAILABLE", self.ctx(session="s1", tool="codex"))

    def test_lock_link_refused(self):
        out = self.outside()
        self.d.mkdir()
        (self.d / ".lock").symlink_to(out / "sentinel.json")
        self.refused(new_work(self.root, "A"), "심볼릭 링크")
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))  # Hook은 멈추지 않고 조용히 통과
        self.assertEqual((out / "sentinel.json").read_text(), '{"keep": true}')  # 링크 대상을 비우지 않음

    def test_c3_work_field_type(self):
        new_work(self.root, "A")
        ledger_absent = not (self.d / "works/a/events.jsonl").exists()
        for bad in (False, 0, [], {}, "", "  ", None):
            with self.subTest(bad=bad):
                self.refused(run(self.root, "save", {"work": bad, "type": "CHECKPOINT", "summary": "x"}),
                             "work는 비어 있지 않은 문자열(작업 id)이어야 합니다")
        self.assertTrue(ledger_absent and not (self.d / "works/a/events.jsonl").exists())  # 현재 작업으로 대체하지 않음

    def test_c4_corrupt_index_entry(self):
        new_work(self.root, "A")
        good = self.index()
        for bad, why in (({}, "title"), (dict(good["works"]["a"], last_seq="1"), "last_seq"),
                         (dict(good["works"]["a"], status="DONE"), "status"), ("x", "객체가 아님")):
            with self.subTest(why=why):
                (self.d / "index.json").write_text(json.dumps({"format": "worklog/2", "works": {"a": bad}}))
                r, out = self.no_traceback(["use", "a", "--quote", "a 이어서"], session="fresh")
                self.refused((r, out), "index.json의 작업 a 항목이 손상됨")
                self.assertIn(why, json.loads(out)["error"])
                self.assertFalse(session_file(self.root, "codex_fresh").exists())  # 거부 전에 상태를 바꾸지 않음
                for args in (["works"], ["show"], ["verify", "--all"], ["new-work", "B", "--quote", "q"], ["archive", "a"]):
                    self.assertEqual(self.no_traceback(args)[0], 2, args)
                self.assertEqual(self.no_traceback(["save"], stdin='{"type":"CHECKPOINT","summary":"x"}')[0], 2)
                self.assertIn("UNAVAILABLE", self.ctx(session="s1", tool="codex"))
        (self.d / "index.json").write_text(json.dumps(good))
        self.assertIn("기록 없음", self.used(use(self.root, "a", session="fresh"), "a"))

    def test_c5_broken_writer_json(self):
        new_work(self.root, "A")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a1"}))
        (self.d / "works/a/writer.json").write_text("{broken")
        out = self.ok(run(self.root, "verify", extra=["--all"]))  # 정보용 파일: ok는 유지, 경고만
        self.assertEqual(out["warnings"], ["a: writer.json 읽기 불가"])
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a2"}))  # 없는 것으로 보고 덮어씀
        self.assertEqual(json.loads((self.d / "works/a/writer.json").read_text())["seq"], 2)
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["warnings"], [])

    def test_c8_verify_all_waits_for_lock(self):
        new_work(self.root, "A")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a1"}))
        with open(self.d / ".lock", "w") as lock:  # 저장이 원장·투영을 쓰고 index는 아직인 순간
            fcntl.flock(lock, fcntl.LOCK_EX)
            p = subprocess.Popen([sys.executable, "-B", str(WL), "verify", "--all", "--root", str(self.root)],
                                 stdout=subprocess.PIPE, text=True, env=clean_env())
            time.sleep(0.5)
            idx = self.index()
            idx["works"]["a"]["last_seq"] = 2
            line = json.dumps({"v": 1, "seq": 2, "id": "E0002", "type": "CHECKPOINT", "at": idx["works"]["a"]["updated_at"],
                               "tool": "codex", "session_id": "s1", "summary": "a2", "quote": None, "refs": [], "changes": {},
                               "prev": load_wl().sha((self.d / "works/a/events.jsonl").read_bytes().rstrip(b"\n"))},
                              ensure_ascii=False, separators=(",", ":"))
            with open(self.d / "works/a/events.jsonl", "a") as f:
                f.write(line + "\n")
            self.assertIsNone(p.poll())  # 잠금을 기다린다
            wl = load_wl()
            state = wl.fold(wl.read_events(self.d / "works/a")[0])[0]
            wl.project(self.d / "works/a", state, "a", "A")
            (self.d / "index.json").write_text(json.dumps(idx))
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, out)  # 일시 상태가 아니라 완료된 상태를 읽었다
        self.assertEqual(json.loads(out)["works"][0]["events"], 2)

    def test_use_shows_state_and_marks_seen(self):
        new_work(self.root, "A", session="x")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a", "quote": "q", "constraints": ["게시 금지"]}, session="x"))
        out = self.used(use(self.root, "a", session="y", quote="a 이어서"), "a")
        self.assertIn("C1: 게시 금지", out)  # show와 같은 현황
        s = json.loads(session_file(self.root, "codex_y").read_text())
        self.assertEqual((s["current_work"], s["last_seen"]), ("a", {"a": 1}))
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y1"}, session="y"))  # use 직후 save 통과
        self.assertEqual(set(self.ok(new_work(self.root, "B", session="y"))), {"ok", "id", "title", "current_work"})

    # --- 이전 도구 C2·C6·C7 ---
    def test_c2_sessions_link_refused(self):
        self.make_v1()
        out = self.outside()
        shutil.rmtree(self.d / "sessions")
        (self.d / "sessions").symlink_to(out, target_is_directory=True)
        before = self.snapshot()
        for mode in ((), ("--apply",)):
            r, res = self.migrate("--work-id", "w", *mode)
            self.assertEqual(r, 2, res)
            self.assertIn("실제 디렉터리가 아닙니다", json.loads(res)["error"])
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((out / "sentinel.json").exists())
        (self.d / "sessions").unlink()
        (self.d / "sessions").mkdir()
        (self.d / "sessions/link.json").symlink_to(out / "sentinel.json")  # 밖을 가리키는 세션 파일 링크
        (self.d / "sessions/codex_a.json").write_text("{}")
        r, res = self.migrate("--work-id", "w", "--apply")
        self.assertEqual(r, 0, res)
        res = json.loads(res)
        self.assertEqual((res["sessions_deleted"], res["sessions_skipped"]), (["codex_a.json"], ["link.json"]))
        self.assertTrue((out / "sentinel.json").exists())

    def test_c6_bad_file_kinds_change_nothing(self):
        for name, damage in (("state.json", lambda p: (p.unlink(), p.mkdir())),
                             ("writer.json", lambda p: (p.unlink(), p.symlink_to(self.outside() / "sentinel.json"))),
                             ("state.md", lambda p: (p.unlink(), p.mkdir()))):
            with self.subTest(name=name):
                self.setUp()
                self.make_v1()
                damage(self.d / name)
                before = self.snapshot()
                r, out = self.migrate("--work-id", "w", "--apply")
                self.assertEqual(r, 2, out)
                self.assertIn("일반 파일이 아닙니다", json.loads(out)["error"])
                self.assertEqual(self.snapshot(), before)  # 이동·index·삭제 없음
                self.assertFalse((self.d / "works").exists() or (self.d / "index.json").exists())

    def test_c7_concurrent_migration(self):
        ledger = self.make_v1()
        with open(self.d / ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            procs = [subprocess.Popen([sys.executable, "-B", str(MIG), "--project", str(self.root), "--work-id", w, "--apply"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for w in ("first", "second")]
            time.sleep(0.8)
            self.assertEqual([p.poll() for p in procs], [None, None])  # 둘 다 잠금을 기다린다
        results = [p.communicate(timeout=30) + (p.returncode,) for p in procs]
        self.assertEqual(sorted(r[2] for r in results), [0, 2])
        loser = next(r for r in results if r[2] == 2)
        self.assertIn("이미 형식 2", json.loads(loser[0])["error"])
        self.assertNotIn("Traceback", loser[1])
        works = [p.name for p in (self.d / "works").iterdir()]
        self.assertEqual(len(works), 1)
        self.assertEqual((self.d / "works" / works[0] / "events.jsonl").read_bytes(), ledger)


if __name__ == "__main__":
    unittest.main()
