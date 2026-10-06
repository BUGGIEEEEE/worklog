import fcntl, importlib.util, io, json, os, shlex, shutil, subprocess, sys, tempfile, time, unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

WL = Path(__file__).resolve().parents[1] / "core" / "wl.py"
INST = Path(__file__).resolve().parents[1] / "tools" / "install_project.py"


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


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_scenario(self):
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "계획", "quote": "7분", "goal": "하루 돌아보기",
                                         "decisions": [{"text": "수요일 저녁 식사 후 종이 노트 7분"}],
                                         "constraints": ["알림 등록 금지", "다른 프로젝트 자료 조회 금지"],
                                         "waiting": ["note-guide.md 다음 요청까지 보류"], "next_action": "대기"})
        self.assertEqual(r, 0, out)
        r, out = run(self.root, "save", {"type": "D_USER", "summary": "11분", "quote": "11분으로",
                                         "decisions": [{"text": "11분", "replaces": "D1"}]})
        self.assertEqual(r, 0, out)
        s = json.loads((self.root / ".worklog/state.json").read_text())
        self.assertEqual([d["id"] for d in s["decisions"]], ["D2"])
        self.assertEqual(len(s["constraints"]), 2)  # 제약은 언급 없이도 유지
        (self.root / "note-guide.md").write_text("수요일 저녁 식사 후 종이 노트에\n11분 동안 적는다. 알림은 따로 만들지 않는다.")
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "안내문", "artifacts": [{"path": "note-guide.md"}],
                                         "check": {"D2": "'11분'"}, "waiting": []})
        self.assertEqual(r, 2)
        self.assertIn("C1", out)  # 누락 제약 지목
        self.assertEqual(len((self.root / ".worklog/events.jsonl").read_text().splitlines()), 2)  # 거부 시 미저장
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "안내문", "artifacts": [{"path": "note-guide.md"}],
                                         "check": {"D2": "'노트에 11분 동안'", "C1": "본문: '알림은 따로 만들지 않는다'",
                                                   "C2": "미반영: 자료 조회를 하지 않았고 본문에 넣을 내용이 아님"},
                                         "waiting": []})
        self.assertEqual(r, 0, out)
        r, out = run(self.root, "verify")
        self.assertEqual(r, 0, out)

    def test_goal_once_and_quote(self):
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x"})[0], 2)  # quote 없음
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "goal": "g"})[0], 0)
        self.assertEqual(run(self.root, "save", {"type": "D_USER", "summary": "x", "quote": "q", "goal": "g2"})[0], 2)

    def test_writer(self):  # 세션 독점 없음: 다른 세션도 show 후 저장. takeover는 선택 기록
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="a")
        run(self.root, "show", session="b", tool="claude")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        self.assertEqual(json.loads((self.root / ".worklog/writer.json").read_text()),
                         {"tool": "claude", "session_id": "b", "seq": 2})
        run(self.root, "show", session="a")
        r, out = run(self.root, "save", {"type": "WRITER_ACQUIRED", "summary": "인수", "takeover": "사용자 승인",
                                         "quote": "코덱스가 이어서 해"}, session="a")
        self.assertEqual(r, 0, out)
        ev = json.loads((self.root / ".worklog/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["writer_acquired"]["from"]["session_id"], "b")

    def test_stale_projection_rebuilt(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["c"]})
        (self.root / ".worklog/state.json").write_text("{}")
        self.assertEqual(run(self.root, "verify")[0], 1)
        r, out = run(self.root, "show")
        self.assertIn("다시 만들었다", out)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_tampered_chain(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"})
        p = self.root / ".worklog/events.jsonl"
        lines = p.read_text().splitlines()
        p.write_text(lines[0].replace('"x"', '"X"') + "\n" + lines[1] + "\n")
        r, out = run(self.root, "show")
        self.assertEqual(r, 2)

    def test_duplicates_ignored_and_removal_rule(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["알림 금지"],
                                "decisions": [{"text": "11분"}]})
        r, out = run(self.root, "save", {"type": "CHANGE", "summary": "y", "constraints": [" 알림  금지", "게시 금지"],
                                         "decisions": [{"text": "11분"}]})
        self.assertEqual(r, 0, out)
        self.assertEqual(len(json.loads(out)["ignored_duplicates"]), 2)
        s = json.loads((self.root / ".worklog/state.json").read_text())
        self.assertEqual([c["id"] for c in s["constraints"]], ["C1", "C2"])
        self.assertEqual(len(s["decisions"]), 1)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "z", "quote": "대조해", "constraints_remove": {"C1": "중복"}})
        self.assertEqual(r, 2)
        r, out = run(self.root, "save", {"type": "D_USER", "summary": "z", "quote": "알림 금지는 풀어", "constraints_remove": {"C1": "사용자 해제"}})
        self.assertEqual(r, 0, out)

    def test_refs_and_import_fields(self):
        self.assertEqual(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "refs": ["B03"]})[0], 2)
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "refs": [{"kind": "block", "id": "B03"}],
                                         "occurred_at": "2026-08-11T13:54:43Z", "source": {"path": "a.jsonl", "line": 1}})
        self.assertEqual(r, 0, out)
        ev = json.loads((self.root / ".worklog/events.jsonl").read_text())
        self.assertEqual(ev["occurred_at"], "2026-08-11T13:54:43Z")
        self.assertEqual(ev["refs"][0]["id"], "B03")

    def test_hook_output(self):
        self.assertEqual(run(self.root, "hook"), (0, ""))  # 미연결 폴더: 빈 출력
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]})
        ctx = json.loads(run(self.root, "hook")[1])["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "SessionStart")
        self.assertIn("C1: 게시 금지", ctx["additionalContext"])

    def test_sample_log_folds(self):  # 저장된 원장 사본(tests/fixtures)이 그대로 읽힌다
        src = Path(__file__).resolve().parent / "fixtures" / "sample-events.jsonl"
        (self.root / ".worklog").mkdir()
        (self.root / ".worklog/events.jsonl").write_bytes(src.read_bytes())
        r, out = run(self.root, "show")
        self.assertEqual(r, 0, out)
        self.assertIn("D2: Log for 15 minutes after dinner (대체: D1)", out)
        self.assertIn("C2: Keep the guide under one page", out)
        self.assertIn("상태: PAUSED", out)
        self.assertEqual(run(self.root, "verify")[0], 0)


    def test_concurrent_tools_single_writer(self):
        import concurrent.futures as cf
        jobs = [("codex", f"c{i}") for i in range(4)] + [("claude", f"k{i}") for i in range(4)]
        def go(t):
            return run(self.root, "save", {"type": "REQUEST", "summary": t[1], "quote": "q"}, session=t[1], tool=t[0])[0]
        with cf.ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(go, jobs))
        self.assertEqual(codes.count(0), 1)  # 잠금으로 직렬화: 첫 저장만 성공, 나머지는 기록을 읽지 않아 거부
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_freshness(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="a")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 2)
        self.assertIn("show 먼저", out)
        self.assertEqual(run(self.root, "show", session="b", tool="claude")[0], 0)
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a2"}, session="a")[0], 0)  # seq 2
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 2)
        self.assertIn("기록이 바뀌었습니다(seq 1→2)", out)
        self.assertEqual(len((self.root / ".worklog/events.jsonl").read_text().splitlines()), 2)
        run(self.root, "show", session="b", tool="claude")
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        hook(self.root, "hook", session="c")  # SessionStart도 읽은 것으로 친다
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "z"}, session="c", tool="claude")[0], 0)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_check_quotes(self):
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
        self.assertEqual(len((self.root / ".worklog/events.jsonl").read_text().splitlines()), 2)  # skip은 원장에 안 씀
        self.assertEqual(json.loads(hook(self.root, "stop-hook", session="other")[1] or "{}"), {})  # 턴 시작 없는 세션은 통과

    def test_hooks_silent_without_worklog(self):
        for cmd in ("hook", "turn-start", "stop-hook"):
            self.assertEqual(hook(self.root, cmd), (0, ""), cmd)
        self.assertFalse((self.root / ".worklog").exists())

    # --- 회귀 시험 ---
    def test_fix1_session_updates_locked(self):
        import concurrent.futures as cf
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude")
        jobs = ["turn-start"] * 12 + ["hook"] * 6
        with cf.ThreadPoolExecutor(18) as ex:
            codes = [r for r, _ in ex.map(lambda c: hook(self.root, c), jobs)]
        self.assertEqual(codes, [0] * 18)
        s = json.loads(session_file(self.root).read_text())
        self.assertEqual((s["turn"], s["last_seen_seq"]), (12, 1))  # 갱신 손실 없음
        self.assertEqual(list(self.root.glob(".worklog/**/*.tmp")), [])  # 고유 임시 파일, 남김 없음

    def test_fix2_show_rereads_under_lock(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"})
        ledger = self.root / ".worklog/events.jsonl"
        full = ledger.read_bytes()
        ledger.write_bytes(full.splitlines(keepends=True)[0])  # show가 볼 seq 1
        (self.root / ".worklog/state.json").write_text("{}")  # 복구 필요
        with open(self.root / ".worklog/.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            env = dict(clean_env(), WL_TOOL="codex", WL_SESSION_ID="s1")
            p = subprocess.Popen([sys.executable, "-B", str(WL), "show", "--root", str(self.root)],
                                 stdout=subprocess.PIPE, text=True, env=env)
            time.sleep(0.5)
            ledger.write_bytes(full)  # 잠금 중 다른 save가 seq 2를 추가한 상황
        out, _ = p.communicate(timeout=30)
        self.assertIn("seq 2", out)
        self.assertEqual(json.loads((self.root / ".worklog/state.json").read_text())["seq"], 2)
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_fix3_artifact_read_once(self):
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
        self.assertEqual(r, 2)  # 무엇을 읽었는지 모르므로 show 먼저
        self.assertIn("show 먼저", out)
        session_file(self.root).write_text("{broken")
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))  # 예외 없이 새로 만든다
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 1)
        run(self.root, "show", tool="claude")
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude")[0], 0)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))

    def test_fix5_sessionstart_without_session_id(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]})
        r, out = hook(self.root, "hook", raw=json.dumps({"cwd": str(self.root)}))
        self.assertEqual(r, 0)
        self.assertIn("C1: 게시 금지", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual([p.name for p in (self.root / ".worklog/sessions").iterdir()], ["codex_s1.json"])  # 새 세션 파일 없음
        for cmd in ("turn-start", "stop-hook"):
            self.assertEqual(hook(self.root, cmd, raw=json.dumps({"cwd": str(self.root)})), (0, ""))

    def test_fix6_7_check_reason_and_quotes(self):
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
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})
        env = {"CODEX_THREAD_ID": "outer", "CLAUDE_CODE_SESSION_ID": "inner"}
        hook(self.root, "turn-start", raw="{}", extra=["--root", str(self.root)], env=env)
        self.assertEqual(json.loads(session_file(self.root, "claude_inner").read_text())["turn"], 1)
        self.assertFalse(session_file(self.root, "codex_outer").exists())
        r, out = hook(self.root, "skip", raw="", extra=["이유", "--root", str(self.root)], env=env)
        self.assertEqual((r, json.loads(out)["turn"]), (0, 1))

    def test_fix9_bad_stdin(self):
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
        self.assertIn("[Worklog worklog/1 SessionStart | EMPTY |", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 1)
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.assertEqual(run(self.root, "skip", tool="claude", extra=["읽기 전용"])[0], 0)
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        hook(self.root, "turn-start")
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="new", tool="claude")
        self.assertEqual(r, 0, out)  # 원장이 없으면 show 먼저 규칙 없음
        self.assertTrue((self.root / ".worklog/events.jsonl").exists())

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
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"})  # 미연결 폴더의 Hook은 빈 출력
        p = subprocess.run(cmd, shell=True, input=json.dumps({"cwd": str(self.root), "source": "compact", "session_id": "x"}),
                           capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")
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
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "11분"}]})
        ledger = self.root / ".worklog/events.jsonl"
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
        wl = load_wl()
        payload = {"type": "REQUEST", "summary": "x", "quote": "q"}
        with mock.patch.object(wl, "render", side_effect=TypeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(wl.Reject) as cm:
                wl.cmd_save(Namespace(root=str(self.root), tool="codex", session="s1"))
        self.assertIn("상태를 만들 수 없는 입력", str(cm.exception))
        self.assertFalse((self.root / ".worklog/events.jsonl").exists())

    def test_show_rebuilds_state_md(self):
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]})
        md = self.root / ".worklog/state.md"
        for damage in (lambda: md.write_text("wrong state"), md.unlink):
            damage()
            self.assertEqual(run(self.root, "verify")[0], 1)
            r, out = run(self.root, "show")
            self.assertIn("다시 만들었다", out)
            self.assertEqual(run(self.root, "verify")[0], 0)


if __name__ == "__main__":
    unittest.main()
