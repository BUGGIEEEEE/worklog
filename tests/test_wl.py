import contextlib, fcntl, hashlib, importlib.util, io, json, os, re, shlex, shutil, subprocess, sys, tempfile, time, unittest
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


TEST_HOME = Path(tempfile.mkdtemp())  # WL_HOME for every run: update mode off, so no test starts a background update check
(TEST_HOME / "config.json").write_text('{"update": "off"}')
os.environ["WL_HOME"] = str(TEST_HOME)  # also for installer runs without an explicit env and in-process imports: the installer writes the registry there (2.17.0), never into the real ~/.worklog


TOOL_ENV_NAMES = {name for _, name in load_wl().TOOL_ENV}  # every session variable the core reads (CODEX_THREAD_ID, ANTIGRAVITY_CONVERSATION_ID, ...)


def clean_env():
    """The test process's environment without any tool's session variables, so a run inside Codex, Claude Code, Antigravity or
    pi sees no session of its own."""
    env = {k: v for k, v in os.environ.items() if not k.endswith("SESSION_ID") and k not in TOOL_ENV_NAMES | {"WL_TOOL"}}
    env["WL_HOME"] = str(TEST_HOME)
    return env


def run(root, cmd, payload=None, session="s1", tool="codex", extra=(), env=None):
    env = dict(clean_env(), WL_TOOL=tool, WL_SESSION_ID=session, **(env or {}))
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


def new_work(root, title="t", session="s1", tool="codex", quote="새 작업", force=True):
    """Fixture setup: each call stands for its own turn, so --force (2.26.0 refuses a second new-work of a session in the same
    turn, turn 0 too). The guard itself is tested with force=False (AutoConnectTest, NewWorkRetryTest)."""
    return run(root, "new-work", session=session, tool=tool, extra=[title, "--quote", quote, *(["--force"] if force else [])])


def use(root, wid="t", session="s1", tool="codex", quote="이어서"):
    return run(root, "use", session=session, tool=tool, extra=[wid, "--quote", quote])


class VersionTest(unittest.TestCase):
    def test_version_matches_changelog(self):
        """`wl.py version` works without a .worklog and its number is the first `## x.y.z` in CHANGELOG.md."""
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = run(Path(tmp), "version")
        self.assertEqual(rc, 0)
        info = json.loads(out)
        changelog = (WL.parents[1] / "CHANGELOG.md").read_text()
        first = re.search(r"^## (\d+\.\d+\.\d+)", changelog, re.M)
        self.assertIsNotNone(first, "CHANGELOG.md needs a `## x.y.z` heading")
        self.assertEqual(info["version"], first.group(1))
        self.assertEqual(info["format"], "worklog/2")
        heads = [tuple(map(int, m.split("."))) for m in re.findall(r"^## (\d+\.\d+\.\d+)", changelog, re.M)]
        for newer, older in zip(heads, heads[1:]):  # 번호 규칙: 바로 앞 항목에서 정확히 한 자리만 오른다(건너뜀 금지)
            x, y, z = older
            self.assertIn(newer, [(x + 1, 0, 0), (x, y + 1, 0), (x, y, z + 1)], f"{older} → {newer}")


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
        r, out = run(self.root, "hook")  # 미연결 폴더: NOT_CONNECTED 한 줄(2.21.0)
        self.assertEqual(r, 0)
        self.assertIn("| NOT_CONNECTED |", json.loads(out)["hookSpecificOutput"]["additionalContext"])
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

    def test_save_rejects_same_session_repeat(self):
        """같은 세션이 직전 사건과 같은 type·summary로 다시 저장하면 거부(되감기 뒤 재저장). 다른 세션이나 다른 summary는 허용."""
        self.start(session="a")
        self.assertEqual(run(self.root, "save", {"type": "CHECKPOINT", "summary": "결정 2 저장"}, session="a")[0], 0)
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": " 결정 2  저장 "}, session="a")  # 공백 차이는 같은 글자
        self.assertEqual(r, 2, out)
        self.assertIn("직전 사건 E0001와 같은 세션·같은 summary", json.loads(out)["error"])
        self.assertIn("skip", json.loads(out)["error"])
        self.assertEqual(run(self.root, "save", {"type": "RESULT", "summary": "결정 2 저장"}, session="a")[0], 0)  # type이 다르면 허용
        self.assertEqual(run(self.root, "save", {"type": "RESULT", "summary": "결정 3 저장"}, session="a")[0], 0)
        r, out = use(self.root, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        self.assertEqual(run(self.root, "save", {"type": "RESULT", "summary": "결정 3 저장"}, session="b", tool="claude")[0], 0)  # 다른 세션은 허용
        self.assertEqual(len((self.wd / "events.jsonl").read_text().splitlines()), 4)

    def test_worktree_warning(self):
        """루트의 .git이 파일(git worktree)이면 SessionStart 주입·save·skip·verify·use에 경고, 폴더면 없음."""
        self.start()
        (self.root / ".git").mkdir()
        r, out = hook(self.root, "hook")
        self.assertNotIn("worktree", out)
        self.assertNotIn("warning_worktree", run(self.root, "skip", extra=["읽기 전용"])[1])
        (self.root / ".git").rmdir()
        (self.root / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")
        r, out = hook(self.root, "hook")
        self.assertEqual(r, 0, out)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[Worklog worktree 경고] git worktree 안입니다", ctx.split("## ")[0])  # head(주입 본문 앞)에 붙는다
        r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "w"})
        self.assertEqual(r, 0, out)
        self.assertIn("events.jsonl이 충돌", json.loads(out)["warning_worktree"])
        self.assertIn("warning_worktree", run(self.root, "skip", extra=["읽기 전용"])[1])
        self.assertIn("warning_worktree", json.loads(run(self.root, "verify", extra=["--all"])[1])["hooks"])
        self.assertIn("[Worklog worktree 경고]", use(self.root, session="b", tool="pi")[1])
        self.assertIn("warning_worktree", run(self.root, "skip", session="b", tool="pi", extra=["읽기 전용"])[1])

    def test_artifacts_missing_same_session_only(self):
        """이 세션이 기록한 산출물의 파일이 없으면 show·use·주입·save·skip에 표시. 다른 세션에는 없음. state.md에는 안 들어감.
        2.27.0 (U12 A): 같은 path(Eid)는 세션당 한 번만 보인다 — 경로마다 처음 보는 출력 하나에만 나온다."""
        self.start(session="a")
        names = ("a.md", "k.md", "v.md", "h.md")
        for n in names:
            (self.root / n).write_text("본문 한 줄 " + n)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": n} for n in names]}, session="a")
        self.assertEqual(r, 0, out)
        self.assertNotIn("artifacts_missing", out)
        (self.root / "a.md").unlink()
        self.assertIn("[Worklog 산출물 없음] 이 세션이 기록한 산출물이 실제 파일에 없다: a.md(E0001)", run(self.root, "show", session="a")[1])
        (self.root / "k.md").unlink()
        self.assertEqual(json.loads(run(self.root, "skip", session="a", extra=["읽기 전용"])[1])["artifacts_missing"], ["k.md(E0001)"])
        (self.root / "v.md").unlink()
        out = json.loads(run(self.root, "save", {"type": "CHECKPOINT", "summary": "c"}, session="a")[1])
        self.assertEqual(out["artifacts_missing"], ["v.md(E0001)"])
        (self.root / "h.md").unlink()
        ctx = json.loads(hook(self.root, "hook", session="a", tool="codex")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[Worklog 산출물 없음] 이 세션이 기록한 산출물이 실제 파일에 없다: h.md(E0001).", ctx)
        self.assertNotIn("산출물 없음", run(self.root, "show", session="a")[1])          # 이미 알린 것은 다시 보이지 않는다
        self.assertNotIn("artifacts_missing", run(self.root, "skip", session="a", extra=["읽기 전용"])[1])
        self.assertNotIn("산출물 없음", (self.wd / "state.md").read_text())  # 출력에만 붙고 투영에는 없다
        self.assertTrue(json.loads(run(self.root, "verify", extra=["--all"], session="a")[1])["ok"])
        r, out = use(self.root, session="b", tool="claude")
        self.assertEqual(r, 0, out)
        self.assertNotIn("산출물 없음", out)  # 다른 세션이 기록한 산출물은 잔소리하지 않는다
        self.assertNotIn("artifacts_missing", run(self.root, "skip", session="b", tool="claude", extra=["읽기 전용"])[1])
        (self.root / "a.md").write_text("복구")
        self.assertNotIn("산출물 없음", run(self.root, "show", session="a")[1])

    def test_verify_artifacts(self):
        """verify는 모든 산출물의 존재·해시를 대조해 artifacts에 보고하고 ok에는 반영하지 않는다."""
        self.start()
        for n in ("x.md", "y.md", "z.md"):
            (self.root / n).write_text(n)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": n} for n in ("x.md", "y.md", "z.md")]})
        self.assertEqual(r, 0, out)
        (self.root / "x.md").unlink()
        (self.root / "y.md").write_text("바뀜")
        r, out = run(self.root, "verify", extra=["--all"])
        self.assertEqual(r, 0, out)
        self.assertEqual(json.loads(out)["works"][0]["artifacts"], {"missing": ["x.md(E0001)"], "changed": 1, "checked": 3})
        self.assertEqual(json.loads(run(self.root, "verify", extra=["--work", "t"])[1])["artifacts"]["missing"], ["x.md(E0001)"])

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
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "s2", "artifacts": arts,
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
        self.assertEqual((r, json.loads(out)), (0, {"ok": True, "turn": 4,  # 통과한 Stop 2회가 턴을 넘겼다(2.16.0). 이 세션에서 돈 Hook: turn-start·stop-hook
                                                    "hooks": {"session_start": False, "turn_start": True, "stop": True}}))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(len((self.wd / "events.jsonl").read_text().splitlines()), 2)  # skip은 원장에 안 씀
        self.assertEqual(json.loads(hook(self.root, "stop-hook", session="other")[1] or "{}"), {})  # 턴 시작 없는 세션은 통과

    def test_hooks_silent_without_worklog(self):
        """2.21.0: SessionStart says NOT_CONNECTED in one line (root = the event's cwd); turn-start·stop-hook stay silent.
        2.25.0: the header also carries auto= and git=; with auto=on the line says to connect on the first request worth recording."""
        r, out = hook(self.root, "hook")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual((r, ctx.count("\n")), (0, 1))
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NOT_CONNECTED | root={self.root.resolve()} | auto=on | git=no] "), ctx)
        self.assertIn(f'new-work "<제목>" --quote "<요청 원문>" --root {self.root.resolve()}', ctx)
        for cmd in ("turn-start", "stop-hook"):
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
        manifest = json.loads((self.root / ".worklog/install.json").read_text())["claude"]  # 2단계: 설치 원본 해시 기록
        self.assertEqual(manifest["rules_src_sha"], hashlib.sha256((inst.parents[1] / "adapters/rules.md").read_bytes()).hexdigest())
        self.assertEqual(manifest["version"], json.loads(run(self.root, "version")[1])["version"])
        self.assertNotIn("warning_install", json.loads(run(self.root, "skip", extra=("x",), session="x", tool="claude")[1]))
        backups = list(self.root.glob("CLAUDE.md.bak-worklog-*"))
        self.assertEqual(len(backups), 1)  # 날짜·시각 붙은 백업, 두 번째 실행은 변경 없음
        self.assertEqual(backups[0].read_text(), "# 기존 내용\n")

    def test_installer_gitignore_in_git_project(self):
        """2.18.0: git 프로젝트면 .gitignore에 `.worklog/`를 더하고(2.11.0~2.17.x의 sessions/·.lock 줄은 치움), 이미 무시 중이거나 git 아닌 폴더는 건드리지 않는다."""
        inst = INST
        run_inst = lambda: subprocess.run([sys.executable, "-B", str(inst), "--tool", "claude", "--root", str(self.root)], check=True, capture_output=True)
        run_inst()
        self.assertFalse((self.root / ".gitignore").exists())  # git 저장소가 아니면 만들지 않는다
        (self.root / ".git").mkdir()
        (self.root / ".gitignore").write_text("node_modules/\n.worklog/.lock\n.worklog/sessions/\n")  # 옛 설치본
        run_inst()
        text = (self.root / ".gitignore").read_text()
        self.assertEqual(text, "node_modules/\n.worklog/\n")  # 옛 두 줄은 빠지고 전체 무시 한 줄
        self.assertEqual(len(list(self.root.glob(".gitignore.bak-worklog-*"))), 1)  # 기존 파일은 백업
        run_inst()
        self.assertEqual((self.root / ".gitignore").read_text(), text)  # 두 번째 실행은 변경 없음
        self.assertEqual(len(list(self.root.glob(".gitignore.bak-worklog-*"))), 1)
        subprocess.run([sys.executable, "-B", str(inst), "--tool", "claude", "--root", str(self.root), "--no-worklog-dir"], check=True, capture_output=True)
        self.assertEqual((self.root / ".gitignore").read_text(), text)  # 상위 폴더 설치는 .gitignore를 건드리지 않는다
        (self.root / ".gitignore").write_text("/.worklog\n")  # 사용자가 이미 다른 표기로 무시 중
        run_inst()
        self.assertEqual((self.root / ".gitignore").read_text(), "/.worklog\n")
        (self.root / ".gitignore").unlink()
        run_inst()
        self.assertEqual((self.root / ".gitignore").read_text(), ".worklog/\n")  # 없으면 새로 만든다

    # --- 배포 전 검토 회귀 시험 ---
    def install(self, *extra, inst=INST):
        p = subprocess.run([sys.executable, "-B", str(inst), "--tool", "claude", "--root", str(self.root), *extra],
                           capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_installer_rolls_back_on_write_failure(self):
        """2.22.0: an OS error in the middle of the writes restores the files written so far (backup → file, new file
        deleted, backup removed), creates no .worklog, registers nothing, and exits 2 with `rolled_back`."""
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        (self.root / ".claude" / "skills").mkdir(parents=True)
        (self.root / ".claude" / "skills" / "worklog").write_text("not a directory")  # SKILL.md의 부모가 파일 → 세 번째 쓰기에서 OS 오류
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        r, out = self.install()
        self.assertEqual(r, 2, out)
        d = json.loads(out)
        self.assertIn("되돌렸습니다", d["error"])
        self.assertEqual(sorted(Path(p).name for p in d["rolled_back"]), ["CLAUDE.md", "settings.local.json"])
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 기존 내용\n")
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)  # 백업·새 파일·.worklog 없음
        self.assertFalse((TEST_HOME / "installs.json").exists() and str(self.root.resolve()) in (TEST_HOME / "installs.json").read_text())

    def test_installer_refuses_link_outside_root(self):
        outside = Path(tempfile.mkdtemp()) / "outside.md"
        outside.write_text("밖의 파일\n")
        (self.root / "CLAUDE.md").symlink_to(outside)
        r, out = self.install()
        self.assertEqual(r, 2, out)
        self.assertIn("밖을 가리키는 링크", json.loads(out)["error"])
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

    def test_installer_keeps_equivalent_hooks_unchanged(self):
        """같은 설치의 Hook은 인용 형식이 달라도 그대로 둔다(파일 바이트 유지 → Codex Hook 재신뢰 불필요)."""
        wl = str(INST.parents[1] / "core" / "wl.py")

        def group(cmd, matcher=None):
            g = {"hooks": [{"type": "command", "command": f'python3 -B "{wl}" {cmd} --tool claude', "timeout": 10}]}
            if matcher:
                g["matcher"] = matcher
            return g
        sp = self.root / ".claude/settings.local.json"
        sp.parent.mkdir()
        text = json.dumps({"hooks": {"SessionStart": [group("hook", "startup|resume|clear|compact|fork")],
                                     "UserPromptSubmit": [group("turn-start")], "Stop": [group("stop-hook")]}},
                          ensure_ascii=False, indent=2) + "\n"
        sp.write_bytes(text.encode())
        r, out = self.install()
        self.assertEqual(r, 0, out)
        self.assertEqual(sp.read_bytes(), text.encode())
        self.assertNotIn(str(sp), json.loads(out)["changed"])

    def test_installer_refuses_backup_link(self):
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        outside = Path(tempfile.mkdtemp()) / "backup-outside.md"
        outside.write_text("Outside unchanged\n")
        (self.root / "CLAUDE.md.bak-worklog-20300102-030405").symlink_to(outside)
        r, out = self.install_at("20300102-030405")
        self.assertEqual(r, 2, out)
        self.assertIn("밖을 가리키는 링크", json.loads(out)["error"])
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

    def test_state_md_map_section(self):
        """2.23.0: `Map:`으로 시작하는 유효 결정은 state.md의 `## 안내` 절(유효 결정 앞)에도 보이고 목록에도 남는다. 없으면 절도 없고,
        `현재 범위`는 Map이 아닌 마지막 결정이며, 대체된 Map 결정은 절에서 사라진다."""
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "조건", "quote": "q", "decisions": [{"text": "저녁 11분"}]})
        md = (self.wd / "state.md").read_text()
        self.assertNotIn("## 안내", md)  # ② Map 결정이 없으면 절이 없다
        self.assertIn("현재 범위(최신 결정): D1: 저녁 11분\n", md)
        r, out = run(self.root, "save", {"type": "D_USER", "summary": "기준 문서", "quote": "spec 먼저 봐",
                                         "decisions": [{"text": "Map: docs/spec.md §3을 먼저 본다"}]})
        self.assertEqual(r, 0, out)
        md = (self.wd / "state.md").read_text()
        guide, valid = md.index("## 안내 — 먼저 볼 것(Map: 결정)"), md.index("## 유효 결정")
        self.assertLess(guide, valid)  # ① 절이 생기고 유효 결정보다 앞
        self.assertEqual(md.count("- D2: Map: docs/spec.md §3을 먼저 본다 [사용자]"), 2)  # ① 안내 절 + 결정 목록
        self.assertEqual(md.count("- D1: 저녁 11분"), 1)
        self.assertIn("현재 범위(최신 결정): D1: 저녁 11분\n", md)  # ③ 마지막 결정이 Map이어도 현재 범위는 그 앞의 비Map 결정
        self.assertEqual(run(self.root, "verify")[0], 0)  # 재계산해도 같은 투영
        run(self.root, "save", {"type": "D_USER", "summary": "변경", "quote": "spec 말고 readme",
                                "decisions": [{"text": "Map: README.md를 먼저 본다", "replaces": "D2"}]})
        md = (self.wd / "state.md").read_text()
        self.assertIn("- D3: Map: README.md를 먼저 본다 (대체: D2) [사용자]", md.split("## 유효 결정")[0])  # ④ 대체된 D2는 절에서 사라진다
        self.assertNotIn("docs/spec.md", md)
        run(self.root, "save", {"type": "D_USER", "summary": "시간 결정 철회", "quote": "11분은 없던 걸로",
                                "decisions": [{"text": "Map: 시간은 docs/plan.md를 따른다", "replaces": "D1"}]})
        md = (self.wd / "state.md").read_text()
        self.assertNotIn("현재 범위", md)  # Map 결정만 남으면 현재 범위 줄을 생략한다
        self.assertEqual(run(self.root, "verify")[0], 0)

    def test_unseen_events_section(self):
        """2.23.0: show·use·SessionStart 주입은 이 세션의 last_seen 뒤 사건을 '못 본 사건' 절로 붙인 뒤 본 것으로 표시한다.
        자기 사건은 들어가지 않고, 없으면 절도 없으며, 세션을 모르는 호출에는 절이 없다."""
        self.start()
        run(self.root, "save", {"type": "REQUEST", "summary": "첫째", "quote": "q"})
        run(self.root, "save", {"type": "RESULT", "summary": "둘째 " + "가" * 100})
        r, out = use(self.root, session="s2")  # ① 다른 세션이 처음 읽으면 두 사건이 절에 보인다
        self.assertEqual(r, 0, out)
        sect = out.split("## 이 세션이 아직 못 본 사건 (seq 1~2)")[1]
        self.assertIn("- E0001 · codex:s1 · REQUEST · 첫째\n", sect)
        self.assertIn("- E0002 · codex:s1 · RESULT · 둘째 " + "가" * 77 + "…\n", sect)
        self.assertNotIn("못 본 사건", run(self.root, "show", session="s2")[1])  # ② 바로 다시 보면 절이 없다
        run(self.root, "save", {"type": "RESULT", "summary": "셋째"}, session="s2")
        self.assertNotIn("못 본 사건", run(self.root, "show", session="s2")[1])  # 자기 사건은 들어가지 않는다
        r, out = run(self.root, "show")  # ③ s1에는 s2의 한 건만
        self.assertIn("## 이 세션이 아직 못 본 사건 (seq 3~3)\n- E0003 · codex:s2 · RESULT · 셋째\n", out)
        self.assertNotIn("E0001 ·", out.split("못 본 사건")[1])
        self.assertNotIn("못 본 사건", run(self.root, "show")[1])
        run(self.root, "save", {"type": "RESULT", "summary": "넷째"}, session="s2")
        self.assertNotIn("못 본 사건", run(self.root, "show", session="", tool="", extra=["--work", "t"])[1])  # ④ 세션 없는 호출
        r, out = hook(self.root, "hook", session="s1", tool="codex")  # ⑤ 주입에도 같은 절
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("## 이 세션이 아직 못 본 사건 (seq 4~4)\n- E0004 · codex:s2 · RESULT · 넷째", ctx)
        self.assertNotIn("못 본 사건", run(self.root, "show")[1])  # 주입이 본 것으로 표시했다

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


class InstallWarningTest(Base):
    """2단계: .worklog/install.json의 rules_src_sha가 코어의 adapters/rules.md와 다르면 경고만 붙는다."""
    def manifest(self, sha, tool="codex", version="2.1.0"):
        (self.d / "install.json").write_text(json.dumps({tool: {"version": version, "rules_src_sha": sha, "installed_at": "x"}}))

    def test_install_warning_on_stale_copy(self):
        self.ok(new_work(self.root, "t"))
        self.manifest("0" * 64)
        out = self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}))
        self.assertIn("설치 당시(v2.1.0)", out["warning_install"])
        self.assertIn("install_project.py", out["warning_install"])
        self.assertIn("warning_install", self.ok(run(self.root, "skip", extra=("이유",))))
        self.assertIn("warning_install", self.ok(run(self.root, "verify", extra=("--all",)))["hooks"])
        self.assertIn("[Worklog 사본 경고]", self.used(run(self.root, "use", extra=("t", "--quote", "t 이어서")), "t"))
        self.assertIn("[Worklog 사본 경고]", self.ctx(tool="codex"))
        self.assertNotIn("[Worklog 사본 경고]", self.ctx(tool="claude"))  # 다른 도구의 항목은 보지 않는다

    def test_install_warning_absent_without_manifest(self):
        self.ok(new_work(self.root, "t"))
        payload = {"type": "REQUEST", "summary": "x", "quote": "q"}
        self.assertNotIn("warning_install", self.ok(run(self.root, "save", payload)))  # 파일 없음
        (self.d / "install.json").write_text("{not json")
        payload["summary"] = "x2"  # 같은 세션의 같은 summary 재저장은 2.13.0부터 거부
        self.assertNotIn("warning_install", self.ok(run(self.root, "save", payload)))  # 깨진 JSON
        (self.d / "install.json").write_text(json.dumps({"codex": "oops"}))
        payload["summary"] = "x3"
        self.assertNotIn("warning_install", self.ok(run(self.root, "save", payload)))  # 항목이 객체가 아님
        current = hashlib.sha256((WL.parents[1] / "adapters" / "rules.md").read_bytes()).hexdigest()
        self.manifest(current)
        payload["summary"] = "x4"
        self.assertNotIn("warning_install", self.ok(run(self.root, "save", payload)))  # 같은 해시
        self.assertNotIn("사본 경고", self.ctx(tool="codex"))

    def test_strip_source_tags_in_text(self):
        """F6: 글자로 적힌 [사용자]/[모델]은 지우고 코어가 출처를 붙인다."""
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q",
                                        "decisions": [{"text": "[사용자] 11분"}, {"text": "3·5·3분 [모델]", "source": "model"}],
                                        "constraints": ["[모델] 게시 금지 [모델]"]}))
        st = json.loads((self.d / "works/t/state.json").read_text())
        self.assertEqual([(x["text"], x["source"]) for x in st["decisions"]], [("11분", "user"), ("3·5·3분", "model")])
        self.assertEqual([(x["text"], x["source"]) for x in st["constraints"]], [("게시 금지", "user")])
        md = (self.d / "works/t/state.md").read_text()
        self.assertIn("- D1: 11분 [사용자]", md)
        self.assertIn("- C1: 게시 금지 [사용자]", md)
        self.refused(run(self.root, "save", {"type": "RESULT", "summary": "y", "decisions": [{"text": "[모델]"}]}), "비어 있습니다")


class CoreWarningTest(Base):
    """3단계 ①: 사건에 쓴 코어 번호가 남고, 더 새 코어가 쓴 사건을 보면 show·use·save·verify에 경고만 붙는다."""
    def rewrite_last_core(self, value):
        """마지막 사건의 core만 바꾼다(마지막 줄이라 다음 prev가 없어 연결은 그대로)."""
        path = self.d / "works/t/events.jsonl"
        lines = path.read_bytes().splitlines()
        ev = json.loads(lines[-1])
        ev.pop("core", None)
        if value is not None:
            ev["core"] = value
        lines[-1] = json.dumps(ev, ensure_ascii=False, separators=(",", ":")).encode()
        path.write_bytes(b"\n".join(lines) + b"\n")

    def test_core_warning_on_newer_event(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}))
        ev = json.loads((self.d / "works/t/events.jsonl").read_bytes().splitlines()[-1])
        self.assertEqual(ev["core"], json.loads(run(self.root, "version")[1])["version"])
        major, minor, _ = (int(x) for x in ev["core"].split("."))
        newer = f"{major}.{minor + 1}.0"  # 현재 코어보다 부 번호가 하나 큰 값(2.9.0 → 2.10.0처럼 자릿수가 늘어도 숫자 비교라 더 크다)
        self.rewrite_last_core(newer)
        msg = f"[Worklog 코어 경고] 이 기록은 코어 {newer}이 썼습니다"
        self.assertIn(msg, run(self.root, "show")[1])
        self.assertIn(msg, self.used(use(self.root, "t"), "t"))
        one = self.ok(run(self.root, "verify"))
        self.assertTrue(one["ok"])  # 경고일 뿐 원장·투영은 정상
        self.assertIn(f"코어 {newer}", one["warning_core"])
        self.assertIn("warning_core", self.ok(run(self.root, "verify", extra=("--all",)))["works"][0])
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "y"}))
        self.assertIn("코어를 갱신하세요", out["warning_core"])

    def test_core_warning_absent_for_old_or_equal_events(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}))
        x, y, z = map(int, load_wl().VERSION.split("."))
        for value in (None, "2.0.0", "garbage", f"{x}.{y}.{z + 1}"):  # core 없음(옛 사건)·더 낮음·해석 불가·끝 번호만 더 큼
            self.rewrite_last_core(value)
            self.assertNotIn("코어 경고", run(self.root, "show")[1], value)
            self.assertNotIn("warning_core", self.ok(run(self.root, "verify")), value)
        self.assertNotIn("warning_core", self.ok(run(self.root, "save", {"type": "RESULT", "summary": "y"})))


class UpdateTest(Base):
    """4단계: 갱신은 사용자가 치는 tools/update.py만 한다(같은 주 번호의 tag로 fast-forward). 배경은 fetch·캐시만, Hook은 캐시만 읽는다."""
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {"WL_HOME": str(self.home)}

    def home_write(self, name, value):
        (self.home / name).write_text(json.dumps(value))

    def git(self, repo, *args):
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                           env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t",
                                    GIT_COMMITTER_EMAIL="t@x", GIT_TERMINAL_PROMPT="0"))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def make_upstream(self):
        """origin with tags v<current>, v<next minor>, v<next major>, and a clone reset to v<current>."""
        up, src, cur = self.root / "upstream", WL.parents[1], load_wl().VERSION
        for rel in ("core/wl.py", "tools/update.py", "tools/install_project.py", "adapters/rules.md", "CHANGELOG.md"):
            (up / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src / rel, up / rel)
        self.git(up, "init", "-q", "-b", "master")
        self.git(up, "add", "-A")
        self.git(up, "commit", "-q", "-m", "base")
        self.git(up, "tag", f"v{cur}")
        major, minor, _ = map(int, cur.split("."))
        prev, versions = cur, (f"{major}.{minor + 1}.0", f"{major + 1}.0.0")
        for v in versions:
            core = up / "core/wl.py"
            core.write_text(core.read_text().replace(f'VERSION = "{prev}"', f'VERSION = "{v}"'))
            self.git(up, "commit", "-qam", v)
            self.git(up, "tag", f"v{v}")
            prev = v
        clone = self.root / "clone"
        self.git(self.root, "clone", "-q", str(up), str(clone))
        self.git(clone, "reset", "-q", "--hard", f"v{cur}")
        return clone, cur, versions[0], versions[1]

    def update(self, clone, *args):
        p = subprocess.run([sys.executable, "-B", str(clone / "tools/update.py"), *args], capture_output=True, text=True,
                           env=dict(os.environ, WL_HOME=str(self.home)))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_check_apply_rollback_in_clone(self):
        clone, cur, minor, major = self.make_upstream()
        c = self.update(clone, "check")
        self.assertEqual((c["mode"], c["current"], c["latest"], c["latest_major"], c["error"]), ("notify", cur, minor, major, None))
        p = subprocess.run([sys.executable, "-B", str(clone / "tools/update.py"), "background"], capture_output=True, text=True,
                           env=dict(os.environ, WL_HOME=str(self.home)))  # 배경 실행은 캐시만 쓰고 아무것도 적용하지 않는다
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertEqual(json.loads((self.home / "update.json").read_text())["latest"], minor)
        self.assertEqual(json.loads(subprocess.run([sys.executable, "-B", str(clone / "core/wl.py"), "version"],
                                                   capture_output=True, text=True).stdout)["version"], cur)
        c = self.update(clone, "apply")
        self.assertEqual((c["current"], c["applied"]["from"], c["applied"]["to"], c["latest"], c["error"]), (minor, cur, minor, None, None))
        out = subprocess.run([sys.executable, "-B", str(clone / "core/wl.py"), "version"], capture_output=True, text=True).stdout
        self.assertEqual(json.loads(out)["version"], minor)
        self.assertEqual(self.git(clone, "branch", "--show-current"), "master")  # fast-forward keeps the user's branch
        c = self.update(clone, "rollback")
        self.assertEqual((c["current"], c["applied"], c["previous"], c["error"]), (cur, None, None, None))
        (clone / "core/wl.py").write_text((clone / "core/wl.py").read_text() + "\n# local change\n")
        c = self.update(clone, "apply")  # 커밋되지 않은 변경: 적용하지 않고 이유만 남긴다
        self.assertIn("커밋되지 않은 변경", c["error"])
        self.assertEqual(c["current"], cur)

    def test_mode_setting_and_plain_copy(self):
        clone, cur, minor, major = self.make_upstream()
        c = self.update(clone, "check", "--mode", "off")
        self.assertEqual((c["mode"], json.loads((self.home / "config.json").read_text())["update"]), ("off", "off"))
        shutil.rmtree(clone / ".git")  # 복사본(shared 폴더처럼 .git 없음): 갱신 대상이 아니다
        self.assertIn("git 저장소가 아니다", self.update(clone, "check")["error"])

    def test_session_start_reads_cache_only(self):
        self.ok(new_work(self.root, "t"))
        wl = load_wl()
        self.home_write("config.json", {"update": "notify"})
        self.home_write("update.json", {"checked_at": wl.now(), "latest": "9.9.0", "current": wl.VERSION})
        ctx = self.ctx(tool="codex", env=self.env)
        self.assertIn("[Worklog 갱신 안내] 새 버전 v9.9.0", ctx)
        self.assertIn("wl.py update", ctx.split("\n")[2])
        self.home_write("update.json", {"checked_at": wl.now(), "latest_major": "10.0.0", "current": wl.VERSION})
        self.assertIn("새 주 버전 v10.0.0", self.ctx(tool="codex", env=self.env))
        self.home_write("update.json", {"checked_at": wl.now(), "applied": {"from": "0.0.1", "to": wl.VERSION, "at": wl.now()}})
        self.assertIn(f"[Worklog 갱신] 코어를 v0.0.1에서 v{wl.VERSION}으로", self.ctx(tool="codex", env=self.env))
        self.home_write("update.json", {"checked_at": wl.now(), "latest": "9.9.0", "error": "git fetch 실패: x"})
        self.assertIn("[Worklog 갱신 실패] v9.9.0", self.ctx(tool="codex", env=self.env))
        stamp = wl.now()
        self.home_write("update.json", {"checked_at": stamp, "latest": "9.9.0"})
        self.ctx(tool="codex", env=self.env)  # 최근 검사가 있으면 배경 검사를 띄우지 않는다(checked_at 불변)
        self.assertEqual(json.loads((self.home / "update.json").read_text())["checked_at"], stamp)
        self.home_write("config.json", {"update": "off"})
        self.assertNotIn("Worklog 갱신", self.ctx(tool="codex", env=self.env))

    def test_stale_copy_is_only_warned_about(self):
        """세션 시작은 규칙 사본을 고쳐 쓰지 않는다: 사본 경고 줄만, install.json 불변."""
        subprocess.run([sys.executable, "-B", str(WL.parents[1] / "tools/install_project.py"), "--tool", "codex", "--root", str(self.root)],
                       capture_output=True, text=True, check=True)
        stale = {"codex": {"version": "0.0.1", "rules_src_sha": "0" * 64, "installed_at": "x"}}
        (self.d / "install.json").write_text(json.dumps(stale))
        self.home_write("config.json", {"update": "notify"})
        self.home_write("update.json", {"checked_at": load_wl().now()})
        ctx = self.ctx(tool="codex", env=self.env)
        self.assertIn("[Worklog 사본 경고]", ctx)
        self.assertNotIn("규칙 갱신", ctx)
        self.assertEqual(json.loads((self.d / "install.json").read_text()), stale)


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
        self.assertIn("/ 전체 0개)\n- (없음)\n## 현재 작업 없음\n기존 작업이 없다. 첫 기록 대상 요청에서 묻지 않고 new-work로", ctx)  # 2.25.0 auto=on
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
        fresh = json.loads(session_file(self.root, "claude_fresh").read_text())  # Hook 작동 기록만 남기고 현재 작업은 없음
        self.assertEqual((fresh["current_work"], sorted(fresh["hooks_seen"])), (None, ["SessionStart"]))
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
        self.assertEqual(json.loads(session_file(self.root).read_text())["selected_turn"], 3)  # 통과한 Stop이 턴을 넘기므로 둘째 선택은 턴 3

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
        self.assertLessEqual({"ok", "id", "title", "current_work"}, set(self.ok(new_work(self.root, "B", session="y"))))

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


class OnOffTest(Base):
    """프로젝트 단위 on/off: .worklog/off 표식. 원장·index·세션 파일 구조는 그대로."""
    def off(self, *extra, quote="워크로그 꺼"):
        return run(self.root, "off", extra=(["--quote", quote] if quote is not None else []) + list(extra))

    def test_off_hooks_do_nothing_and_inject_one_line(self):
        self.ok(new_work(self.root, "Habit Plan", tool="claude"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "h", "quote": "q"}, tool="claude"))
        hook(self.root, "turn-start")  # 끄는 턴: 아직 저장 없음
        out = self.ok(self.off("--reason", "실험 중", quote="워크로그 꺼 실험 중"))
        self.assertEqual((out["off"], out["reason"]), (True, "실험 중"))
        marker = json.loads((self.d / "off").read_text())
        self.assertEqual(marker, {"at": marker["at"], "reason": "실험 중", "by": "codex:s1", "quote": "워크로그 꺼 실험 중"})
        before = self.snapshot()
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))  # 끈 턴도 차단하지 않음
        self.assertEqual(hook(self.root, "turn-start"), (0, ""))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        line = (f"[Worklog worklog/2 SessionStart | OFF | root={self.root.resolve()}] Worklog가 꺼져 있다(이유: 실험 중, "
                f"시각: {marker['at']}). 사용자가 켜 달라고 하기 전까지 Worklog 절차를 적용하지 않는다.\n")
        self.assertEqual(self.ctx(), line)  # 현재 작업이 있는 세션도 한 줄
        self.assertEqual(self.ctx(session="fresh"), line)
        self.assertEqual(self.snapshot(), before)  # 세 Hook은 세션 파일을 포함해 아무것도 바꾸지 않음
        self.assertFalse(session_file(self.root, "claude_fresh").exists())

    def test_on_restores_normal_path(self):
        self.ok(new_work(self.root, "Habit Plan", tool="claude"))
        hook(self.root, "turn-start")
        self.ok(self.off())
        hook(self.root, "turn-start")  # 꺼진 동안의 턴은 세지 않음
        out = self.ok(run(self.root, "on"))
        self.assertIs(out["off"], False)
        self.assertIsInstance(out["off_seconds"], int)
        self.assertIn("꺼져 있던 기간: ", out["message"])
        self.assertIn("다음 save에 적는다", out["message"])
        self.assertFalse(os.path.lexists(self.d / "off"))
        self.assertNotIn("off", self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "h", "quote": "q"}, tool="claude")))
        self.assertIn("| PROVIDED |", self.ctx())
        hook(self.root, "turn-start")
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.assertNotIn("off", self.ok(run(self.root, "skip", extra=["읽기"], tool="claude")))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 3)  # 꺼진 동안의 turn-start 1회는 세지 않고, 통과한 Stop이 1 올림
        self.assertEqual(len((self.d / "works/habit-plan/events.jsonl").read_text().splitlines()), 1)  # off·on은 원장에 쓰지 않음

    def test_commands_work_while_off_with_warning(self):
        self.ok(new_work(self.root, "Habit Plan"))
        self.ok(self.off())  # 이유는 선택
        self.assertIsNone(json.loads((self.d / "off").read_text())["reason"])
        out = self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "h", "quote": "q"}))
        self.assertEqual((out["off"], out["seq"]), (True, 1))
        self.assertIs(self.ok(run(self.root, "skip", extra=["읽기"]))["off"], True)
        self.assertIs(self.ok(new_work(self.root, "Recipe"))["off"], True)
        self.assertIs(self.ok(run(self.root, "works"))["off"], True)
        self.assertIn("\n[Worklog OFF] ", self.used(use(self.root, "habit-plan"), "habit-plan"))
        r, out = run(self.root, "show")
        self.assertEqual(r, 0, out)
        self.assertTrue(out.startswith("[Worklog OFF] "), out)
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), [".lock", "index.json", "install.json", "off", "sessions", "works"])  # install.json: new-work가 폴더를 연결(2.21.0)

    def test_off_needs_quote(self):
        self.ok(new_work(self.root, "t"))
        self.refused(self.off("--reason", "이유", quote=None), "사용자 원문이 필요합니다")
        self.refused(self.off(quote="  "), "사용자 원문이 필요합니다")
        self.refused(run(self.root, "off", extra=["이유", "--quote", "꺼"]), "--reason")
        self.assertFalse(os.path.lexists(self.d / "off"))

    def test_not_installed_and_repeats(self):
        self.refused(self.off(), "연결되지 않은 폴더")  # 2.21.0: .worklog가 없는 폴더는 "미연결"
        self.refused(run(self.root, "on"), "연결되지 않은 폴더")
        self.assertFalse(self.d.exists())
        self.d.mkdir()
        out = self.ok(run(self.root, "on"))
        self.assertTrue(out["already"])
        self.assertIn("이미 켜져", out["message"])
        self.ok(self.off("--reason", "첫 이유"))
        first = (self.d / "off").read_bytes()
        out = self.ok(self.off("--reason", "둘째 이유"))
        self.assertEqual((out["already"], out["reason"]), (True, "첫 이유"))
        self.assertIn("이미 꺼져", out["message"])
        self.assertEqual((self.d / "off").read_bytes(), first)  # 기존 표식 유지
        self.assertNotIn("already", self.ok(run(self.root, "on")))
        self.assertTrue(self.ok(run(self.root, "on"))["already"])

    def test_marker_link_refused(self):
        self.d.mkdir()
        outside = Path(tempfile.mkdtemp()) / "x"
        outside.write_text("keep")
        (self.d / "off").symlink_to(outside)
        self.refused(self.off(), "심볼릭 링크")
        self.refused(run(self.root, "on"), "심볼릭 링크")
        self.assertEqual(outside.read_text(), "keep")
        self.assertTrue((self.d / "off").is_symlink())
        ctx = self.ctx()  # 링크는 따라가지 않고 꺼진 것으로 본다
        self.assertIn("| OFF |", ctx)
        self.assertIn("이유: 없음", ctx)


UNINST = Path(__file__).resolve().parents[1] / "tools" / "uninstall_project.py"


class UninstallTest(Base):
    """2.17.0: tools/uninstall_project.py는 설치기가 한 일을 되돌리고, 기록은 --keep-records/--delete-records로 사용자가 정한다."""

    def setUp(self):
        super().setUp()
        self.home = Path(tempfile.mkdtemp())  # 이 시험만의 WL_HOME: registry가 다른 시험의 프로젝트와 섞이지 않게
        (self.home / "config.json").write_text('{"update": "off"}')
        self.env = dict(clean_env(), WL_HOME=str(self.home))
        self.root.joinpath(".git").mkdir()  # git 프로젝트: .gitignore 줄까지 설치된다
        (self.root / "CLAUDE.md").write_text("# 기존 내용\n")
        (self.root / ".gitignore").write_text("node_modules/\n")
        (self.root / ".claude").mkdir()
        self.other_hook = {"type": "command", "command": "echo other", "timeout": 5}
        (self.root / ".claude/settings.local.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [self.other_hook]}]}}))

    def install(self, tool):
        p = subprocess.run([sys.executable, "-B", str(INST), "--tool", tool, "--root", str(self.root)], capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def uninstall(self, *extra, root=True):
        argv = [sys.executable, "-B", str(UNINST), *(["--root", str(self.root)] if root else []), *extra]
        p = subprocess.run(argv, capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertIn(p.returncode, (0, 2), p.stderr)
        return p.returncode, json.loads(p.stdout)

    def registry(self):
        try:
            return json.loads((self.home / "installs.json").read_text())
        except FileNotFoundError:
            return None

    def names(self, folder):
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else None

    def test_installer_refuses_without_tool_and_reports_detected(self):
        """2.19.0: --tool이 없으면 아무것도 쓰지 않고, 사용자에게 물으라는 메시지와 이 기기의 도구(~/.claude·~/.codex)를 알린다."""
        home = Path(tempfile.mkdtemp())
        (home / ".codex").mkdir()
        before = sorted(p.name for p in self.root.rglob("*"))
        p = subprocess.run([sys.executable, "-B", str(INST), "--root", str(self.root)], capture_output=True, text=True,
                           env=dict(self.env, HOME=str(home)))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        err = json.loads(p.stdout)["error"]
        self.assertIn("어느 도구에 설치할지", err)
        self.assertIn("claude=없음, codex=있음", err)
        self.assertEqual(sorted(p.name for p in self.root.rglob("*")), before)
        self.assertFalse((home / ".worklog").exists())  # registry도 안 쓴다

    def test_uninstaller_requires_tool_and_lists_installed(self):
        """2.19.0: --root만 주면 아무것도 쓰지 않고 설치된 도구를 알린다. --all-projects는 all."""
        self.install("claude")
        self.install("codex")
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        code, out = self.uninstall("--keep-records")
        self.assertEqual(code, 2)
        self.assertIn("어느 도구를 제거할지", out["projects"][0]["error"])
        self.assertIn("설치됨: claude, codex", out["projects"][0]["error"])
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)
        code, out = self.uninstall("--tool", "codex")  # 다른 도구가 남으면 기록 선택 불필요
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(json.loads((self.d / "install.json").read_text())), ["claude"])  # claude 설치는 그대로
        self.assertIn("worklog-shared:begin", (self.root / "CLAUDE.md").read_text())
        code, out = self.uninstall("--tool", "claude")  # 마지막 도구: 기록 선택 필수
        self.assertEqual(code, 2)
        self.assertIn("--keep-records 또는 --delete-records", out["projects"][0]["error"])
        code, out = self.uninstall("--all-projects", "--keep-records", root=False)  # --all-projects = 모든 도구
        self.assertEqual((code, out["projects"][0]["tool"]), (0, "all"))
        self.assertNotIn("worklog-shared:begin", (self.root / "CLAUDE.md").read_text())

    def test_all_keep_records_removes_manifest_with_two_tools(self):
        """2.20.0: 두 도구 설치 + --tool all --keep-records → install.json이 둘째 도구 항목을 남기지 않고 사라진다(M-uninstall 발견)."""
        self.install("claude")
        self.install("codex")
        code, out = self.uninstall("--tool", "all", "--keep-records")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.d / "install.json").exists())
        self.assertFalse(self.d.exists())  # 기록이 없으니 빈 .worklog 폴더도 정리된다
        self.assertIn(str(self.d.resolve() / "install.json"), out["projects"][0]["removed"])  # 출력은 resolve된 경로(/private/var…)

    def test_installer_writes_registry(self):
        self.assertEqual(self.install("claude")["registry"], str(self.home / "installs.json"))
        self.install("codex")
        self.install("claude")  # 두 번 설치해도 한 번만 적힌다
        self.assertEqual(self.registry(), {str(self.root.resolve()): ["claude", "codex"]})

    def test_keep_records_then_reinstall_continues(self):
        self.install("claude")
        self.ok(new_work(self.root, "Habit Plan", tool="claude"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude"))
        hook(self.root, "stop-hook", env={"WL_HOME": str(self.home)})
        self.assertTrue((self.d / ".lock").exists() and session_file(self.root).exists())
        code, out = self.uninstall("--tool", "all", "--keep-records", "--dry-run")
        self.assertEqual((code, out["dry_run"]), (0, True))
        self.assertIn("worklog-shared:begin", (self.root / "CLAUDE.md").read_text())  # dry-run은 아무것도 안 바꾼다
        code, out = self.uninstall("--tool", "all", "--keep-records")
        self.assertEqual(code, 0, out)
        p = out["projects"][0]
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 기존 내용\n")  # 블록만 빠지고 원래 내용은 그대로
        settings = json.loads((self.root / ".claude/settings.local.json").read_text())
        self.assertEqual(settings, {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [self.other_hook]}]}})  # 남의 Hook·설정 유지
        self.assertFalse((self.root / ".claude/skills").exists())  # 스킬 파일과 빈 폴더 제거
        self.assertEqual((self.root / ".gitignore").read_text(), "node_modules/\n.worklog/\n")  # 2.21.0: 기록을 남기면 .gitignore 줄도 남긴다(기록이 커밋되지 않게)
        self.assertEqual(self.names(self.d), ["index.json", "works"])  # 기록은 남고 세션·잠금·설치 정보는 사라진다
        self.assertIn("여전히 연결된 폴더", p["notes"][0])
        self.assertEqual(sorted(Path(b).name.split(".bak-worklog-")[0] for b in p["backups"]), ["CLAUDE.md", "settings.local.json"])
        self.assertTrue(all(Path(b).exists() for b in p["backups"]))
        self.assertTrue(any(Path(b).read_text().count("worklog-shared:begin") == 1 for b in p["backups"]))  # 백업은 제거 전 내용
        self.assertIsNone(self.registry())
        self.assertTrue(len(list(self.root.glob("CLAUDE.md.bak-worklog-*"))) >= 2)  # 설치기의 옛 백업은 그대로(--purge-backups 없음)
        self.install("claude")  # 다시 설치하면 남긴 기록을 그대로 잇는다
        self.assertIn("habit-plan · Habit Plan", self.ctx(env={"WL_HOME": str(self.home)}))

    def test_single_tool_leaves_shared_state_and_refuses_delete(self):
        self.install("claude")
        self.install("codex")
        self.ok(new_work(self.root, "t", tool="codex"))
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        code, out = self.uninstall("--tool", "codex", "--delete-records")
        self.assertEqual(code, 2)
        self.assertIn("claude가 아직 설치돼 있어", out["projects"][0]["error"])
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)  # 거부는 아무것도 안 바꾼다
        code, out = self.uninstall("--tool", "codex", "--keep-records")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / "AGENTS.md").exists())  # 설치기가 통째로 만든 파일은 사라진다(백업은 남음)
        self.assertEqual(len(list(self.root.glob("AGENTS.md.bak-worklog-*"))), 1)
        self.assertFalse((self.root / ".codex/hooks.json").exists())
        self.assertFalse((self.root / ".agents").exists())
        self.assertEqual(sorted(json.loads((self.d / "install.json").read_text())), ["claude"])
        self.assertTrue((self.d / ".lock").exists() and (self.d / "sessions").is_dir())  # claude가 남아 있어 공용 상태는 그대로
        self.assertEqual((self.root / ".gitignore").read_text(), "node_modules/\n.worklog/\n")  # 공용 줄 유지
        self.assertIn("worklog-shared:begin", (self.root / "CLAUDE.md").read_text())
        self.assertEqual(self.registry(), {str(self.root.resolve()): ["claude"]})
        self.assertIn("claude가 아직 설치돼 있어", out["projects"][0]["notes"][0])

    def test_all_delete_records_purge_and_home(self):
        self.install("claude")
        self.install("codex")
        self.ok(new_work(self.root, "t", tool="claude"))
        code, out = self.uninstall("--home", "--delete-records", root=False)  # 프로젝트가 남아 있으면 home은 거부
        self.assertEqual(code, 2)
        self.assertIn("아직 설치된 프로젝트", out["error"])
        self.assertTrue(self.home.exists())
        code, out = self.uninstall("--all-projects", "--delete-records", "--purge-backups", "--no-backup", "--home", root=False)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["projects"][0]["root"], str(self.root.resolve()))
        self.assertEqual(self.names(self.root), [".claude", ".git", ".gitignore", "CLAUDE.md"])  # .worklog·AGENTS.md·.codex·.agents·백업 전부 제거
        self.assertEqual(self.names(self.root / ".claude"), ["settings.local.json"])
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 기존 내용\n")
        self.assertEqual(out["projects"][0]["backups"], [])
        self.assertEqual(out["home"]["removed"], str(self.home))
        self.assertFalse(self.home.exists())
        self.assertTrue(any("rm -rf" in n for n in out["notes"]))  # clone은 스스로 지우지 않고 명령만 알려 준다

    def test_requires_records_choice_and_refuses_before_writing(self):
        self.install("claude")
        code, out = self.uninstall("--tool", "all")  # 터미널이 아니면 기록 처리를 정하라고 거부
        self.assertEqual(code, 2)
        self.assertIn("--keep-records 또는 --delete-records", out["projects"][0]["error"])
        (self.root / ".claude/settings.local.json").write_text("{broken")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, out = self.uninstall("--tool", "all", "--delete-records")
        self.assertEqual(code, 2)
        self.assertIn("읽을 수 없습니다", out["projects"][0]["error"])
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)  # 거부 전에 쓴 것 없음
        self.assertTrue(self.d.exists())

    def test_guide_only_block_is_deleted_and_middle_block_keeps_both_sides(self):
        (self.root / "CLAUDE.md").unlink()
        self.install("claude")
        self.assertEqual(self.uninstall("--tool", "all", "--keep-records")[0], 0)
        self.assertFalse((self.root / "CLAUDE.md").exists())  # 블록뿐이던 파일은 삭제(백업 1개)
        self.assertEqual(len(list(self.root.glob("CLAUDE.md.bak-worklog-*"))), 1)
        self.install("claude")
        text = (self.root / "CLAUDE.md").read_text()
        (self.root / "CLAUDE.md").write_text("# 위\n\n" + text + "\n# 아래\n")
        self.assertEqual(self.uninstall("--tool", "all", "--keep-records")[0], 0)
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# 위\n\n# 아래\n")


class UserScopeTest(Base):
    """2.21.0: install once per machine (--user); a folder is connected by its first new-work; NOT_CONNECTED elsewhere."""

    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.wl_home = self.root / "wl_home"
        self.wl_home.mkdir()
        (self.wl_home / "config.json").write_text('{"update": "off"}')
        self.env = dict(clean_env(), HOME=str(self.home), WL_HOME=str(self.wl_home))
        self.other_hook = {"type": "command", "command": "echo other", "timeout": 5}
        self.settings0 = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [self.other_hook]}]}}
        (self.home / ".claude/settings.json").write_text(json.dumps(self.settings0))
        self.proj = self.root / "proj"
        self.proj.mkdir()
        (self.proj / ".git").mkdir()

    def script(self, path, *argv):
        p = subprocess.run([sys.executable, "-B", str(path), *argv], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertIn(p.returncode, (0, 2), p.stderr)
        return p.returncode, json.loads(p.stdout)

    def install(self, *argv):
        return self.script(INST, *argv)

    def uninstall(self, *argv):
        return self.script(UNINST, *argv)

    def cmd(self, root, command, *extra, session="s1", tool="claude", payload=None):
        return run(root, command, payload, session=session, tool=tool, extra=extra, env=self.env)

    def user_manifest(self):
        return json.loads((self.wl_home / "install.json").read_text())

    def registry(self):
        try:
            return json.loads((self.wl_home / "installs.json").read_text())
        except FileNotFoundError:
            return None

    def tree(self, folder):
        return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

    def test_user_install_config_failure_leaves_no_manifest(self):
        """2.25.0: config.json is written before the manifest, so a failed config write leaves no manifest entry (rollback
        covers the tool files only)."""
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "WL_HOME": str(self.wl_home)}):
            spec = importlib.util.spec_from_file_location("install_project_f11", INST)
            inst = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(inst)
            real = inst.wl.write_atomic
            def failing(path, text):
                if Path(path).name == "config.json":
                    raise OSError("디스크 가득 참")
                return real(path, text)
            out, code = io.StringIO(), 0
            argv = ["install_project.py", "--tool", "claude", "--user"]
            with mock.patch.object(inst.wl, "write_atomic", failing), mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", out):
                try:
                    inst.main()
                except SystemExit as e:
                    code = e.code
        self.assertEqual(code, 2, out.getvalue())
        self.assertIn("rolled_back", json.loads(out.getvalue()))
        self.assertFalse((self.wl_home / "install.json").exists())                  # 매니페스트가 남지 않는다
        self.assertEqual(json.loads((self.wl_home / "config.json").read_text()), {"update": "off"})
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())                # 도구 파일은 되돌렸다
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text()), self.settings0)

    def test_user_install_claude_and_codex(self):
        before = self.tree(self.home)
        code, out = self.install("--tool", "claude", "--user", "--dry-run")
        self.assertEqual((code, out["scope"], out["dry_run"]), (0, "user", True))
        self.assertEqual(sorted(Path(c).name for c in out["changed"]), ["CLAUDE.md", "SKILL.md", "settings.json"])
        self.assertEqual(out["config"], {"path": str(self.wl_home / "config.json"), "auto": "on"})  # 2.25.0: auto 키가 없으면 on을 적는다(changed와 별도)
        self.assertEqual(self.tree(self.home), before)  # dry-run은 아무것도 안 쓴다
        self.assertFalse((self.wl_home / "install.json").exists())
        self.assertEqual(json.loads((self.wl_home / "config.json").read_text()), {"update": "off"})
        code, out = self.install("--tool", "claude", "--user")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((self.wl_home / "config.json").read_text()), {"update": "off", "auto": "on"})  # 다른 키 유지
        guide = (self.home / ".claude/CLAUDE.md").read_text()
        self.assertEqual(guide.count("worklog-shared:begin"), 1)
        self.assertIn("| NOT_CONNECTED |", guide)  # 2.21.0 규칙 첫 줄
        self.assertIn("--tool claude", guide)
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(settings["permissions"], self.settings0["permissions"])  # 남의 설정·Hook 유지, 새 그룹은 뒤에
        self.assertEqual(settings["hooks"]["SessionStart"][0], self.settings0["hooks"]["SessionStart"][0])
        self.assertEqual([len(settings["hooks"][e]) for e in ("SessionStart", "UserPromptSubmit", "Stop")], [2, 1, 1])
        self.assertIn(f"{WL} hook --tool claude", settings["hooks"]["SessionStart"][1]["hooks"][0]["command"].replace("'", ""))
        self.assertTrue((self.home / ".claude/skills/worklog/SKILL.md").exists())
        m = self.user_manifest()["claude"]
        self.assertEqual(m["rules_src_sha"], hashlib.sha256((WL.parents[1] / "adapters/rules.md").read_bytes()).hexdigest())
        self.assertEqual(m["version"], load_wl().VERSION)
        self.assertIsNone(self.registry())  # 사용자 범위 설치는 프로젝트를 등록하지 않는다
        self.assertFalse(any(p.name == ".worklog" for p in self.home.rglob(".worklog")))
        self.assertEqual(len(list((self.home / ".claude").glob("settings.json.bak-worklog-*"))), 1)
        after = self.tree(self.home)
        code, out = self.install("--tool", "claude", "--user")  # 두 번째 실행: 파일 불변(Hook 바이트 유지), 매니페스트만 다시 씀
        self.assertEqual((code, [Path(c).name for c in out["changed"]]), (0, ["install.json"]))
        self.assertNotIn("config", out)  # auto 키가 이미 있으면 그대로 둔다
        self.assertEqual(self.tree(self.home), after)
        code, out = self.install("--tool", "codex", "--user")
        self.assertEqual(code, 0, out)
        self.assertIn("worklog-shared:begin", (self.home / ".codex/AGENTS.md").read_text())
        self.assertEqual(len(json.loads((self.home / ".codex/hooks.json").read_text())["hooks"]["Stop"]), 1)
        self.assertTrue((self.home / ".agents/skills/worklog/SKILL.md").exists())
        self.assertEqual(sorted(self.user_manifest()), ["claude", "codex"])
        self.assertIn("/hooks", out["next"])
        code, out = self.install("--tool", "pi", "--user")  # 2.24.0: pi has a user-level install (block, extension, skill)
        self.assertEqual(code, 0, out)
        self.assertIn("worklog-shared:begin", (self.home / ".pi/agent/AGENTS.md").read_text())
        self.assertIn(json.dumps(str(WL)), (self.home / ".pi/agent/extensions/worklog.ts").read_text())
        self.assertTrue((self.home / ".pi/agent/skills/worklog/SKILL.md").exists())
        self.assertEqual(sorted(self.user_manifest()), ["claude", "codex", "pi"])
        p = subprocess.run([sys.executable, "-B", str(INST), "--tool", "claude", "--user", "--root", str(self.proj)], capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 2)  # --user와 --root는 배타
        p = subprocess.run([sys.executable, "-B", str(INST), "--tool", "claude", "--root", str(self.proj), "--migrate"], capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 2)  # --migrate는 --user와만
        code, out = self.install("--user")
        self.assertEqual(code, 2)
        self.assertIn("--user", out["error"])  # 도구를 묻는 거부에 --user 안내

    def test_not_connected_hook_and_commands(self):
        r, out = hook(self.proj, "hook", env=self.env)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NOT_CONNECTED | root={self.proj.resolve()} | auto=on | git=yes] "), ctx)
        self.assertFalse((self.proj / ".worklog").exists())
        self.assertFalse((self.wl_home / "update.json").exists())  # 갱신 검사를 띄우지 않는다
        self.assertEqual(hook(self.proj, "turn-start", env=self.env), (0, ""))
        self.assertEqual(hook(self.proj, "stop-hook", env=self.env), (0, ""))
        r, out = self.cmd(self.proj, "show")
        self.assertEqual(r, 0)
        first, line = out.split("\n", 1)
        self.assertIn("연결되지 않은 폴더", first)
        self.assertEqual(line, ctx.replace("SessionStart | NOT_CONNECTED", "show | NOT_CONNECTED", 1))  # 2.26.0: Hook과 같은 안내(auto=on)
        (self.wl_home / "config.json").write_text('{"update": "off", "auto": "off"}')
        out = self.cmd(self.proj, "show")[1]
        (self.wl_home / "config.json").write_text('{"update": "off"}')
        self.assertIn("| auto=off | git=yes] ", out)
        self.assertIn('사용자가 "새 작업: <제목>"이라 하기 전까지', out)
        self.refused(self.cmd(self.proj, "use", "t", "--quote", "t 이어서"), "연결되지 않은 폴더")
        self.refused(self.cmd(self.proj, "on"), "연결되지 않은 폴더")
        self.refused(self.cmd(self.proj, "off", "--quote", "워크로그 꺼"), "연결되지 않은 폴더")
        self.assertEqual(self.ok(self.cmd(self.proj, "skip", "읽기 전용")), {"ok": True, "turn": 0})
        self.assertFalse((self.proj / ".worklog").exists())

    def test_new_work_connects(self):
        out = self.ok(self.cmd(self.proj, "new-work", "Habit Plan", "--quote", "새 작업: Habit Plan"))
        self.assertEqual((out["id"], out["connected"], out["connected_notes"]), ("habit-plan", True, []))
        self.assertEqual((self.proj / ".gitignore").read_text(), ".worklog/\n")  # git 프로젝트: 줄 추가(백업 없음)
        self.assertEqual(self.registry(), {str(self.proj.resolve()): ["claude"]})
        entry = json.loads((self.proj / ".worklog/install.json").read_text())["claude"]
        self.assertEqual((entry["scope"], entry["version"], "rules_src_sha" in entry), ("user", load_wl().VERSION, False))
        self.assertEqual(sorted(Path(c).name for c in out["connected_changed"]), [".gitignore", "install.json", "installs.json"])
        ctx = json.loads(hook(self.proj, "hook", env=self.env)[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("| PROVIDED |", ctx)  # 연결 뒤 같은 세션의 SessionStart는 현재 작업을 주입
        self.assertNotIn("connected", self.ok(self.cmd(self.proj, "new-work", "Second", "--quote", "새 작업: Second", "--force")))  # 이미 연결됨
        self.ok(self.cmd(self.proj, "save", payload={"type": "REQUEST", "summary": "x", "quote": "q"}))
        (self.proj / ".gitignore").write_text("/.worklog\nnode_modules/\n")  # 이미 무시 중이면 불변
        shutil.rmtree(self.proj / ".worklog")
        self.ok(self.cmd(self.proj, "new-work", "T", "--quote", "새 작업: T"))
        self.assertEqual((self.proj / ".gitignore").read_text(), "/.worklog\nnode_modules/\n")
        plain = self.root / "plain"  # git이 아니면 .gitignore 없음, 등록·매니페스트는 됨
        plain.mkdir()
        out = self.ok(self.cmd(plain, "new-work", "P", "--quote", "새 작업: P", tool="codex"))
        self.assertTrue(out["connected"] and not (plain / ".gitignore").exists())
        self.assertEqual(sorted(self.registry()), sorted([str(self.proj.resolve()), str(plain.resolve())]))
        self.assertEqual(json.loads((plain / ".worklog/install.json").read_text())["codex"]["scope"], "user")
        sub = self.proj / "sub"  # 상위에 작업이 있는 .worklog가 있으면 notice
        sub.mkdir()
        out = self.ok(self.cmd(sub, "new-work", "S", "--quote", "새 작업: S"))
        self.assertIn(f"상위 폴더 {self.proj.resolve()}에 Worklog", out["notice"])
        self.assertIn("사용자에게 확인", out["notice"])
        self.assertNotIn("warning", out)  # 연결한 세션: 연결 전 Hook은 기록을 남길 수 없으므로 미작동 경고 없음(M 시험 발견)
        self.assertEqual(out["hooks"], {"session_start": None, "turn_start": None, "stop": None})  # 2.26.0: 첫 연결 턴은 null
        self.assertNotIn("첫 연결 턴", out["notice"])  # new-work의 notice는 다른 작업 제약·상위 폴더 안내만(첫 연결 안내는 save·skip에)
        self.assertNotIn("warning", self.ok(self.cmd(sub, "skip", "x")))
        self.assertIn("warning", self.ok(self.cmd(sub, "skip", "x", session="other")))  # 연결하지 않은 다른 세션은 기존대로 경고
        wl_like = self.root / "wl_like"  # 작업 없는 .worklog(WL_HOME 같은 상태 폴더, 빈 연결)는 상위로 치지 않는다(M 시험 발견: ~/.worklog 오인)
        (wl_like / ".worklog").mkdir(parents=True)
        (wl_like / ".worklog/installs.json").write_text("{}")
        (wl_like / "deep").mkdir()
        self.assertNotIn("notice", self.ok(self.cmd(wl_like / "deep", "new-work", "D", "--quote", "새 작업: D")))
        broken = Path(tempfile.mkdtemp()) / "nothome"  # registry를 못 쓰면 연결은 되고 notes에 남는다
        broken.write_text("x")
        p2 = self.root / "p2"
        p2.mkdir()
        r, raw = run(p2, "new-work", session="s1", tool="claude", extra=["Q", "--quote", "새 작업: Q"], env=dict(self.env, WL_HOME=str(broken)))
        out = json.loads(raw)
        self.assertEqual((r, out["connected"]), (0, True))
        self.assertTrue(any("등록하지 못함" in n for n in out["connected_notes"]), out)
        self.assertTrue((p2 / ".worklog/index.json").exists())

    def test_install_report_by_scope(self):
        self.ok(self.cmd(self.proj, "new-work", "T", "--quote", "새 작업: T"))
        self.assertNotIn("warning_install", self.ok(self.cmd(self.proj, "skip", "x")))  # 전역 매니페스트 없음 → 경고 없음
        (self.wl_home / "install.json").write_text(json.dumps({"claude": {"version": "0.0.1", "rules_src_sha": "0" * 64, "installed_at": "x"}}))
        w = self.ok(self.cmd(self.proj, "skip", "x"))["warning_install"]
        self.assertIn("--user", w)  # 연결만 된 폴더(scope user)는 전역 사본과 비교하고 --user 재설치를 안내
        self.assertNotIn("--root", w)
        self.assertIn("[Worklog 사본 경고]", json.loads(hook(self.proj, "hook", env=self.env)[1])["hookSpecificOutput"]["additionalContext"])
        (self.proj / ".worklog/install.json").write_text(json.dumps({"claude": {"version": "0.0.2", "rules_src_sha": "1" * 64, "installed_at": "x"}}))
        w = self.ok(self.cmd(self.proj, "skip", "x"))["warning_install"]
        self.assertIn(f"--root {shlex.quote(str(self.proj.resolve()))}", w)  # 프로젝트 단위 설치는 그 사본과 비교
        self.assertIn("v0.0.2", w)
        (self.proj / ".worklog/install.json").unlink()
        self.assertIn("--user", self.ok(self.cmd(self.proj, "skip", "x"))["warning_install"])  # 항목 없음 → 전역과 비교

    def test_user_install_refuses_project_hooks_and_migrates(self):
        code, out = self.install("--tool", "claude", "--root", str(self.proj))
        self.assertEqual(code, 0, out)
        self.ok(self.cmd(self.proj, "new-work", "T", "--quote", "새 작업: T"))
        self.ok(self.cmd(self.proj, "save", payload={"type": "REQUEST", "summary": "x", "quote": "q"}))
        sess = session_file(self.proj)
        self.assertTrue(sess.exists())
        home_before = self.tree(self.home)
        code, out = self.install("--tool", "claude", "--user")
        self.assertEqual(code, 2)
        self.assertIn(str(self.proj.resolve()), out["error"])
        self.assertIn("--migrate", out["error"])
        self.assertEqual(self.tree(self.home), home_before)  # 거부는 아무것도 안 쓴다
        proj_before = self.tree(self.proj)
        code, out = self.install("--tool", "claude", "--user", "--migrate", "--dry-run")
        self.assertEqual((code, out["migrated"][0]["root"]), (0, str(self.proj.resolve())))
        self.assertEqual((self.tree(self.home), self.tree(self.proj)), (home_before, proj_before))
        code, out = self.install("--tool", "claude", "--user", "--migrate")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.proj / "CLAUDE.md").exists())  # 블록뿐이던 파일은 삭제(백업 남음)
        self.assertEqual(len(list(self.proj.glob("CLAUDE.md.bak-worklog-*"))), 1)
        self.assertFalse((self.proj / ".claude/settings.local.json").exists())
        self.assertFalse((self.proj / ".claude/skills").exists())
        self.assertTrue(sess.exists())  # 진행 중 세션은 유지
        self.assertTrue((self.proj / ".worklog/works/t/events.jsonl").exists())
        self.assertEqual((self.proj / ".gitignore").read_text(), ".worklog/\n")
        entry = json.loads((self.proj / ".worklog/install.json").read_text())["claude"]
        self.assertEqual((entry["scope"], "rules_src_sha" in entry), ("user", False))
        self.assertEqual(self.registry(), {str(self.proj.resolve()): ["claude"]})  # 여전히 연결된 프로젝트
        self.assertIn("worklog-shared:begin", (self.home / ".claude/CLAUDE.md").read_text())
        self.assertIn("| PROVIDED |", json.loads(hook(self.proj, "hook", env=self.env)[1])["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("warning_install", self.ok(self.cmd(self.proj, "skip", "x")))
        code, out = self.install("--tool", "claude", "--user")  # 이제 프로젝트 Hook이 없으니 거부 없음
        self.assertEqual((code, out["migrated"]), (0, []))

    def test_uninstall_user(self):
        self.install("--tool", "claude", "--user")
        self.install("--tool", "codex", "--user")
        self.ok(self.cmd(self.proj, "new-work", "T", "--quote", "새 작업: T"))
        before = self.tree(self.home)
        p = subprocess.run([sys.executable, "-B", str(UNINST), "--user"], capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 2)  # --user에는 --tool이 필요
        code, out = self.uninstall("--user", "--tool", "claude", "--dry-run")
        self.assertEqual((code, out["user"]["dry_run"]), (0, True))
        self.assertEqual(self.tree(self.home), before)
        self.assertEqual(sorted(self.user_manifest()), ["claude", "codex"])
        code, out = self.uninstall("--user", "--tool", "claude")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())  # 블록뿐이던 파일은 삭제
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text()), self.settings0)  # 남의 Hook·설정 복원
        self.assertFalse((self.home / ".claude/skills").exists())
        self.assertEqual(sorted(self.user_manifest()), ["codex"])
        self.assertIn("worklog-shared:begin", (self.home / ".codex/AGENTS.md").read_text())  # codex는 그대로
        self.assertTrue((self.proj / ".worklog/index.json").exists())  # 프로젝트 기록은 건드리지 않는다
        self.assertEqual(self.registry(), {str(self.proj.resolve()): ["claude"]})
        code, out = self.uninstall("--user", "--tool", "all", "--purge-backups")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".codex/AGENTS.md").exists() or (self.home / ".codex/hooks.json").exists() or (self.home / ".agents").exists())
        self.assertEqual(len(list((self.home / ".codex").glob("AGENTS.md.bak-worklog-*"))), 1)  # 이번 제거의 백업(블록뿐이던 파일)
        self.assertFalse((self.wl_home / "install.json").exists())
        self.assertEqual(list((self.home / ".claude").glob("*.bak-worklog-*")), [])  # --purge-backups: 이전 설치·제거의 백업 삭제
        code, out = self.uninstall("--home")  # 연결된 프로젝트가 남아 있으면 home은 거부
        self.assertEqual(code, 2)
        self.assertIn("아직 설치된 프로젝트", out["error"])

    def test_connected_only_project_uninstall(self):
        self.ok(self.cmd(self.proj, "new-work", "T", "--quote", "새 작업: T"))
        self.ok(self.cmd(self.proj, "save", payload={"type": "REQUEST", "summary": "x", "quote": "q"}))
        code, out = self.uninstall("--root", str(self.proj), "--keep-records")
        self.assertEqual(code, 2)
        self.assertIn("설치됨: claude", out["projects"][0]["error"])  # 연결 항목만 있어도 "설치됨"
        code, out = self.uninstall("--root", str(self.proj), "--tool", "all", "--keep-records")
        self.assertEqual(code, 0, out)
        p = out["projects"][0]
        self.assertTrue(any("여전히 연결된 폴더" in n for n in p["notes"]), p)
        self.assertEqual((self.proj / ".gitignore").read_text(), ".worklog/\n")  # 기록을 남기면 줄도 남는다
        self.assertTrue((self.proj / ".worklog/works/t/events.jsonl").exists())
        self.assertFalse((self.proj / ".worklog/install.json").exists())
        self.assertIsNone(self.registry())
        ctx = json.loads(hook(self.proj, "hook", env=self.env)[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("| NO_CURRENT_WORK |", ctx)  # 여전히 연결됨(세션 파일은 지워져 현재 작업만 없음)
        self.ok(self.cmd(self.proj, "new-work", "U", "--quote", "새 작업: U", session="s2"))  # 이미 .worklog가 있어 재연결 없음
        self.assertFalse((self.proj / ".worklog/install.json").exists())
        code, out = self.uninstall("--root", str(self.proj), "--tool", "claude", "--delete-records")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.proj / ".worklog").exists())
        self.assertFalse((self.proj / ".gitignore").exists())  # 줄뿐이던 파일은 삭제
        self.assertIn("| NOT_CONNECTED |", json.loads(hook(self.proj, "hook", env=self.env)[1])["hookSpecificOutput"]["additionalContext"])

    def test_update_reinstalls_user_scope(self):
        self.install("--tool", "claude", "--user")
        (self.home / ".claude/CLAUDE.md").write_text("# 사용자 글\n")  # 블록이 지워진 상태 → 재설치가 복원
        (self.proj / ".worklog").mkdir()
        (self.proj / ".worklog/install.json").write_text(json.dumps({"claude": {"version": "0", "connected_at": "x", "scope": "user"}}))
        with mock.patch.dict(os.environ, self.env):
            spec = importlib.util.spec_from_file_location("upd", WL.parents[1] / "tools" / "update.py")
            upd = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(upd)
            self.assertEqual(upd.reinstall_user(), ["claude"])
            self.assertEqual(upd.reinstall(self.proj.resolve()), [])  # scope user 항목은 프로젝트 재설치 대상이 아니다
        text = (self.home / ".claude/CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# 사용자 글") and text.count("worklog-shared:begin") == 1)
        self.assertFalse((self.proj / "CLAUDE.md").exists())


class AgyPiTest(Base):
    """2.24.0: agy (Antigravity CLI) hooks.json payloads/outputs, Stop blocked once per turn without a tool flag, and the
    user-level installs of agy (own rule file, named hook, global skill) and pi (block, extension, skill)."""

    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".gemini" / "config").mkdir(parents=True)
        (self.home / ".pi" / "agent").mkdir(parents=True)
        self.wl_home = self.root / "wl_home"
        self.wl_home.mkdir()
        (self.wl_home / "config.json").write_text('{"update": "off"}')
        self.env = dict(clean_env(), HOME=str(self.home), WL_HOME=str(self.wl_home))
        self.other = {"SessionStart": [{"type": "command", "command": "echo other", "timeout": 5}]}
        (self.home / ".gemini/config/hooks.json").write_text(json.dumps({"herdr": self.other}, indent=1))

    def script(self, path, *argv):
        p = subprocess.run([sys.executable, "-B", str(path), *argv], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertIn(p.returncode, (0, 2), p.stderr)
        return p.returncode, json.loads(p.stdout)

    def agy(self, cmd, **event):
        """A hook as agy runs it: hooks.json payload (conversationId, workspacePaths), JSON on stdout."""
        raw = json.dumps({"conversationId": "c1", "workspacePaths": [str(self.root)], "modelName": "x", **event})
        p = subprocess.run([sys.executable, "-B", str(WL), cmd, "--tool", "agy"], input=raw, capture_output=True, text=True,
                           env=clean_env(), cwd=tempfile.gettempdir())
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)

    def session(self):
        return json.loads(session_file(self.root, "agy_c1").read_text())

    def test_agy_hook_payloads_and_outputs(self):
        r, out = self.agy("hook")
        self.assertEqual(r, 0)
        self.assertIn("NOT_CONNECTED", out["injectSteps"][0]["systemMessage"]["systemMessage"])  # 미연결: injectSteps 형식의 한 줄
        self.assertFalse(session_file(self.root, "agy_c1").exists())
        self.assertEqual(self.agy("turn-start")[1], {})
        self.assertEqual(self.agy("stop-hook")[1], {})
        self.d.mkdir()
        run(self.root, "new-work", session="c1", tool="agy", extra=["t", "--quote", "새 작업"])
        r, out = self.agy("hook")
        text = out["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertTrue(text.startswith("[Worklog worklog/2 SessionStart | PROVIDED"), text)
        self.assertIn("SessionStart", self.session()["hooks_seen"])
        self.assertEqual(self.agy("turn-start", invocationNum=0)[1], {})
        self.assertEqual(self.session()["turn"], 1)
        self.assertEqual(self.agy("turn-start", invocationNum=1)[1], {})  # 같은 턴의 두 번째 모델 호출: 턴이 늘지 않는다
        self.assertEqual(self.session()["turn"], 1)
        r, out = self.agy("stop-hook", terminationReason="NO_TOOL_CALL")  # save 없음 → 차단(continue)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("save", out["reason"])
        self.assertEqual(self.session()["blocked_turn"], 1)
        self.assertEqual(self.agy("stop-hook", terminationReason="NO_TOOL_CALL")[1], {})  # 같은 턴 두 번째 Stop: 통과, 턴 진행
        self.assertEqual(self.session()["turn"], 2)
        self.assertEqual(self.agy("stop-hook", terminationReason="USER_CANCELED")[1], {})  # 취소·오류 종료는 막지 않는다
        self.assertEqual(self.session()["turn"], 2)
        out = json.loads(run(self.root, "skip", session="c1", tool="agy", extra=["읽기"])[1])
        self.assertEqual(out["hooks"], {"session_start": True, "turn_start": True, "stop": True})
        self.assertNotIn("warning", out)

    def test_agy_auto_mode_tool_calls_do_not_advance_turn(self):
        """2.24.1 (premise corrected in 2.24.2: invocationNum does increase across tool calls; repeats come from a doubled hook):
        PreInvocations after the first one of a turn do not advance it; save/skip in that turn satisfies the Stop; a blocked turn
        is blocked once even though agy's re-entry starts turn+1."""
        self.d.mkdir()
        self.agy("hook")
        for _ in range(3):  # new-work, save, answer: three model calls, one turn
            self.agy("turn-start", invocationNum=0)
        self.assertEqual(self.session()["turn"], 1)
        run(self.root, "new-work", session="c1", tool="agy", extra=["t", "--quote", "새 작업"])
        self.agy("turn-start", invocationNum=0)  # the model call after the new-work tool result
        r, out = run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="c1", tool="agy")
        self.assertEqual(r, 0, out)
        self.assertEqual(self.agy("stop-hook", terminationReason="NO_TOOL_CALL")[1], {})  # saved in this turn → pass
        self.assertEqual((self.session()["turn"], self.session()["in_turn"]), (2, False))
        self.agy("turn-start", invocationNum=0)  # next user turn
        self.agy("turn-start", invocationNum=0)  # a tool call inside it
        self.assertEqual(self.session()["turn"], 3)
        self.assertEqual(self.agy("stop-hook", terminationReason="NO_TOOL_CALL")[1]["decision"], "continue")  # nothing saved → blocked once
        self.agy("turn-start", invocationNum=0)  # re-entry starts turn 4
        self.assertEqual(self.agy("stop-hook", terminationReason="NO_TOOL_CALL")[1], {})  # still nothing saved → passes (blocked once), no loop
        self.assertEqual(self.session()["turn"], 5)

    def test_agy_duplicate_hook_registration_acts_once(self):
        """2.24.2: with the project .agents/hooks.json and ~/.gemini/config/hooks.json both carrying the worklog hook, agy runs every
        hook twice. The second delivery of the same event is a no-op: one injection, one turn, one Stop judgement (the 2.24.0
        loop: the first Stop passed and advanced the turn, the second blocked the new turn)."""
        self.d.mkdir()
        run(self.root, "new-work", session="c1", tool="agy", extra=["t", "--quote", "새 작업"])
        r, out = self.agy("hook")
        self.assertIn("injectSteps", out)
        self.assertEqual(self.agy("hook")[1], {})  # duplicate SessionStart before any turn
        for i in range(2):
            self.agy("turn-start", invocationNum=0, initialNumSteps=1)  # delivered twice
        self.assertEqual(self.session()["turn"], 1)
        run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, session="c1", tool="agy")
        self.agy("turn-start", invocationNum=1, initialNumSteps=3)
        self.agy("turn-start", invocationNum=1, initialNumSteps=3)
        self.assertEqual(self.session()["turn"], 1)
        self.assertEqual(self.agy("stop-hook", executionNum=0, terminationReason="NO_TOOL_CALL")[1], {})  # saved → pass, turn 2
        self.assertEqual(self.agy("stop-hook", executionNum=0, terminationReason="NO_TOOL_CALL")[1], {})  # duplicate: no second judgement
        self.assertEqual((self.session()["turn"], self.session()["blocked_turn"]), (2, 0))
        self.agy("turn-start", invocationNum=0, initialNumSteps=1)  # next user turn, nothing saved
        self.agy("turn-start", invocationNum=0, initialNumSteps=1)
        self.assertEqual(self.agy("stop-hook", executionNum=1, terminationReason="NO_TOOL_CALL")[1]["decision"], "continue")  # blocked once
        self.assertEqual(self.agy("stop-hook", executionNum=1, terminationReason="NO_TOOL_CALL")[1], {})  # duplicate of the blocked Stop
        self.assertEqual(self.session()["blocked_turn"], 3)

    def test_claude_stop_blocks_once_without_flag(self):
        """2.24.0: a second Stop of the same turn passes even without stop_hook_active (pi's extension sends none)."""
        self.d.mkdir()
        run(self.root, "new-work", session="s1", tool="claude", extra=["t", "--quote", "새 작업"])
        hook(self.root, "turn-start")
        r, out = hook(self.root, "stop-hook")
        self.assertEqual(json.loads(out)["decision"], "block")
        r, out = hook(self.root, "stop-hook")
        self.assertEqual(out.strip(), "")
        self.assertEqual(json.loads(session_file(self.root).read_text())["turn"], 2)

    def test_user_install_agy_and_pi_and_uninstall(self):
        code, out = self.script(INST, "--tool", "agy", "--user", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(Path(c).name for c in out["changed"]), ["SKILL.md", "hooks.json", "worklog.md"])
        code, out = self.script(INST, "--tool", "agy", "--user")
        self.assertEqual(code, 0, out)
        rule = (self.home / ".gemini/config/rules/worklog.md").read_text()
        self.assertTrue(rule.startswith("---\ntrigger: always_on\n---\n<!-- worklog-shared:begin -->"), rule[:80])
        self.assertIn("--tool agy", rule)
        hooks = json.loads((self.home / ".gemini/config/hooks.json").read_text())
        self.assertEqual(hooks["herdr"], self.other)  # 다른 이름의 훅은 그대로
        self.assertEqual(sorted(hooks["worklog"]), ["PreInvocation", "SessionStart", "Stop"])
        self.assertTrue(hooks["worklog"]["Stop"][0]["command"].endswith("stop-hook --tool agy"))
        self.assertTrue((self.home / ".gemini/config/skills/worklog/SKILL.md").exists())
        self.assertEqual(len(list((self.home / ".gemini/config").glob("hooks.json.bak-worklog-*"))), 1)
        code, out = self.script(INST, "--tool", "agy", "--user")  # 재실행: 매니페스트만
        self.assertEqual([Path(c).name for c in out["changed"]], ["install.json"])
        code, out = self.script(INST, "--tool", "pi", "--user")
        self.assertEqual(code, 0, out)
        ext = (self.home / ".pi/agent/extensions/worklog.ts").read_text()
        self.assertIn(f"const WL = {json.dumps(str(WL))};", ext)
        self.assertIn("agent_before_settle", ext)
        manifest = json.loads((self.wl_home / "install.json").read_text())
        self.assertEqual(sorted(manifest), ["agy", "pi"])
        code, out = self.script(UNINST, "--user", "--tool", "agy")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".gemini/config/rules/worklog.md").exists())
        self.assertEqual(json.loads((self.home / ".gemini/config/hooks.json").read_text()), {"herdr": self.other})
        self.assertFalse((self.home / ".gemini/config/skills").exists())
        self.assertEqual(sorted(json.loads((self.wl_home / "install.json").read_text())), ["pi"])
        code, out = self.script(UNINST, "--user", "--tool", "pi")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".pi/agent/extensions/worklog.ts").exists())
        self.assertFalse((self.home / ".pi/agent/AGENTS.md").exists())  # 블록뿐이던 파일은 삭제
        self.assertFalse((self.wl_home / "install.json").exists())

    def test_project_install_agy_has_no_skill_and_does_not_shadow_codex(self):
        proj = self.root / "proj"
        proj.mkdir()
        code, out = self.script(INST, "--tool", "agy", "--root", str(proj))
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(Path(c).name for c in out["changed"]), [".worklog", "hooks.json", "install.json", "worklog.md"])
        self.assertTrue((proj / ".worklog").is_dir() and (proj / ".agents/hooks.json").exists())
        self.assertTrue((proj / ".agents/rules/worklog.md").read_text().startswith("---\ntrigger: always_on\n---\n"))
        self.assertFalse((proj / ".agents/skills").exists() or (proj / "AGENTS.md").exists())
        code, out = self.script(INST, "--tool", "codex", "--root", str(proj))
        self.assertEqual(code, 0, out)
        self.assertIn("--tool codex", (proj / ".agents/skills/worklog/SKILL.md").read_text())
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "codex", "--keep-records")
        self.assertEqual(code, 0, out)
        self.assertIn("agy가 아직 설치돼 있어", out["projects"][0]["notes"][0])
        self.assertTrue((proj / ".agents/hooks.json").exists() and (proj / ".agents/rules/worklog.md").exists())  # agy의 훅·규칙 파일은 남는다
        self.assertFalse((proj / "AGENTS.md").exists())  # codex의 블록뿐이던 AGENTS.md는 사라진다
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "agy", "--keep-records", "--no-backup")
        self.assertEqual(code, 0, out)
        self.assertFalse((proj / ".agents").exists(), sorted(str(q) for q in proj.rglob(".agents/**/*")))  # 규칙 파일·훅·빈 폴더 모두 정리


class UninstallRoundTripTest(Base):
    """제거 게이트(2026-10-20 추가 지시): 사용자 수준·프로젝트 수준 × 네 도구를 임시 HOME·임시 프로젝트에 설치했다가 제거한다.
    ① .worklog/ 원장·세션 파일 불변(--user 제거는 연결된 프로젝트를 건드리지 않고, 프로젝트 제거 --keep-records는 기록을 남긴다)
    ② 설치 전과 제거 뒤 파일 트리 동일(빈 폴더 prune, --purge-backups --no-backup) ③ 미리 넣어 둔 다른 훅(hooks.json의 herdr 키·
    settings의 다른 그룹)과 블록 밖 본문 불변 ④ --dry-run 삭제·수정 목록 = 설치기가 만든 파일 집합."""
    OTHER = {"type": "command", "command": "echo other", "timeout": 5}

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()  # 설치기·제거기는 경로를 resolve해 적는다(/var → /private/var)
        self.home = self.root / "home"
        self.wl_home = self.root / "wl_home"
        self.wl_home.mkdir()
        (self.wl_home / "config.json").write_text('{"update": "off"}')
        self.env = dict(clean_env(), HOME=str(self.home), WL_HOME=str(self.wl_home))
        # 이 기기에 있을 법한 사용자 설정: 다른 훅(herdr)과 블록 밖 본문
        for d in (".claude", ".codex", ".gemini/config", ".pi/agent"):
            (self.home / d).mkdir(parents=True)
        (self.home / ".claude/CLAUDE.md").write_text("# 내 지침\n")
        (self.home / ".claude/settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [self.OTHER]}]}}, indent=2) + "\n")
        (self.home / ".codex/AGENTS.md").write_text("# codex 지침\n")
        (self.home / ".codex/hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [self.OTHER]}]}}, indent=2) + "\n")
        (self.home / ".gemini/config/hooks.json").write_text(json.dumps({"herdr": {"SessionStart": [self.OTHER]}}, indent=1))
        (self.home / ".pi/agent/AGENTS.md").write_text("# pi 지침\n")

    def script(self, path, *argv):
        p = subprocess.run([sys.executable, "-B", str(path), *argv], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertIn(p.returncode, (0, 2), p.stderr)
        return p.returncode, json.loads(p.stdout)

    @staticmethod
    def tree(base):
        """{상대 경로: "dir" | 내용 sha | JSON 정규형} — 빈 폴더까지 비교한다."""
        out = {}
        for p in base.rglob("*"):
            rel = str(p.relative_to(base))
            if p.is_dir():
                out[rel] = "dir"
            elif p.suffix == ".json":  # 훅·설정 JSON은 설치기·제거기가 indent 2로 다시 쓴다: 내용(의미)만 비교한다
                out[rel] = json.dumps(json.loads(p.read_text()), sort_keys=True)
            else:
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    @staticmethod
    def norm(paths, worklog=None):
        """비교용 경로 집합: rmtree의 끝 '/'를 떼고, .worklog/ 안의 파일은 폴더 하나로 친다(설치기는 .worklog와 install.json을 따로 적고,
        제거기는 .worklog/ 하나로 지운다)."""
        out = set()
        for p in paths:
            p = p.rstrip("/")
            if worklog and p.startswith(str(worklog) + "/"):
                p = str(worklog)
            out.add(p)
        return out

    def test_uninstall_round_trip_user_and_project_four_tools(self):
        # ── 사용자 수준 ───────────────────────────────────────────────────────────────
        before = self.tree(self.home)
        made = set()
        for tool in ("claude", "codex", "agy", "pi"):
            code, out = self.script(INST, "--tool", tool, "--user")
            self.assertEqual(code, 0, out)
            made |= set(out["changed"])
        self.assertIn(str(self.wl_home / "install.json"), made)
        # 연결된 프로젝트: 원장·세션 파일이 있는 .worklog/ (--user 제거는 건드리지 않는다)
        proj_u = self.root / "proj_u"
        proj_u.mkdir()
        r, raw = run(proj_u, "new-work", session="s1", tool="claude", extra=["Habit", "--quote", "새 작업: Habit"], env=self.env)
        self.assertEqual(r, 0, raw)
        (proj_u / ".worklog/project.md").write_text("- [P1] 본문\n")
        self.assertTrue((proj_u / ".worklog/sessions/claude_s1.json").exists())
        ledger_u = self.tree(proj_u / ".worklog")
        code, out = self.script(UNINST, "--user", "--tool", "all", "--no-backup", "--dry-run")  # ④ 삭제·수정 목록 = 설치 파일 집합
        self.assertEqual(code, 0, out)
        self.assertEqual(self.norm(out["user"]["removed"] + out["user"]["changed"]), self.norm(made), out["user"])
        self.assertTrue(all(str(proj_u) not in p for p in out["user"]["removed"] + out["user"]["changed"]))  # .worklog/ 원장은 대상에 없다
        self.assertEqual(self.tree(self.home), self.tree(self.home) | {})  # dry-run은 아무것도 바꾸지 않았다(아래 실제 제거와 대조)
        code, out = self.script(UNINST, "--user", "--tool", "all", "--no-backup", "--purge-backups")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.tree(self.home), before, "② 설치 전과 제거 뒤 사용자 폴더 트리 동일")  # ③ 다른 훅·블록 밖 본문 불변도 여기에 포함
        self.assertEqual(json.loads((self.home / ".gemini/config/hooks.json").read_text()), {"herdr": {"SessionStart": [self.OTHER]}})
        self.assertEqual(self.tree(proj_u / ".worklog"), ledger_u, "① 연결된 프로젝트의 원장·세션 파일 불변")
        self.assertFalse((self.wl_home / "install.json").exists())
        self.assertIn(str(proj_u), (self.wl_home / "installs.json").read_text())  # 연결 등록은 남는다(문서대로: 프로젝트는 그대로)
        r, raw = run(proj_u, "show", session="s2", tool="claude", env=self.env)
        self.assertEqual(r, 0, raw)
        self.assertNotIn("연결되지 않은 폴더", raw)  # 기록이 남은 폴더는 여전히 연결 상태
        # ── 프로젝트 수준 ─────────────────────────────────────────────────────────────
        proj = self.root / "proj"
        for d in (".git", ".claude", ".codex", ".agents"):
            (proj / d).mkdir(parents=True)
        (proj / "CLAUDE.md").write_text("# 프로젝트 지침\n")
        (proj / "AGENTS.md").write_text("# 프로젝트 agents\n")
        (proj / ".gitignore").write_text("node_modules/\n")
        (proj / ".claude/settings.local.json").write_text(json.dumps({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [self.OTHER]}]}}, indent=2) + "\n")
        (proj / ".codex/hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [self.OTHER]}]}}, indent=2) + "\n")
        (proj / ".agents/hooks.json").write_text(json.dumps({"herdr": {"SessionStart": [self.OTHER]}}, indent=1))
        before = self.tree(proj)
        made = set()
        for tool in ("claude", "codex", "agy", "pi"):
            code, out = self.script(INST, "--tool", tool, "--root", str(proj))
            self.assertEqual(code, 0, out)
            made |= set(out["changed"])
        self.assertEqual(sorted(json.loads((proj / ".worklog/install.json").read_text())), ["agy", "claude", "codex", "pi"])
        r, raw = run(proj, "new-work", session="s1", tool="claude", extra=["Habit", "--quote", "새 작업: Habit"], env=self.env)
        self.assertEqual(r, 0, raw)
        (proj / ".worklog/project.md").write_text("- [P1] 본문\n")
        records = {k: v for k, v in self.tree(proj / ".worklog").items() if k.split("/")[0] in ("works", "index.json", "project.md")}
        worklog = proj / ".worklog"
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "all", "--keep-records", "--no-backup", "--dry-run")
        self.assertEqual(code, 0, out)
        listed = out["projects"][0]["removed"] + out["projects"][0]["changed"]
        self.assertFalse([p for p in listed if any(p.startswith(str(worklog / n)) for n in ("works", "index.json", "project.md"))], listed)  # 원장은 대상에 없다
        self.assertIn(str(worklog / "sessions") + "/", out["projects"][0]["removed"])  # 마지막 도구가 가면 세션 파일은 상태로서 지워진다(문서대로)
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "all", "--delete-records", "--no-backup", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.norm(out["projects"][0]["removed"] + out["projects"][0]["changed"], worklog), self.norm(made, worklog), out["projects"][0])  # ④
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "all", "--keep-records", "--no-backup", "--purge-backups")
        self.assertEqual(code, 0, out)
        self.assertEqual({k: v for k, v in self.tree(worklog).items() if k.split("/")[0] in ("works", "index.json", "project.md")}, records, "① 기록 불변")
        self.assertFalse((worklog / "sessions").exists() or (worklog / "install.json").exists())
        self.assertEqual(json.loads((proj / ".agents/hooks.json").read_text()), {"herdr": {"SessionStart": [self.OTHER]}})  # ③
        self.assertEqual((proj / "AGENTS.md").read_text(), "# 프로젝트 agents\n")
        self.assertEqual((proj / "CLAUDE.md").read_text(), "# 프로젝트 지침\n")
        self.assertIn(".worklog/", (proj / ".gitignore").read_text())  # 기록이 남는 동안 .gitignore 줄도 남는다
        r, raw = run(proj, "show", session="s2", tool="claude", env=self.env)
        self.assertNotIn("연결되지 않은 폴더", raw)  # 기록이 남은 폴더는 여전히 연결 상태(사용자 수준 Hook이 기록)
        code, out = self.script(UNINST, "--root", str(proj), "--tool", "all", "--delete-records", "--no-backup", "--purge-backups")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.tree(proj), before, "② 기록까지 지우면 설치 전 트리와 동일")
        r, raw = run(proj, "show", session="s3", tool="claude", env=self.env)
        self.assertIn("연결되지 않은 폴더", raw)  # 기록이 가면 NOT_CONNECTED로 돌아간다
        self.assertNotIn(str(proj), json.loads((self.wl_home / "installs.json").read_text()))  # registry에서 빠진다(proj_u만 남음)


class AutoConnectTest(Base):
    """2.25.0 (PLAN-auto-connect §7 U층): 루트 후보, NOT_CONNECTED 헤더, auto 설정, FORK, Hook 중복 키, 같은 턴 new-work 거부,
    reassign·rename, 규칙 블록 1단계 축소."""
    # 2.24.2 adapters/rules.md 2~17행(규칙 16항목)의 sha256 앞 16자리. 3행(NOT_CONNECTED)·6행(현재 작업 없음)은 2.25.0에서 교체
    RULES_2_24_2 = {2: "6f4cbb6931ca7278", 3: "9415f22b28ed4f08", 4: "2e10507d74e79527", 5: "86b9cf7f20f0afbd", 6: "570ad4f7baee2e95",
                    7: "22fc65f3ab7e8b9e", 8: "2308274279d90633", 9: "eeab50635b48198f", 10: "3385bef279bf3858", 11: "dcc8129b563ce938",
                    12: "a5865adb6b96621d", 13: "9f29b4a6c8ecf04e", 14: "6838a8a38ec8acf4", 15: "eff8a02e99ac056d", 16: "7486ca233ae3ffa5",
                    17: "349c6f0508465c04"}
    REPLACED = {3, 6, 9, 13, 16}  # 2.27.0: 9 (U11) 결정 이유 한 구절, 13 (U12 C) 산출물 누락 처리, 16 (U14) 하위 사건 채택 문장

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.d = self.root / ".worklog"
        self.wl = load_wl()

    def home(self, **config):
        h = Path(tempfile.mkdtemp())
        (h / "config.json").write_text(json.dumps(dict({"update": "off"}, **config)))
        return {"WL_HOME": str(h)}

    def mk(self, *parts, git=False, records=False, worktree=False):
        p = self.root.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        if git:
            (p / ".git").mkdir()
        if worktree:
            (p / ".git").write_text("gitdir: /elsewhere\n")
        if records:
            (p / ".worklog").mkdir()
            (p / ".worklog/index.json").write_text('{"format": "worklog/2", "works": {}}')
        return p

    def plain(self, cwd, *argv, session="s1", tool="claude", payload=None, env=None):
        """A command as the model runs it: no --root, cwd = the session folder."""
        e = dict(clean_env(), WL_TOOL=tool, WL_SESSION_ID=session, **(env or {}))
        p = subprocess.run([sys.executable, "-B", str(WL), *argv], input=json.dumps(payload) if payload else "",
                           capture_output=True, text=True, env=e, cwd=str(cwd))
        return p.returncode, p.stdout

    def state(self, wid):
        return json.loads((self.d / "works" / wid / "state.json").read_text())

    def events(self, wid):
        return [json.loads(x) for x in (self.d / "works" / wid / "events.jsonl").read_text().splitlines()]

    # --- 루트 후보 (§6-2) ---
    def test_candidate_root_cases(self):
        info = lambda *parts: self.wl.root_info(self.root.joinpath(*parts))
        r = self.mk("g", git=True)
        self.mk("g", "a", "b")
        self.assertEqual(info("g")["root"], r)                                  # git 루트에서 연 세션
        self.assertEqual((info("g", "a", "b")["root"], info("g", "a", "b")["git"]), (r, r))  # 하위 폴더: 기록이 없으면 git 루트
        self.mk("g", "a", records=True)
        self.assertEqual(info("g", "a", "b")["root"], r / "a")                  # 가장 가까운 상위 .worklog/index.json
        self.mk("g", records=True)
        self.assertEqual(info("g", "a", "b")["root"], r / "a")                  # 중첩: 가까운 쪽이 이긴다
        n = self.mk("n", "c")
        self.mk("n", records=True)
        self.assertEqual((info("n", "c")["root"], info("n", "c")["git"]), (n, None))  # git 아님: cwd, 상위 탐색 없음
        x = self.mk("x", records=True)
        y = self.mk("x", "y", git=True)
        self.mk("x", "y", "z")
        i = info("x", "y", "z")
        self.assertEqual((i["root"], i["outside"]), (y, x))                    # git 경계 밖 기록은 합류하지 않고 알림만
        w = self.mk("g", "wt", worktree=True)
        self.mk("g", "wt", "s")
        self.assertEqual(info("g", "wt", "s")["root"], w)                       # worktree: .git 파일이 있는 폴더
        c = self.mk("g", "conn")
        (c / ".worklog").mkdir()
        self.assertEqual(info("g", "conn")["root"], c)                          # cwd가 연결돼 있으면 cwd(2.21.0 그대로)
        h = self.mk("h", git=True)
        self.mk("h", "home", records=True)
        self.mk("h", "home", "s")
        with mock.patch.object(self.wl, "WL_HOME", h / "home" / ".worklog"):
            self.assertEqual(info("h", "home", "s")["root"], h)               # 상위 탐색은 WL_HOME을 고르지 않는다
            bare = self.mk("bare")
            (bare / ".worklog").mkdir()
            with mock.patch.object(self.wl, "WL_HOME", bare / ".worklog"):
                self.assertFalse(self.wl.connected_here(bare))                 # 기록 없는 WL_HOME(~/.worklog)은 연결이 아니다

    def test_not_connected_header_fields(self):
        g = self.mk("g", git=True)
        sub = self.mk("g", "sub")
        ctx = json.loads(hook(sub, "hook")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NOT_CONNECTED | root={g} | auto=on | git=yes] "), ctx)
        self.assertIn(f"root는 세션 폴더 {sub}가 아니라 git 최상위 폴더다.", ctx)
        self.assertEqual(ctx.count("\n"), 1)
        x = self.mk("x", records=True)
        y = self.mk("x", "y", git=True)
        ctx = json.loads(hook(y, "hook")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"상위 폴더 {x}의 Worklog 기록은 git 경계 밖이라 쓰지 않는다", ctx)
        self.assertNotIn("세션 폴더", ctx)
        ctx = json.loads(hook(sub, "hook", env=self.home(auto="off"))[1])["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NOT_CONNECTED | root={g} | auto=off | git=yes] "), ctx)
        self.assertIn('사용자가 "새 작업: <제목>"이라 하기 전까지 Worklog 절차(작업 지정 질문·save·skip·show)를 적용하지 않는다.', ctx)  # 옛 동작
        self.assertNotIn("new-work", ctx)
        for cmd in ("turn-start", "stop-hook"):
            self.assertEqual(hook(sub, cmd), (0, ""))
        self.assertFalse((g / ".worklog").exists() or (sub / ".worklog").exists())  # 세션을 열기만 해서는 아무것도 만들지 않는다

    def test_subfolder_session_joins_git_root(self):
        g = self.mk("g", git=True)
        sub = self.mk("g", "sub")
        out = self.ok(self.plain(sub, "new-work", "구조 설명", "--quote", "이 코드 구조 설명해 줘"))  # --root 없이: 후보 루트
        self.assertTrue(out["connected"])
        self.assertTrue((g / ".worklog/index.json").is_file())
        self.assertFalse((sub / ".worklog").exists())                          # 하위에 새로 만들지 않는다
        self.assertIn(".worklog/", (g / ".gitignore").read_text())
        ctx = json.loads(hook(sub, "hook")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | PROVIDED | root={g}]"), ctx)
        hook(sub, "turn-start")
        self.assertEqual(json.loads((g / ".worklog/sessions/claude_s1.json").read_text())["turn"], 1)
        self.assertEqual(json.loads(hook(sub, "stop-hook")[1])["decision"], "block")  # 상위 프로젝트 기록으로 판정
        self.ok(self.plain(sub, "save", payload={"type": "REQUEST", "summary": "[auto] 제목 자동: 구조 설명", "quote": "이 코드 구조 설명해 줘"}))
        self.assertEqual(len(self.events_at(g, out["id"])), 1)
        explicit = self.mk("other")
        self.ok(run(explicit, "new-work", tool="claude", extra=["t", "--quote", "q"]))  # --root가 있으면 그대로
        self.assertTrue((explicit / ".worklog/index.json").is_file())

    def events_at(self, root, wid):
        return (root / ".worklog/works" / wid / "events.jsonl").read_text().splitlines()

    def test_wl_home_is_never_auto_connected(self):
        """F01 (2.25.0): ~ whose .worklog is WL_HOME without index.json is not connected, for the hooks and the commands, even
        with auto=on and even as the git top level of a subfolder. An explicit new-work there still makes ~ a project and
        leaves WL_HOME/install.json (the user-level manifest) alone."""
        h = self.mk("home")
        wlh = h / ".worklog"
        wlh.mkdir()
        (wlh / "config.json").write_text('{"update": "off"}')                      # auto 키 없음 = on
        (wlh / "install.json").write_text('{"codex": {"version": "2.25.0", "rules_src_sha": "x"}}')
        env = {"HOME": str(h), "WL_HOME": str(wlh)}
        tree = lambda: {str(p.relative_to(wlh)): p.read_bytes() for p in wlh.rglob("*") if p.is_file()}
        before = tree()
        def quiet(cwd):
            ctx = json.loads(hook(cwd, "hook", env=env)[1])["hookSpecificOutput"]["additionalContext"]
            self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NOT_CONNECTED | root={h} | auto=on | "), ctx)
            self.assertIn("홈 폴더는 자동 연결하지 않는다.", ctx)
            self.assertNotIn("new-work", ctx)
            for cmd in ("turn-start", "stop-hook"):
                self.assertEqual(hook(cwd, cmd, env=env), (0, ""))
        quiet(h)
        self.assertIn("연결되지 않은 폴더", self.plain(h, "show", env=env)[1])
        self.assertEqual(self.ok(self.plain(h, "skip", "x", env=env))["turn"], 0)
        self.refused(self.plain(h, "use", "t", "--quote", "q", env=env), "연결되지 않은")
        self.assertEqual(self.plain(h, "save", payload={"type": "CHECKPOINT", "summary": "x"}, env=env)[0], 2)
        (h / ".git").mkdir()                                                       # git 최상위가 ~인 하위 폴더
        quiet(self.mk("home", "sub"))
        self.assertEqual(tree(), before)                                           # sessions·.lock·install.json 모두 그대로
        out = self.ok(self.plain(h, "new-work", "홈 작업", "--quote", "새 작업: 홈 작업", env=env))  # 명시 new-work: 홈을 프로젝트로
        self.assertTrue(out["connected"])
        self.assertEqual((wlh / "install.json").read_bytes(), before["install.json"])  # 사용자 매니페스트는 건드리지 않는다
        self.assertNotIn(str(wlh / "install.json"), out["connected_changed"])
        for cwd in (h, h / "sub"):                                                 # index가 있으면 기존대로 연결된다
            ctx = json.loads(hook(cwd, "hook", session="s2", env=env)[1])["hookSpecificOutput"]["additionalContext"]
            self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NO_CURRENT_WORK | root={h}]"), ctx)

    def test_hook_explicit_root_wins(self):
        """F02 (2.25.0): a hook run with --root uses that folder, not the event's cwd (the installed hooks carry no --root)."""
        a, b = self.mk("a"), self.mk("b")
        self.ok(run(a, "new-work", tool="claude", extra=["A", "--quote", "q"]))
        self.ok(run(b, "new-work", tool="claude", extra=["B", "--quote", "q"]))
        ctx = json.loads(hook(b, "hook", session="x1", extra=["--root", str(a)])[1])["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NO_CURRENT_WORK | root={a}]"), ctx)
        self.assertEqual(hook(b, "turn-start", session="x1", extra=["--root", str(a)]), (0, ""))
        res = json.loads(hook(b, "stop-hook", session="x1", extra=["--root", str(a)])[1])
        self.assertEqual(res["decision"], "block")
        self.assertIn(f"--root {a}", res["reason"])
        self.assertEqual(json.loads(session_file(a, "claude_x1").read_text())["turn"], 1)
        self.assertFalse(session_file(b, "claude_x1").exists())
        hook(b, "hook", session="x2")                                              # --root 없음: 이벤트 cwd
        self.assertTrue(session_file(b, "claude_x2").exists())
        self.assertFalse(session_file(a, "claude_x2").exists())

    def test_new_work_unwritable_folder(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores permissions")
        ro = self.mk("ro")
        ro.chmod(0o555)
        try:
            r, out = run(ro, "new-work", tool="claude", extra=["t", "--quote", "q"])
        finally:
            ro.chmod(0o755)
        self.assertEqual(r, 2, out)
        res = json.loads(out)
        self.assertEqual(res["ok"], False)
        self.assertIn("PermissionError", res["error"])
        self.assertFalse((ro / ".worklog").exists())
        self.assertEqual(hook(ro, "stop-hook"), (0, ""))                       # 미연결: Stop은 막지 않는다

    def test_off_wins_and_auto_off_keeps_connected_projects(self):
        self.ok(new_work(self.root, "t", tool="claude"))
        self.ok(run(self.root, "off", tool="claude", extra=["--quote", "워크로그 꺼"]))
        self.assertIn("| OFF |", self.ctx())                                  # 프로젝트 off > 사용자 auto
        self.ok(run(self.root, "on", tool="claude"))
        self.assertIn("| PROVIDED |", self.ctx(env=self.home(auto="off")))    # auto=off는 미연결 폴더에만 영향
        (self.d / "index.json").write_text('{"format": "worklog/2", "works": {}}')
        self.assertIn("사용자에게 작업을 지정받을 때까지 저장하지 않는다.", self.ctx(session="z", env=self.home(auto="off")))  # 빈 목록 + auto=off: 옛 안내
        self.assertIn("기존 작업이 없다.", self.ctx(session="y"))

    def test_fork_header_and_separate_session(self):
        self.ok(new_work(self.root, "t", tool="claude"))
        parent = session_file(self.root).read_bytes()
        ctx = self.ctx(session="f1", source="fork")
        self.assertTrue(ctx.startswith(f"[Worklog worklog/2 SessionStart | NO_CURRENT_WORK | root={self.root} | FORK]\n"), ctx)
        self.assertIsNone(json.loads(session_file(self.root, "claude_f1").read_text())["current_work"])
        self.assertEqual(session_file(self.root).read_bytes(), parent)         # 본 세션 파일은 그대로
        self.assertNotIn("FORK", self.ctx(session="f2", source="startup"))
        bare = self.mk("bare")
        ctx = json.loads(hook(bare, "hook", source="fork")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("| auto=on | git=no | FORK] ", ctx)

    def test_second_new_work_in_one_turn(self):
        self.ok(new_work(self.root, "A", tool="claude", force=False))
        self.refused(new_work(self.root, "B", tool="claude", force=False), "이미 new-work로 작업 a를")  # 2.26.0: 첫 연결 턴(turn 0)도 거부
        self.assertEqual(sorted(self.index()["works"]), ["a"])
        hook(self.root, "turn-start")
        self.ok(new_work(self.root, "C", tool="claude", force=False))
        self.refused(new_work(self.root, "D", tool="claude", force=False), "--force")  # 같은 턴 두 번째
        self.assertNotIn("d", self.index()["works"])
        out = self.ok(run(self.root, "new-work", tool="claude", extra=["D", "--quote", "q", "--force"]))
        self.assertEqual(out["id"], "d")
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))                # 선택한 턴: 통과
        hook(self.root, "turn-start")
        self.ok(new_work(self.root, "E", tool="claude", force=False))          # 다음 턴은 다시 된다
        self.ok(new_work(self.root, "F", tool="other", session="s2", force=False))  # 다른 세션은 따로 센다

    def call(self, fn, args, **patches):
        """An in-process command with module attributes patched (failure injection); (exit code, parsed JSON or None)."""
        buf, code = io.StringIO(), 0
        with mock.patch("sys.stdout", buf), contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(self.wl, name, value))
            try:
                fn(Namespace(**args))
            except SystemExit as e:
                code = e.code
        return code, (json.loads(buf.getvalue()) if buf.getvalue().strip() else None)

    def failing(self, name, when):
        """self.wl.<name> that raises OSError on the calls `when` picks (call number, args, kwargs → bool), else runs."""
        real, n = getattr(self.wl, name), [0]
        def fn(*a, **kw):
            n[0] += 1
            if when(n[0], a, kw):
                raise OSError(f"{name} 실패(시험)")
            return real(*a, **kw)
        return fn

    def test_new_work_retry_after_partial_failure(self):
        """F04 (나): the session marker (new_work_turn, new_work_id) is written before index.json. A retry after a failed session
        write is refused and names the work; a retry after a failed index write makes the same id, not "<id>-2"."""
        args = dict(arg="T", quote="새 작업: T", root=str(self.root), tool="codex", session="s1", force=False)
        with self.assertRaises(OSError):  # index 뒤 세션 쓰기(current_work) 실패: 작업은 index에 있다
            self.call(self.wl.cmd_new_work, args, update_session=self.failing("update_session", lambda n, a, kw: "current_work" in kw))
        self.assertEqual(list(self.index()["works"]), ["t"])
        self.refused(new_work(self.root, "T", force=False), "use t --quote")  # 재시도: 새 id를 만들지 않고 그 작업을 알려 준다
        self.assertEqual(list(self.index()["works"]), ["t"])
        other = self.mk("other")
        args["root"] = str(other)
        with self.assertRaises(OSError):  # 표식 뒤 index 쓰기 실패: 작업은 아직 없다
            self.call(self.wl.cmd_new_work, args, write_index=self.failing("write_index", lambda n, a, kw: n == 1))
        self.assertFalse((other / ".worklog/index.json").exists())
        self.assertEqual(json.loads(session_file(other, "codex_s1").read_text())["new_work_id"], "t")
        sf = session_file(other, "codex_s1")
        bad = dict(json.loads(sf.read_text()), new_work_id=7, new_work_turn="x")  # 이상한 값은 없는 것으로 읽고 손상으로 보지 않는다
        sf.write_text(json.dumps(bad))
        loaded = self.wl.load_session(other / ".worklog", "codex", "s1")
        self.assertEqual((loaded["new_work_id"], loaded["new_work_turn"], loaded["current_work"]), (None, None, None))
        sf.write_text(json.dumps(dict(bad, new_work_id="t", new_work_turn=0)))
        out = self.ok(new_work(other, "T", force=False))                        # 같은 턴 재시도는 통과하고 같은 id
        self.assertEqual((out["id"], sorted(json.loads((other / ".worklog/index.json").read_text())["works"])), ("t", ["t"]))
        self.assertEqual(self.ok(run(other, "verify", extra=["--all"]))["ok"], True)

    def test_first_connection_turn_hooks_null(self):
        """D48: in the turn that connected the folder no hook has had a session file yet: hooks are null (unknown) with a notice."""
        out = self.ok(run(self.root, "new-work", tool="claude", extra=["t", "--quote", "q"]))
        self.assertEqual(out["hooks"], {"session_start": None, "turn_start": None, "stop": None})
        self.assertNotIn("notice", out)                                         # new-work의 notice는 제약 확인 신호라 쓰지 않는다
        res = self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude"))
        self.assertEqual(res["hooks"], {"session_start": None, "turn_start": None, "stop": None})
        self.assertEqual(res["notice"], self.wl.FIRST_CONNECT_NOTICE)
        self.assertNotIn("warning", res)
        hook(self.root, "turn-start")                                           # 다음 턴: Hook이 세션 파일에 기록
        res = self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude"))
        self.assertEqual(res["hooks"], {"session_start": False, "turn_start": True, "stop": False})
        self.assertNotIn("notice", res)

    def test_home_project_install_report_is_user_scope(self):
        """The home folder as a project: its store is WL_HOME, whose install.json is the user-level manifest, so a stale copy is
        reported as a --user reinstall (2.25.0 read it as a project manifest and said --root <home>)."""
        h = self.mk("home2")
        wlh = h / ".worklog"
        wlh.mkdir()
        (wlh / "config.json").write_text('{"update": "off"}')
        (wlh / "install.json").write_text(json.dumps({"codex": {"version": "2.25.0", "rules_src_sha": "0" * 64}}))
        env = {"HOME": str(h), "WL_HOME": str(wlh)}
        self.ok(self.plain(h, "new-work", "홈", "--quote", "새 작업: 홈", tool="codex", env=env))
        w = self.ok(self.plain(h, "skip", "x", tool="codex", env=env))["warning_install"]
        self.assertIn("--user", w)
        self.assertNotIn("--root", w)

    def test_installer_root_next_matches_auto(self):
        """--root: the next step says what auto=on really does (the first request worth recording creates the work)."""
        def install(*extra, env=None):
            p = subprocess.run([sys.executable, "-B", str(INST), "--tool", "claude", "--root", str(self.root), *extra],
                               capture_output=True, text=True, env=dict(clean_env(), **(env or {})))
            self.assertEqual(p.returncode, 0, p.stdout)
            return json.loads(p.stdout)["next"]
        nxt = install("--dry-run")
        self.assertIn("첫 기록 대상 요청", nxt)
        self.assertIn("auto=on", nxt)
        self.assertIn("만들지 않았습니다", install("--dry-run", "--no-worklog-dir"))
        self.assertIn("`새 작업: <제목>`으로 작업을 만드세요", install("--dry-run", env=self.home(auto="off")))

    # --- Hook 중복 키 ---
    def test_duplicate_sessionstart_and_prompt(self):
        self.ok(new_work(self.root, "t", tool="claude"))
        self.assertIn("| PROVIDED |", self.ctx(source="startup"))
        self.assertEqual(hook(self.root, "hook", source="startup"), (0, ""))   # 같은 source가 5초 안에 다시: 무동작
        self.assertIn("| PROVIDED |", self.ctx(source="resume"))               # 다른 source는 새 SessionStart
        self.assertIn("| PROVIDED |", self.ctx())                              # source 없는 이벤트는 키가 없다(지금처럼)
        turn = lambda: json.loads(session_file(self.root).read_text())["turn"]
        for kw, want in (({"turn_id": "t1"}, 1), ({"turn_id": "t1"}, 1), ({"turn_id": "t2"}, 2),
                         ({"prompt_id": "p1"}, 3), ({"prompt_id": "p1"}, 3), ({}, 4), ({}, 5)):
            self.assertEqual(hook(self.root, "turn-start", **kw), (0, ""))
            self.assertEqual(turn(), want, kw)
        self.assertEqual(json.loads(session_file(self.root).read_text())["hook_keys"]["UserPromptSubmit"], "p1")

    def test_sessionstart_after_a_turn_is_injected_again(self):
        """F03: the same source within 5 s is a duplicate only when no turn happened in between (turn, UserPromptSubmit, Stop)."""
        self.ok(new_work(self.root, "t", tool="claude"))
        self.assertIn("| PROVIDED |", self.ctx(source="resume"))
        hook(self.root, "turn-start")                                           # 사이에 프롬프트
        self.assertIn("| PROVIDED |", self.ctx(source="resume"))                # 5초 안이라도 정상 재개: 다시 주입
        self.assertEqual(hook(self.root, "hook", source="resume"), (0, ""))   # 그 직후 중복은 무동작
        hook(self.root, "stop-hook")                                            # 사이에 Stop(차단)
        self.assertIn("| PROVIDED |", self.ctx(source="resume"))
        self.assertEqual(hook(self.root, "hook", source="resume"), (0, ""))

    def test_duplicate_stop(self):
        """A Stop that started before the session's previous Stop finished, at the turn that Stop left, is the same Stop run by a
        second registration (claude·codex run hooks in parallel). STARTED is set by hand here; sequential Stops keep 2.16.0."""
        self.ok(new_work(self.root, "t", tool="claude"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude"))
        hook(self.root, "turn-start")
        wl = self.wl
        def stop(started, **event):
            buf = io.StringIO()
            with mock.patch.object(wl, "STARTED", started), mock.patch("sys.stdin", io.StringIO(json.dumps(dict(cwd=str(self.root), session_id="s1", **event)))), \
                    mock.patch("sys.stdout", buf):
                wl.cmd_stop_hook(Namespace(tool="claude", root=str(self.root), session=None))
            return buf.getvalue()
        sess = lambda: json.loads(session_file(self.root).read_text())
        self.assertEqual(json.loads(stop(time.time()))["decision"], "block")
        self.assertEqual((stop(0.0), sess()["turn"], sess()["blocked_turn"]), ("", 1, 1))     # 중복: 차단을 풀지 않는다
        self.assertEqual(stop(time.time(), stop_hook_active=True), "")
        self.assertEqual(sess()["turn"], 2)                                                     # 한 번 막힌 뒤 Stop: 통과, 턴 진행
        self.assertEqual((stop(0.0, stop_hook_active=True), sess()["turn"]), ("", 2))           # 그 중복은 턴을 또 넘기지 않는다
        self.assertEqual(json.loads(stop(time.time()))["decision"], "block")                    # 차례로 온 다음 Stop은 판정(2.16.0)
        self.assertEqual(json.loads(hook(self.root, "stop-hook", stop_hook_active=True)[1] or "{}"), {})

    # --- reassign · rename (§4-5) ---
    def two_works(self):
        self.ok(new_work(self.root, "A"))
        self.ok(new_work(self.root, "B"))
        self.used(use(self.root, "b"), "b")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "b1", "quote": "b 요청", "decisions": [{"text": "b 고유 결정"}]}))
        self.used(use(self.root, "a"), "a")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a1", "quote": "3장까지, 게시 금지", "decisions": [{"text": "3장까지"}],
                                        "constraints": ["게시 금지"]}))
        (self.root / "note.md").write_text("3장까지 표로 정리한다.")
        self.ok(run(self.root, "save", {"type": "D_USER", "summary": "a2", "quote": "표로", "decisions": [{"text": "표로 정리", "source": "model"}],
                                        "artifacts": [{"path": "note.md"}], "check": {"D1": "'3장까지 표로'", "D2": "'표로 정리한다'", "C1": "미반영: 게시 안 함"}}))
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a3", "constraints": ["외부 공유 금지"]}))

    def test_reassign_moves_decisions_and_constraints(self):
        self.two_works()
        before = (self.d / "works/a/events.jsonl").read_bytes()
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "그거 B 작업이야"]))
        self.assertEqual((out["misfiled"], out["refiled"], out["current_work"]), ("E0004", "E0002", "b"))
        self.assertEqual(out["moved"], {"decisions": ["D1", "D2"], "constraints": ["C1"], "artifacts": ["note.md"]})
        a, b = self.state("a"), self.state("b")
        self.assertEqual(a["decisions"], [])                                                    # 잘못된 작업의 현황에서 사라진다
        self.assertEqual([c["text"] for c in a["constraints"]], ["외부 공유 금지"])               # 범위 밖 사건의 제약은 그대로
        self.assertEqual([(x["id"], x["text"], x["source"]) for x in b["decisions"]],
                         [("D1", "b 고유 결정", "user"), ("D2", "3장까지", "user"), ("D3", "표로 정리", "model")])  # 새 id, 출처 유지
        self.assertEqual([(x["id"], x["text"], x["source"]) for x in b["constraints"]], [("C1", "게시 금지", "user")])
        self.assertEqual([x["path"] for x in b["artifacts"]], ["note.md"])
        self.assertTrue((self.d / "works/a/events.jsonl").read_bytes().startswith(before))      # 원본 사건은 그대로
        ea, eb = self.events("a")[-1], self.events("b")[-1]
        self.assertEqual((ea["type"], ea["summary"], ea["quote"]), ("CORRECTION", "[misfiled → b] E0001-E0002", "그거 B 작업이야"))
        self.assertIn({"kind": "refiled_to", "work": "b", "id": "E0002"}, ea["refs"])
        self.assertEqual([r["id"] for r in ea["refs"] if r["kind"] == "misfiled"], ["E0001", "E0002"])
        self.assertEqual(eb["summary"], "[refiled ← a] E0001-E0002")
        self.assertEqual([r["kind"] for r in eb["refs"]], ["refiled_from", "refiled_from"])     # 2.26.0: 맞는 작업이 먼저, a의 기존 사건만 가리킨다
        self.assertIn({"kind": "refiled_from", "work": "a", "id": "E0001", "quote": "3장까지, 게시 금지"}, eb["refs"])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)
        self.assertIn("[모델]", (self.d / "works/b/state.md").read_text())
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "b 이어감"}))           # 현재 작업 b, 읽은 것으로 침
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "다시"]), "이미 옮겼습니다")
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0009", "--quote", "q"]), "작업에 없는 사건")
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0001"]), "사용자 원문")
        self.refused(run(self.root, "reassign", extra=["a", "a", "--events", "E0001", "--quote", "q"]), "같습니다")

    def test_reassign_refused_after_refiled_elsewhere(self):
        """An event already refiled a → b is not refiled again a → c (that would leave an empty correction pair)."""
        self.two_works()
        self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "B야"]))
        self.ok(new_work(self.root, "C"))
        a_before = (self.d / "works/a/events.jsonl").read_bytes()
        self.refused(run(self.root, "reassign", extra=["a", "c", "--events", "E0002", "--quote", "아니 C야"]), "이미 b로 옮긴 사건입니다: E0002")
        self.refused(run(self.root, "reassign", extra=["a", "c", "--events", "E0002-E0003", "--quote", "C야"]), "show --work b")
        self.assertEqual((self.d / "works/a/events.jsonl").read_bytes(), a_before)
        self.assertFalse((self.d / "works/c/events.jsonl").exists() and (self.d / "works/c/events.jsonl").read_text())
        out = self.ok(run(self.root, "reassign", extra=["a", "c", "--events", "E0003", "--quote", "그건 C야"]))  # 안 옮긴 사건은 된다
        self.assertEqual(out["moved"]["constraints"], ["C2"])
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "다시"]), "이미 옮겼습니다")  # 같은 쪽: 기존 동작

    def reassign(self, events="E0001", quote="B야", wrong="a", right="b", **patches):
        return self.call(self.wl.cmd_reassign, dict(arg=wrong, arg2=right, events=events, quote=quote, root=str(self.root),
                                                    tool="codex", session="s1"), **patches)

    def test_reassign_partial_then_retry(self):
        """F05: the right work's write fails before its append, another session writes to it, the same command again: a's
        refiled_to names the id the refiled event really got (2.25.0 kept a predicted id)."""
        self.two_works()
        code, res = self.reassign(commit=self.failing("commit", lambda n, a, kw: n == 1))
        self.assertEqual(code, 2)
        self.assertEqual((res["ok"], res["partial"], res["done"], res["refiled"], res["misfiled"]), (False, True, [], None, None))
        self.assertIn("같은 reassign 명령", res["next"])
        self.assertEqual((len(self.events("a")), len(self.events("b"))), (3, 1))  # 아무 쪽에도 쓰지 않았다
        run(self.root, "show", session="s2", extra=["--work", "b"])
        self.ok(run(self.root, "save", {"work": "b", "type": "CHECKPOINT", "summary": "다른 세션의 b 기록"}, session="s2"))
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]))
        self.assertEqual((out["refiled"], out["misfiled"]), ("E0003", "E0004"))
        self.assertNotIn("resumed", out)
        self.assertIn({"kind": "refiled_to", "work": "b", "id": "E0003"}, self.events("a")[-1]["refs"])
        self.assertEqual(self.events("b")[2]["summary"], "[refiled ← a] E0001")
        self.assertEqual(self.state("a")["decisions"][0]["text"], "표로 정리")                  # E0001의 D1만 빠졌다
        self.assertEqual([x["text"] for x in self.state("b")["decisions"]], ["b 고유 결정", "3장까지"])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)

    def test_reassign_resumes_missing_steps(self):
        """F06: a failure after the right work's append (projection), and a failure of the last session write: each run reports
        the steps on disk (done) and the same command does only the missing ones; the ledgers get one event each."""
        self.two_works()
        code, res = self.reassign(project=self.failing("project", lambda n, a, kw: n == 1))   # b 원장은 썼고 투영에서 실패
        self.assertEqual((code, res["partial"], res["done"], res["refiled"], res["misfiled"]), (2, True, ["refiled"], "E0002", None))
        self.assertEqual(self.state("b")["seq"], 1)                                                # 투영은 옛 상태
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]))
        self.assertEqual((out["refiled"], out["misfiled"], out["resumed"], out["current_work"]), ("E0002", "E0004", ["refiled"], "b"))
        self.assertIn({"kind": "refiled_to", "work": "b", "id": "E0002"}, self.events("a")[-1]["refs"])
        self.assertEqual((self.state("b")["seq"], self.index()["works"]["b"]["last_seq"]), (2, 2))  # b 투영·index 복구
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]), "이미 옮겼습니다")
        code, res = self.reassign(events="E0003", update_session=self.failing("update_session", lambda n, a, kw: "current_work" in kw))
        self.assertEqual((code, res["done"]), (2, ["refiled", "refiled_state", "misfiled", "misfiled_state"]))
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0003", "--quote", "B야"]))
        self.assertEqual(out["resumed"], ["refiled", "refiled_state", "misfiled", "misfiled_state"])
        self.assertEqual(([e["type"] for e in self.events("a")].count("CORRECTION"), [e["type"] for e in self.events("b")].count("CORRECTION")), (2, 2))
        self.assertEqual(json.loads((self.d / "sessions/codex_s1.json").read_text())["current_work"], "b")
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0003", "--quote", "B야"]), "이미 옮겼습니다")

    def test_reassign_refuses_refiled_elsewhere_before_misfiled_mark(self):
        """A run that stopped after writing the right work (no misfiled mark in a yet) still blocks refiling those events to a
        third work: the refusal reads every work's refiled_from refs."""
        self.two_works()
        self.ok(new_work(self.root, "C"))
        code, res = self.reassign(commit=self.failing("commit", lambda n, a, kw: n == 2))   # b는 끝, a 쓰기에서 실패
        self.assertEqual((code, res["done"]), (2, ["refiled", "refiled_state"]))
        a_before = (self.d / "works/a/events.jsonl").read_bytes()
        self.refused(run(self.root, "reassign", extra=["a", "c", "--events", "E0001", "--quote", "아니 C야"]), "이미 b로 옮긴 사건입니다: E0001(b E0002)")
        self.assertEqual((self.d / "works/a/events.jsonl").read_bytes(), a_before)
        self.assertFalse((self.d / "works/c/events.jsonl").exists())
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]))  # 같은 쪽은 이어서 끝낸다
        self.assertEqual((out["misfiled"], out["refiled"], out["resumed"]), ("E0004", "E0002", ["refiled", "refiled_state"]))

    def test_reassign_keeps_user_source_over_same_model_text(self):
        """F07: same text in the right work — same source: skipped; incoming user over existing model: the model item is removed
        and the text added as user (upgraded); incoming model over existing user: skipped."""
        self.ok(new_work(self.root, "A"))
        self.ok(new_work(self.root, "B"))
        self.used(use(self.root, "b"), "b")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "b1", "decisions": [{"text": "3장까지"}],
                                        "constraints": ["게시 금지", "외부 공유 금지"]}))                     # b의 [모델] 항목
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "b2", "quote": "표로", "decisions": [{"text": "표로 정리"}]}))  # b의 [사용자]
        self.used(use(self.root, "a"), "a")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a1", "quote": "3장까지, 게시 금지", "decisions": [{"text": "3장까지"}],
                                        "constraints": ["게시 금지"]}))                                       # a의 [사용자]
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "a2", "decisions": [{"text": "표로 정리"}],
                                        "constraints": ["외부 공유 금지"]}))                                  # a의 [모델]
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "B 작업이야"]))
        self.assertEqual(sorted(out["upgraded"]), ["3장까지", "게시 금지"])
        self.assertEqual(sorted(out["already_there"]), ["외부 공유 금지", "표로 정리"])
        b = self.state("b")
        self.assertEqual(sorted((x["text"], x["source"]) for x in b["decisions"]), [("3장까지", "user"), ("표로 정리", "user")])
        self.assertEqual(sorted((x["text"], x["source"]) for x in b["constraints"]), [("게시 금지", "user"), ("외부 공유 금지", "model")])
        changes = self.events("b")[-1]["changes"]
        self.assertEqual((list(changes["decisions_remove"]), list(changes["constraints_remove"])), (["D1"], ["C1"]))
        self.assertEqual([c["text"] for c in self.state("a")["constraints"]], [])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)

    def test_reassign_corrects_a_2_25_0_predicted_ref(self):
        """F05 remainder: a 2.25.0 partial run left a's [misfiled → b] naming a predicted b id; another session wrote that id in b.
        2.26.0 writes the refiled event and one more CORRECTION in a that names the real id (corrected_ref), the ledger lines stay."""
        self.two_works()
        wl, d = self.wl, self.d
        with wl.locked(d):                                                          # 2.25.0이 남긴 partial: a만 기록, 예측 번호 b:E0002
            index = wl.index_or_new(d)
            events, prev = wl.read_events(wl.work_dir(d, "a"))
            refs = [{"kind": "misfiled", "id": "E0001"}, {"kind": "refiled_to", "work": "b", "id": "E0002"}]
            changes = {"decisions_remove": {"D1": "b로 옮김(reassign)"}, "constraints_remove": {"C1": "b로 옮김(reassign)"}}
            ev = dict(wl.new_event(events, prev, "CORRECTION", "codex", "s1", "[misfiled → b] E0001", "B야", refs, changes), core="2.25.0")
            wl.commit(d, index, "a", ev)
        run(self.root, "show", session="s2", extra=["--work", "b"])
        self.ok(run(self.root, "save", {"work": "b", "type": "CHECKPOINT", "summary": "다른 세션이 b:E0002를 씀"}, session="s2"))
        before = (self.d / "works/a/events.jsonl").read_bytes()
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]))
        self.assertEqual((out["refiled"], out["misfiled"], out["corrected_ref"], out["ref_correction"]), ("E0003", "E0004", True, "E0005"))
        self.assertTrue((self.d / "works/a/events.jsonl").read_bytes().startswith(before))   # 원장 불변, 정정 사건만 추가
        fix = self.events("a")[-1]
        self.assertEqual((fix["type"], fix["summary"], fix["changes"]), ("CORRECTION", "[misfiled → b] 대상 정정 E0004", {}))
        self.assertEqual(fix["refs"], [{"kind": "corrects", "id": "E0004"}, {"kind": "refiled_to", "work": "b", "id": "E0003"}])
        self.assertIn({"kind": "correction", "work": "a", "id": "E0004"}, self.events("b")[2]["refs"])
        self.assertEqual([x["text"] for x in self.state("b")["decisions"]], ["b 고유 결정", "3장까지"])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]), "이미 옮겼습니다")

    def test_reassign_session_step_needs_current_work(self):
        """F06 remainder: reading b (show --work b) does not finish the session step; current_work must be b. After a finished run,
        a work the user selects later is kept: the re-run is refused and current_work is not taken back."""
        sess = lambda: json.loads((self.d / "sessions/codex_s1.json").read_text())
        self.two_works()                                                            # 재현 A: b 투영 실패 → show --work b → 재실행
        self.assertEqual(self.reassign(project=self.failing("project", lambda n, a, kw: n == 1))[1]["done"], ["refiled"])
        run(self.root, "show", extra=["--work", "b"])
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0001", "--quote", "B야"]))
        self.assertEqual((out["current_work"], sess()["current_work"]), ("b", "b"))
        self.assertNotIn("session", out["resumed"])
        code, res = self.reassign(events="E0003", update_session=self.failing("update_session", lambda n, a, kw: "current_work" in kw))
        self.assertEqual(code, 2)                                                   # 재현 B: 마지막 세션 쓰기 실패 → show → 재실행
        self.used(use(self.root, "a", quote="a 보자"), "a")
        run(self.root, "show", extra=["--work", "b"])
        out = self.ok(run(self.root, "reassign", extra=["a", "b", "--events", "E0003", "--quote", "B야"]))
        self.assertEqual(sess()["current_work"], "b")
        self.assertIn("misfiled_state", out["resumed"])
        self.used(use(self.root, "a", quote="이제 a 작업"), "a")                   # 끝난 뒤 사용자가 다른 작업을 고름
        self.refused(run(self.root, "reassign", extra=["a", "b", "--events", "E0003", "--quote", "B야"]), "이미 옮겼습니다")
        self.assertEqual(sess()["current_work"], "a")                              # 되돌리지 않는다

    def test_reassign_selection_user_source_wins(self):
        """F07 remainder: the moved decisions hold the same text as model and as user (a replaces): b gets it once, as user, in
        either order."""
        for first, second in (("D_AGENT", "D_USER"), ("D_USER", "D_AGENT")):
            root = Path(tempfile.mkdtemp())
            self.ok(new_work(root, "A"))
            self.ok(new_work(root, "B"))
            self.used(use(root, "a"), "a")
            self.ok(run(root, "save", {"type": first, "summary": "one", "quote": "q", "decisions": [{"text": "same"}, {"text": "different"}]}))
            self.ok(run(root, "save", {"type": second, "summary": "two", "quote": "q", "decisions": [{"text": "same", "replaces": "D2"}]}))
            out = self.ok(run(root, "reassign", extra=["a", "b", "--events", "E0001-E0002", "--quote", "B"]))
            b = json.loads((root / ".worklog/works/b/state.json").read_text())
            self.assertEqual([(x["text"], x["source"]) for x in b["decisions"]], [("same", "user")], first)
            self.assertNotIn("already_there", out)
            self.assertEqual(json.loads((root / ".worklog/works/a/state.json").read_text())["decisions"], [])

    def test_reassign_refuses_when_another_ledger_is_unreadable(self):
        """N02: a ledger that cannot be read is not an empty history: the refusal names that work and writes nothing."""
        self.two_works()
        self.ok(new_work(self.root, "C"))
        self.assertEqual(self.reassign(commit=self.failing("commit", lambda n, a, kw: n == 2))[1]["done"], ["refiled", "refiled_state"])
        with open(self.d / "works/b/events.jsonl", "a") as f:
            f.write("BROKEN\n")
        a_before = (self.d / "works/a/events.jsonl").read_bytes()
        self.refused(run(self.root, "reassign", extra=["a", "c", "--events", "E0001", "--quote", "C"]), "작업 b의 원장을 읽을 수 없어")
        self.assertEqual((self.d / "works/a/events.jsonl").read_bytes(), a_before)
        self.assertFalse((self.d / "works/c/events.jsonl").exists())

    def test_not_connected_refusals_and_empty_show(self):
        """D61: use·rename·reassign·on·off refuse with show's NOT_CONNECTED text; show with no works gives the SessionStart text."""
        bare = self.mk("bare")
        for argv, event in ((["use", "t", "--quote", "q"], "use"), (["rename", "t", "x", "--quote", "q"], "rename"),
                            (["reassign", "a", "b", "--events", "E0001", "--quote", "q"], "reassign"), (["on"], "on"),
                            (["off", "--quote", "q"], "off")):
            err = json.loads(self.plain(bare, *argv)[1])["error"]
            self.assertTrue(err.startswith(f"Worklog에 연결되지 않은 폴더입니다({bare}에 .worklog 없음).\n[Worklog worklog/2 {event} | NOT_CONNECTED | "
                                           f"root={bare} | auto=on | git=no] "), err)
            self.assertIn("new-work", err)
        empty = self.mk("empty", records=True)
        self.assertIn(self.wl.EMPTY_GUIDE, self.plain(empty, "show")[1])
        self.assertIn(self.wl.NO_WORK_GUIDE, self.plain(empty, "show", env=self.home(auto="off"))[1])

    def test_rename_title_only(self):
        self.ok(new_work(self.root, "Habit"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "decisions": [{"text": "7분"}]}))
        before = (self.d / "works/habit/events.jsonl").read_bytes()
        out = self.ok(run(self.root, "rename", extra=["habit", "습관 계획", "--quote", "제목은 습관 계획으로"]))
        self.assertEqual((out["work"], out["title"], out["old_title"], out["saved"]), ("habit", "습관 계획", "Habit", "E0002"))
        self.assertEqual(self.index()["works"]["habit"]["title"], "습관 계획")
        self.assertEqual(sorted(self.index()["works"]), ["habit"])                              # id 그대로
        self.assertTrue((self.d / "works/habit/events.jsonl").read_bytes().startswith(before))  # 해시 체인: 앞 줄 불변
        last = self.events("habit")[-1]
        self.assertEqual((last["type"], last["summary"], last["changes"]), ("CHANGE", "제목 변경: Habit → 습관 계획", {}))
        self.assertIn("habit · 습관 계획", (self.d / "works/habit/state.md").read_text())
        self.assertEqual([d["text"] for d in self.state("habit")["decisions"]], ["7분"])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)
        self.refused(run(self.root, "rename", extra=["habit", "습관 계획", "--quote", "q"]), "이미")
        self.refused(run(self.root, "rename", extra=["habit", "새 제목"]), "사용자 원문")
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "이어감"}))            # 읽던 세션은 계속 저장

    # --- 규칙 블록 1단계 (PLAN-block-size §7) ---
    def test_rules_items_kept_and_save_help_dedup(self):
        lines = (WL.parents[1] / "adapters/rules.md").read_text().split("\n")
        have = {hashlib.sha256(l.encode()).hexdigest()[:16] for l in lines}
        for n, h in self.RULES_2_24_2.items():
            self.assertEqual(h in have, n not in self.REPLACED, f"2.24.2 rules.md {n}행")  # 교체한 두 줄 외에는 글자 하나 바뀌지 않았다
        text = "\n".join(lines)
        for part in ("`auto=on`이면 첫 기록 대상 요청", "④ 기존 작업이 하나도 없으면", "`reassign <잘못된 id> <맞는 id>", "`| FORK`가 보이면",
                     '"기록하지 마"·"워크로그 꺼"는 `off --quote', "`기록: <id> 새 작업으로 시작(제목 자동)`"):
            self.assertIn(part, text)
        wl = self.wl
        for gone in ("위임한 턴은 첫머리에", "지금 고른 방법·범위", "모델이 제안한 것은 사용자 발언과 같은 save에", "계속 지킬 금지·자료 범위만",
                     '"다음 요청까지 작성 보류"처럼', '"파일은 만들지 마"·"두 줄로 답해"', "운영 지시(도구·서브에이전트", "그런 인용은 결과의 self_quoted",
                     "제약 문장을 본문에 옮겨 적지 않는다", "기록이 바뀌었습니다", "소스 코드를 읽을 필요는 없다", "작업 선택 — 사용자가 지정한다"):
            self.assertNotIn(gone, wl.SAVE_HELP)                                                # 규칙과 겹치는 9줄·거부 처리·명령 목록
        tail = wl.SAVE_HELP.split("\n}\n", 1)[1].split("\n")
        self.assertEqual(len(tail), 4)
        self.assertTrue(tail[-1].startswith("명령: works(JSON 목록) · use <id> --quote · new-work"))  # 명령 목록 한 줄
        for back in ("id는 제목의 영문·숫자 슬러그, 한글만·숫자만이면 work·work-2", "show [--work <id>](현재 작업이 없으면 목록)",
                     "archive/reopen <id>(COMPLETED/ACTIVE로)", '"artifacts_moved": {'):           # 2.26.0 (F09): 되살린 안내
            self.assertIn(back, wl.SAVE_HELP)
        r, out = run(self.root, "help")
        self.assertEqual(out, f"worklog core {wl.VERSION} (format worklog/2)\n{wl.SAVE_HELP}\n")
        spec = importlib.util.spec_from_file_location("inst_rules", INST)
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)
        block = inst.rules("claude")
        self.assertIn(wl.SAVE_HELP.split("\n", 1)[1], block)                                    # 코어 help와 설치 블록의 {FORMAT}이 같다
        self.assertEqual(block.count("python3 -B wl.py"), 0)


class LongLedgerTest(unittest.TestCase):
    """TEST-SPEC-3 U1: 긴 원장(사건 40+)에서 결정 교체 사슬·산출물 요약·출처별 해제·COMPLETED 뒤 새 작업·주입 크기."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.d = self.root / ".worklog"

    def ok(self, result):
        r, out = result
        self.assertEqual(r, 0, out)
        return json.loads(out)

    def save(self, payload, session="s1"):
        return self.ok(run(self.root, "save", payload, session=session, tool="claude"))

    def test_long_ledger_consistency(self):
        self.ok(new_work(self.root, "long", tool="claude"))
        self.save({"type": "REQUEST", "summary": "시작", "quote": "주간 계획을 세워", "goal": "주간 계획",
                   "constraints": ["알림 등록 금지", "외부 게시 금지", "다른 프로젝트 자료 조회 금지"], "decisions": [{"text": "1화까지"}]})
        prev = "D1"
        for n in range(2, 8):  # 결정 교체 6회 연속
            self.save({"type": "D_USER", "summary": f"{n}화", "quote": f"{n}화까지", "decisions": [{"text": f"{n}화까지", "replaces": prev}]})
            prev = f"D{n}"
        self.save({"type": "RESULT", "summary": "모델 제약", "constraints": ["모델이 읽은 조건"]})
        for i in range(28):
            self.save({"type": "CHECKPOINT", "summary": f"진행 {i}"})
        arts = []
        for ep in (1, 2):  # 산출물 20개, 폴더 2개
            (self.root / f"out/EP0{ep}").mkdir(parents=True)
            for i in range(10):
                p = self.root / f"out/EP0{ep}/c{i}.md"
                p.write_text(f"7화까지 진행한다. 알림을 등록하지 않는다. 외부에 게시하지 않는다. 다른 프로젝트 자료를 조회하지 않는다. "
                             f"모델이 읽은 조건을 지킨다. 컷 {ep}-{i}")
                arts.append({"path": f"out/EP0{ep}/c{i}.md"})
        out = self.save({"type": "RESULT", "summary": "20개", "artifacts": arts,
                         "check": {"D7": "'7화까지 진행한다'", "C1": "'알림을 등록하지 않는다'", "C2": "'외부에 게시하지 않는다'",
                                   "C3": "'다른 프로젝트 자료를 조회하지 않는다'", "C4": "'모델이 읽은 조건을 지킨다'"}})
        self.assertEqual((out["self_quoted"], out["unreflected"]), ([], []))
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "z", "constraints_remove": {"C1": "불편"}}, tool="claude")
        self.assertEqual(r, 2, out)  # [사용자] 제약은 사유만으로 해제되지 않는다
        self.save({"type": "RESULT", "summary": "모델 해제", "constraints_remove": {"C4": "조건 종료"}})
        self.save({"type": "D_USER", "summary": "사용자 해제", "quote": "알림은 이제 등록해도 돼", "constraints_remove": {"C1": "사용자 해제"}})
        self.save({"type": "D_USER", "summary": "끝", "quote": "이 작업은 끝났어", "status": "COMPLETED"})
        events = (self.d / "works/long/events.jsonl").read_text().splitlines()
        self.assertGreaterEqual(len(events), 40)
        s = json.loads((self.d / "works/long/state.json").read_text())
        self.assertEqual([x["id"] for x in s["decisions"]], ["D7"])
        self.assertEqual([x["id"] for x in s["constraints"]], ["C2", "C3"])
        self.assertEqual((s["status"], len(s["artifacts"]), len(s["superseded"]), len(s["removed_constraints"])), ("COMPLETED", 20, 6, 2))
        md = (self.d / "works/long/state.md").read_text()
        for text in ("현재 범위(최신 결정): D7: 7화까지", "## 산출물 — 20개, 폴더별 요약", "- out/EP01/ · 10개", "대체된 결정 6개·해제된 제약 2개"):
            self.assertIn(text, md)
        self.assertTrue(self.ok(run(self.root, "verify", extra=["--all"], tool="claude"))["ok"])
        r, out = run(self.root, "show", extra=["--work", "long"], tool="claude")
        self.assertEqual(r, 0, out)
        self.assertFalse(out.startswith("(현재 상태가 원장과"), "projection이 원장과 달라 다시 만들어졌다")
        ctx = json.loads(hook(self.root, "hook", session="s1")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("## 현재 작업: long", ctx)
        self.assertLessEqual(len(ctx.encode()), 8192, f"현재 작업 주입 {len(ctx.encode())}B")
        self.ok(new_work(self.root, "next", session="s2", tool="claude"))
        ctx = json.loads(hook(self.root, "hook", session="fresh")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("- 그 외 COMPLETED 1개: long · long (", ctx)
        self.assertLessEqual(len(ctx.encode()), 8192)


if __name__ == "__main__":
    unittest.main()


class FinalPlanTest(unittest.TestCase):
    """2026-10-09 최종안: check 자기 인용 표시·비텍스트 산출물, Hook 자가 진단, 출처별 해제, goal·id 정리, COMPLETED 목록, 산출물 요약."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.d = self.root / ".worklog"

    def ok(self, result):
        r, out = result
        self.assertEqual(r, 0, out)
        return json.loads(out)

    def state(self, wid="t"):
        return json.loads((self.d / f"works/{wid}/state.json").read_text())

    def test_self_quoted_is_flagged_not_rejected(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["알림 등록 금지"],
                                        "decisions": [{"text": "저녁 식사 후 11분"}]}))
        (self.root / "a.md").write_text("규칙: 알림 등록 금지.\n저녁 식사 후 11분 동안 적는다.")
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": "a.md"}],
                                              "check": {"D1": "'11분 동안 적는다'", "C1": "'알림 등록 금지'"}}))
        self.assertEqual((out["self_quoted"], out["unreflected"]), (["C1"], []))  # 규칙 문장 그대로 = 증거 아님, 저장은 된다
        ev = json.loads((self.d / "works/t/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["self_quoted"], ["C1"])
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s2", "artifacts": [{"path": "a.md"}],
                                              "check": {"D1": "'11분 동안 적는다'", "C1": "미반영: 알림은 만들지 않았음"}}))
        self.assertEqual((out["self_quoted"], out["unreflected"]), ([], ["C1"]))

    def test_artifacts_moved(self):
        """D49 (2.26.0): save artifacts_moved {"old": "new"} replaces the recorded path in place (hash and event from this save),
        so artifacts_missing stops naming the old path. The new file must exist and the old path must be recorded."""
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]}))
        (self.root / "note.md").write_text("메모 본문입니다.")
        (self.root / "b.md").write_text("다른 산출물")
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": "note.md"}, {"path": "b.md"}],
                                        "check": {"C1": "미반영: 게시는 하지 않음"}}))
        (self.root / "docs").mkdir()
        os.replace(self.root / "note.md", self.root / "docs/note.md")
        self.assertEqual(self.ok(run(self.root, "skip", extra=["x"]))["artifacts_missing"], ["note.md(E0002)"])
        for moved, text in (({"note.md": "docs/none.md"}, "새 경로의 파일이 없습니다"), ({"x.md": "docs/note.md"}, "산출물 목록에 없는 경로"),
                            ({"note.md": "note.md"}, "같습니다"), (["note.md"], "artifacts_moved는")):
            r, out = run(self.root, "save", {"type": "CHECKPOINT", "summary": "옮김", "artifacts_moved": moved})
            self.assertEqual(r, 2, out)
            self.assertIn(text, json.loads(out)["error"])
        out = self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "옮김", "artifacts_moved": {"note.md": "docs/note.md"}}))
        self.assertNotIn("artifacts_missing", out)                                  # 체크 인용 없이 저장된다(이동은 새 산출물이 아님)
        digest = hashlib.sha256((self.root / "docs/note.md").read_bytes()).hexdigest()
        self.assertEqual(self.state()["artifacts"], [{"path": "docs/note.md", "sha256": digest, "event": "E0003"},
                                                     {"path": "b.md", "sha256": hashlib.sha256("다른 산출물".encode()).hexdigest(), "event": "E0002"}])
        ev = json.loads((self.d / "works/t/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["changes"]["artifacts_moved"], {"note.md": {"path": "docs/note.md", "sha256": digest}})
        self.assertIn("docs/note.md", (self.d / "works/t/state.md").read_text())
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["ok"], True)
        self.assertNotIn("artifacts_missing", self.ok(run(self.root, "skip", extra=["x"])))

    def test_artifacts_moved_whole_mapping(self):
        """N01: the mapping is applied at once to the list before the move, whatever the key order; two moves to one path, a new
        path that is an unmoved artifact, and a cycle (swap) are refused before the append."""
        def setup():
            root = Path(tempfile.mkdtemp())
            self.ok(new_work(root, "t"))
            for name, text in (("a.md", "A"), ("b.md", "B"), ("x.md", "X")):
                (root / name).write_text(text)
            self.ok(run(root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": p} for p in ("a.md", "b.md", "x.md")]}))
            return root
        h = lambda text: hashlib.sha256(text.encode()).hexdigest()
        arts = lambda root: [(x["path"], x["sha256"]) for x in json.loads((root / ".worklog/works/t/state.json").read_text())["artifacts"]]
        for order in (("a.md", "b.md"), ("b.md", "a.md")):
            root = setup()                                                          # 연쇄: b→c, a→b
            os.replace(root / "b.md", root / "c.md")
            os.replace(root / "a.md", root / "b.md")
            chain = {"a.md": "b.md", "b.md": "c.md"}
            self.ok(run(root, "save", {"type": "CHECKPOINT", "summary": "chain", "artifacts_moved": {k: chain[k] for k in order}}))
            self.assertEqual(arts(root), [("b.md", h("A")), ("c.md", h("B")), ("x.md", h("X"))], order)
            self.assertTrue(self.ok(run(root, "verify", extra=["--all"]))["ok"])
            root = setup()                                                          # 교환(순환): 거부
            swap = {"a.md": "b.md", "b.md": "a.md"}
            r, out = run(root, "save", {"type": "CHECKPOINT", "summary": "swap", "artifacts_moved": {k: swap[k] for k in order}})
            self.assertEqual(r, 2, out)
            self.assertIn("순환", json.loads(out)["error"])
            self.assertEqual(len((root / ".worklog/works/t/events.jsonl").read_text().splitlines()), 1)
            (root / "d").mkdir()                                                    # 독립 이동 두 개
            os.replace(root / "a.md", root / "d/a.md")
            os.replace(root / "x.md", root / "d/x.md")
            two = {"a.md": "d/a.md", "x.md": "d/x.md"}
            keys = ("a.md", "x.md") if order[0] == "a.md" else ("x.md", "a.md")
            self.ok(run(root, "save", {"type": "CHECKPOINT", "summary": "two", "artifacts_moved": {k: two[k] for k in keys}}))
            self.assertEqual(arts(root), [("d/a.md", h("A")), ("b.md", h("B")), ("d/x.md", h("X"))], order)
        root = setup()
        for moved, text in (({"a.md": "x.md"}, "옮기지 않는 기존 산출물"), ({"a.md": "n.md", "b.md": "n.md"}, "겹칩니다")):
            (root / "n.md").write_text("N")
            r, out = run(root, "save", {"type": "CHECKPOINT", "summary": "bad", "artifacts_moved": moved})
            self.assertEqual(r, 2, out)
            self.assertIn(text, json.loads(out)["error"])

    def test_non_text_artifacts_need_no_quote(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["폭력 과장 금지"]}))
        (self.root / "ep.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)))
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "그림", "artifacts": [{"path": "ep.png"}]}))  # check 생략 가능
        self.assertEqual(out["unreflected"], [])
        self.assertEqual(len(self.state()["artifacts"]), 1)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "그림 2", "artifacts": [{"path": "ep.png"}], "check": {"C1": "'폭력'"}})
        self.assertEqual(r, 2)
        self.assertIn("비텍스트", json.loads(out)["error"])
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "그림 3", "artifacts": [{"path": "ep.png"}],
                                              "check": {"C1": "미반영: 그림이라 인용 불가"}}))
        self.assertEqual(out["unreflected"], ["C1"])
        (self.root / "note.md").write_text("폭력 장면은 실루엣으로 처리했다.")
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "둘", "artifacts": [{"path": "ep.png"}, {"path": "note.md"}]})
        self.assertEqual(r, 2)  # 텍스트 산출물이 하나라도 있으면 check 필수
        self.assertIn("산출물 대조 누락", json.loads(out)["error"])

    def test_decision_source_model_in_user_event(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q",
                                        "decisions": [{"text": "11분"}, {"text": "3·5·3분 배분(모델 제안)", "source": "model"}]}))
        s = self.state()
        self.assertEqual([(d["id"], d["source"]) for d in s["decisions"]], [("D1", "user"), ("D2", "model")])
        md = (self.d / "works/t/state.md").read_text()
        self.assertIn("- D1: 11분 [사용자]", md)
        self.assertIn("- D2: 3·5·3분 배분(모델 제안) [모델]", md)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "y", "decisions": [{"text": "z", "source": "user"}]})
        self.assertEqual(r, 2)  # 모델 사건에서 사용자 출처를 꾸밀 수 없다
        self.assertIn('"model"만', json.loads(out)["error"])

    def test_constraint_source_and_release_rule(self):
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["사용자 제약"]}))
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "y", "constraints": ["모델이 읽은 조건"],
                                        "decisions": [{"text": "3컷씩 나눔"}]}))
        s = self.state()
        self.assertEqual([(c["id"], c["source"]) for c in s["constraints"]], [("C1", "user"), ("C2", "model")])
        self.assertEqual(s["decisions"][0]["source"], "model")
        md = (self.d / "works/t/state.md").read_text()
        self.assertIn("- C1: 사용자 제약 [사용자]", md)
        self.assertIn("- C2: 모델이 읽은 조건 [모델]", md)
        self.assertIn("- D1: 3컷씩 나눔 [모델]", md)
        r, out = run(self.root, "save", {"type": "RESULT", "summary": "z", "constraints_remove": {"C1": "불편"}})
        self.assertEqual(r, 2)  # 사용자 제약은 사용자 출처 + quote
        self.assertIn("사용자 제약 ['C1']", json.loads(out)["error"])
        out = self.ok(run(self.root, "save", {"type": "RESULT", "summary": "z", "constraints_remove": {"C2": "조건이 바뀜"}}))  # 모델 제약: 사유만
        self.assertEqual(out["constraints"], ["C1: 사용자 제약 [사용자]"])
        out = self.ok(run(self.root, "save", {"type": "D_USER", "summary": "z", "quote": "풀어", "constraints_remove": {"C1": "사용자 해제"}}))
        self.assertEqual(out["constraints"], [])

    def test_work_id_and_goal_cleanup(self):
        out = self.ok(new_work(self.root, "던전디펜스 1화 제작"))
        self.assertEqual(out["id"], "work")  # 숫자만 남는 제목은 work
        out = self.ok(new_work(self.root, "새 작업: 웹툰 제작"))
        self.assertEqual((out["id"], out["title"]), ("work-2", "웹툰 제작"))  # 명령 접두어 제거
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "첫 저장"}))
        self.assertEqual(self.state("work-2")["goal"], "웹툰 제작")  # goal 생략 → 제목
        self.assertEqual(use(self.root, "work")[0], 0)
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "새 작업: 던전디펜스 1화 제작",
                                        "goal": "새 작업: 던전디펜스 1화 제작", "decisions": [{"text": "1화 60컷"}]}))
        self.assertEqual(self.state("work")["goal"], "던전디펜스 1화 제작")
        self.assertIn("현재 범위(최신 결정): D1: 1화 60컷", (self.d / "works/work/state.md").read_text())

    def test_completed_works_listed_and_usable(self):
        self.ok(new_work(self.root, "A", tool="claude"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a", "quote": "q"}, tool="claude"))
        self.ok(new_work(self.root, "B", tool="claude"))
        self.ok(run(self.root, "archive", extra=["a"], tool="claude"))
        ctx = json.loads(hook(self.root, "hook", session="fresh")[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("- b · B · ACTIVE", ctx)
        self.assertNotIn("- a · A · COMPLETED", ctx)
        self.assertIn("- 그 외 COMPLETED 1개: a · A (", ctx)
        self.assertIn("[use] 현재 작업: a · A · COMPLETED", use(self.root, "a", session="fresh", tool="claude")[1])

    def test_hooks_seen_reported(self):
        (self.root / ".worklog").mkdir()  # 이미 연결된 폴더(연결한 세션은 2.21.0부터 경고를 내지 않는다: UserScopeTest)
        self.ok(new_work(self.root, "t", tool="claude"))
        out = self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude"))
        self.assertEqual(out["hooks"], {"session_start": False, "turn_start": False, "stop": False})
        self.assertIn("Hook 미작동 의심", out["warning"])
        self.assertIn("하나도 없습니다", out["warning"])
        self.assertIn("[Worklog Hook 경고]", use(self.root, "t", tool="claude")[1])
        hook(self.root, "hook")  # SessionStart만 돌았다(`!` 셸 입력·다른 세션 알림으로 시작한 턴): Hook은 동작 중 → 경고 없음 (2.16.0)
        out = self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y0"}, tool="claude"))
        self.assertEqual(out["hooks"], {"session_start": True, "turn_start": False, "stop": False})
        self.assertNotIn("warning", out)
        self.assertNotIn("[Worklog Hook 경고]", use(self.root, "t", tool="claude")[1])
        hook(self.root, "turn-start")
        out = self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "y"}, tool="claude"))
        self.assertEqual(out["hooks"], {"session_start": True, "turn_start": True, "stop": False})
        self.assertNotIn("warning", out)
        hook(self.root, "stop-hook")
        out = self.ok(run(self.root, "verify", extra=["--all"], tool="claude"))
        self.assertEqual(out["hooks"], {"session": "claude:s1", "session_start": True, "turn_start": True, "stop": True})
        self.assertEqual(out["warnings"], [])
        out = self.ok(run(self.root, "verify", extra=["--all"], tool="claude", session="other"))
        self.assertIn("warning", out["hooks"])  # 다른 세션 ID: Hook 기록 없음 → 경고
        out = self.ok(run(self.root, "skip", extra=["읽기"], tool="pi"))  # 2.24.0: pi hooks exist only with the user-level extension → reported, never warned
        self.assertEqual(out["hooks"], {"session_start": False, "turn_start": False, "stop": False})
        self.assertNotIn("warning", out)

    def test_stop_hook_advances_turn(self):
        """UserPromptSubmit 없이 시작하는 턴(`!` 셸 입력, 다른 세션의 알림)도 Stop Hook이 지나간 뒤에는 새 턴으로 센다 (2.16.0)."""
        turn = lambda: json.loads(session_file(self.root).read_text())["turn"]
        self.ok(new_work(self.root, "t", tool="claude"))  # selected_turn = 0
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(turn(), 1)  # 통과한 Stop이 턴을 넘긴다
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")  # 턴 1: save·skip 없음 → 차단
        self.assertEqual(turn(), 1)  # 차단은 턴을 넘기지 않는다
        self.ok(run(self.root, "skip", extra=["알림만 받음"], tool="claude"))
        self.assertEqual(hook(self.root, "stop-hook"), (0, ""))
        self.assertEqual(turn(), 2)
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")
        self.assertEqual(hook(self.root, "stop-hook", stop_hook_active=True), (0, ""))  # 한 번 막힌 뒤 다시 온 Stop: 통과하고 턴을 넘긴다
        self.assertEqual(turn(), 3)
        self.assertEqual(json.loads(hook(self.root, "stop-hook")[1])["decision"], "block")  # 턴 3도 자기 save·skip이 필요하다
        hook(self.root, "turn-start")  # 사용자 프롬프트: 번호가 하나 건너뛰어도 턴마다 다르기만 하면 된다
        self.assertEqual(turn(), 4)
        self.assertIn("Stop", json.loads(session_file(self.root).read_text())["hooks_seen"])

    def test_artifact_summary_in_state_md(self):
        self.ok(new_work(self.root, "t"))
        arts = []
        for ep in (1, 2):
            (self.root / f"out/EP0{ep}").mkdir(parents=True)
            for n in range(8):
                p = self.root / f"out/EP0{ep}/f{n}.txt"
                p.write_text(f"file {ep} {n}")
                arts.append({"path": f"out/EP0{ep}/f{n}.txt"})
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "16개", "artifacts": arts}))
        md = (self.d / "works/t/state.md").read_text()
        self.assertIn("## 산출물 — 16개, 폴더별 요약", md)
        self.assertIn("- out/EP01/ · 8개 · 최근 E0001", md)
        self.assertNotIn("sha256:", md)
        self.assertEqual(len(self.state()["artifacts"]), 16)  # 전체 목록은 state.json

    def test_new_work_notice_about_other_constraints(self):
        self.ok(new_work(self.root, "A"))
        self.assertNotIn("notice", self.ok(new_work(self.root, "B")))  # 제약 없는 작업은 안내 없음
        self.assertEqual(use(self.root, "a")[0], 0)
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "a", "quote": "q", "constraints": ["게시 완료라고 주장하지 않는다"]}))
        out = self.ok(new_work(self.root, "C"))
        self.assertIn("a 1개", out["notice"])
        self.assertIn("사용자에게 확인", out["notice"])


class CleanupTest(Base):
    """2.26.1: characterization tests added before the core cleanup (hook table, save helpers). Behaviour unchanged."""

    def test_codex_turn_start_and_stop_hook(self):
        """codex as its hooks run it: turn_id dedups UserPromptSubmit, a SessionStart repeat is silent, Stop blocks once per
        turn with {"decision": "block"} and records hook_keys (no agy marks)."""
        self.ok(new_work(self.root, "t", tool="codex"))
        sess = lambda: json.loads(session_file(self.root, "codex_s1").read_text())
        ctx = self.ctx(tool="codex", source="startup")
        self.assertIn("| PROVIDED |", ctx)
        self.assertEqual(hook(self.root, "hook", tool="codex", source="startup"), (0, ""))
        for kw, want in (({"turn_id": "t1"}, 1), ({"turn_id": "t1"}, 1), ({"turn_id": "t2"}, 2)):
            self.assertEqual(hook(self.root, "turn-start", tool="codex", **kw), (0, ""))
            self.assertEqual(sess()["turn"], want, kw)
        self.assertEqual((sess()["hook_keys"]["UserPromptSubmit"], sess()["agy_pre"], sess()["in_turn"]), ("t2", None, True))
        r, out = hook(self.root, "stop-hook", tool="codex")
        self.assertEqual((r, json.loads(out)["decision"]), (0, "block"))
        self.assertEqual((sess()["turn"], sess()["blocked_turn"], sess()["agy_stop"]), (2, 2, None))
        self.assertTrue(sess()["hook_keys"]["Stop"].startswith("2/0@"))
        self.assertEqual(hook(self.root, "stop-hook", tool="codex"), (0, ""))  # blocked once: pass, turn advances
        self.assertEqual((sess()["turn"], sess()["in_turn"]), (3, False))
        self.assertTrue(sess()["hook_keys"]["Stop"].startswith("3/0@"))
        hook(self.root, "turn-start", tool="codex", turn_id="t3")
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="codex"))
        self.assertEqual(hook(self.root, "stop-hook", tool="codex"), (0, ""))  # saved → pass
        self.assertEqual((sess()["turn"], sess()["blocked_turn"]), (5, 2))

    def test_drop_repeats(self):
        """drop_repeats (from cmd_save): source tags stripped, repeats of the state or of this save dropped (replaces kept),
        empty text refused with the constraint check first. In place, no disk."""
        wl = load_wl()
        state = {"constraints": [{"text": "알림 금지"}], "decisions": [{"text": "7분"}]}
        changes = {"constraints": ["[사용자] 알림 금지", "게시 금지", "게시  금지"],
                   "decisions": [{"text": "7분 [모델]"}, {"text": "7분", "replaces": "D1"}, {"text": "11분"}, {"text": "11 분"}]}
        ignored = wl.drop_repeats(changes, state)
        self.assertEqual(ignored, ["알림 금지", "게시  금지", {"text": "7분"}])
        self.assertEqual(changes, {"constraints": ["게시 금지"],
                                   "decisions": [{"text": "7분", "replaces": "D1"}, {"text": "11분"}, {"text": "11 분"}]})
        self.assertEqual(wl.drop_repeats({"waiting": []}, state), [])
        with self.assertRaisesRegex(wl.Reject, "^제약 내용이 비어 있습니다"):
            wl.drop_repeats({"constraints": ["[모델]"], "decisions": [{"text": "[사용자]"}]}, state)
        with self.assertRaisesRegex(wl.Reject, "^결정 내용이 비어 있습니다"):
            wl.drop_repeats({"decisions": [{"text": "x"}, {"text": " [사용자] "}]}, state)

    def test_check_quotes_function(self):
        """check_quotes (from cmd_save): (need, unreflected, self_quoted) or the same refusals as save."""
        wl = load_wl()
        state = {"decisions": [{"id": "D1", "text": "7분"}], "constraints": [{"id": "C1", "text": "알림 금지"}]}
        body = [wl.norm("수요일 저녁 7분 동안 적는다.\n알림 금지")]
        arts = [{"path": "a.md"}]
        cq = lambda check, a=arts, b=body: wl.check_quotes({"check": check}, a, b, state)
        self.assertEqual(wl.check_quotes({}, [], [], state), ([], [], []))
        with self.assertRaisesRegex(wl.Reject, r"^산출물 대조 누락: \['D1', 'C1'\]"):
            cq({})
        self.assertEqual(cq({"D1": "'저녁 7분 동안'", "C1": "미반영: 작업 방식"}), (["D1", "C1"], ["C1"], []))
        self.assertEqual(cq({"D1": "“저녁 7분 동안”", "C1": "'알림 금지'"}), (["D1", "C1"], [], ["C1"]))
        with self.assertRaisesRegex(wl.Reject, "^check D1의 미반영 이유가 비어"):
            cq({"D1": "미반영:  ", "C1": "'없는 문장입니다'"})
        with self.assertRaisesRegex(wl.Reject, "^check D1의 인용이 너무 짧습니다"):
            cq({"D1": "'7분'", "C1": "미반영: x"})
        with self.assertRaisesRegex(wl.Reject, "^check C1의 인용이 산출물에 없습니다"):
            cq({"D1": "'저녁 7분 동안'", "C1": "'없는 문장입니다'"})
        self.assertEqual(cq({"D1": "미반영: 그림", "X9": "'아무거나 넣음'"}, b=[]), (["D1"], ["D1"], []))  # 비텍스트만: 있는 id만
        with self.assertRaisesRegex(wl.Reject, "^check D1: 산출물이 모두 비텍스트"):
            cq({"D1": "'저녁 7분 동안'"}, b=[])


class Release2270Test(Base):
    """2.27.0: U16 tool guess guard, U12 once-per-session missing notes and artifacts_gone, U15 reassign --new."""
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.d = self.root / ".worklog"

    def bare(self, *argv, env=None, payload=None):
        """A command without WL_TOOL/WL_SESSION_ID: the tool comes from --tool or the tool session variables in env."""
        p = subprocess.run([sys.executable, "-B", str(WL), *argv, "--root", str(self.root)], input=json.dumps(payload) if payload else "",
                           capture_output=True, text=True, env=dict(clean_env(), **(env or {})))
        return p.returncode, p.stdout

    def events(self, wid):
        return [json.loads(x) for x in (self.d / "works" / wid / "events.jsonl").read_text().splitlines()]

    def state(self, wid):
        return json.loads((self.d / "works" / wid / "state.json").read_text())

    # --- U16 ---
    def test_tool_guess_refused_with_two_session_variables(self):
        self.ok(new_work(self.root, "t", tool="claude"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}, tool="claude"))
        both = {"CLAUDE_CODE_SESSION_ID": "c1", "PI_SESSION_ID": "p1"}
        r, out = self.bare("use", "t", "--quote", "q", env=both)                       # 둘 다 있고 --tool 없음: 추정하지 않는다
        self.assertEqual(r, 2, out)
        err = json.loads(out)["error"]
        self.assertTrue(err.startswith("도구를 확정할 수 없습니다: CLAUDE_CODE_SESSION_ID(claude), PI_SESSION_ID(pi)가 함께 있습니다."), err)
        self.assertIn("--tool <codex|claude|agy|pi>", err)
        self.assertFalse((self.d / "sessions/claude_c1.json").exists())
        self.assertTrue(self.bare("use", "t", "--quote", "q", env={"PI_SESSION_ID": "p1"})[1].startswith("[use] 현재 작업: t"))  # 하나면 추정
        self.assertTrue((self.d / "sessions/pi_p1.json").exists())
        self.assertTrue(self.bare("use", "t", "--quote", "q", "--tool", "pi", env=dict(both, PI_SESSION_ID="p2"))[1].startswith("[use]"))
        self.assertTrue((self.d / "sessions/pi_p2.json").exists())                     # --tool pi: pi 변수의 세션
        self.assertFalse((self.d / "sessions/claude_c1.json").exists())
        save = {"work": "t", "type": "CHECKPOINT", "summary": "y"}
        r, out = self.bare("save", "--tool", "pi", env={"CLAUDE_CODE_SESSION_ID": "c1", "PI_SESSION_ID": "p3"}, payload=save)
        self.assertEqual(r, 2, out)
        self.assertTrue(json.loads(out)["error"].endswith("(이 호출: tool=pi session=p3, --tool 지정)"), out)
        r, out = self.bare("save", env={"PI_SESSION_ID": "p4"}, payload=save)
        self.assertIn("(이 호출: tool=pi session=p4, 환경변수 PI_SESSION_ID에서 추정)", json.loads(out)["error"])
        self.refused(run(self.root, "save", save, session="w1", tool="codex"), "show 먼저 실행하세요(작업 t).")
        self.refused(run(self.root, "save", save, session="w1", tool="codex"), "(이 호출: tool=codex session=w1, WL_TOOL)")
        self.ok(self.bare("save", "--tool", "pi", env={"PI_SESSION_ID": "p1"}, payload=save))
        self.refused(run(self.root, "save", {"type": "CHECKPOINT", "summary": "z"}, tool="claude"),
                     "기록이 바뀌었습니다(seq 1→2). show 후 다시 저장하세요. (이 호출: tool=claude session=s1, WL_TOOL)")
        # Hook 명령은 설치기가 늘 --tool을 넣는다: 변수가 둘이어도 그 도구의 세션으로 돈다
        r, out = hook(self.root, "hook", session="c9", tool="claude", env=both)
        self.assertIn("SessionStart | NO_CURRENT_WORK", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(hook(self.root, "turn-start", session="c9", tool="claude", env=both), (0, ""))
        self.assertEqual(json.loads(hook(self.root, "stop-hook", session="c9", tool="claude", env=both)[1])["decision"], "block")
        s = json.loads(session_file(self.root, "claude_c9").read_text())
        self.assertEqual((s["turn"], s["blocked_turn"], sorted(s["hooks_seen"])), (1, 1, ["SessionStart", "Stop", "UserPromptSubmit"]))

    # --- U12 ---
    def test_missing_noted_once_per_session(self):
        """U12 A: each session sees a missing path(Eid) once; another session's own missing file is not hidden by it; a file that
        comes back and goes again stays quiet in that session; verify still lists it."""
        self.ok(new_work(self.root, "t", session="a"))
        (self.root / "a.md").write_text("A 본문")
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "a", "artifacts": [{"path": "a.md"}]}, session="a"))
        self.used(use(self.root, session="b"), "t")
        (self.root / "b.md").write_text("B 본문")
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "b", "artifacts": [{"path": "b.md"}]}, session="b"))
        run(self.root, "show", session="a")
        (self.root / "a.md").unlink()
        (self.root / "b.md").unlink()
        first = run(self.root, "show", session="a")[1]
        self.assertIn("a.md(E0001)", first)
        self.assertNotIn("b.md", first.split("\n")[0])                               # 알림 줄: 다른 세션이 기록한 것은 없다
        self.assertNotIn("산출물 없음", run(self.root, "show", session="a")[1])
        self.assertIn("b.md(E0002)", run(self.root, "show", session="b")[1])           # 다른 세션: 자기 것은 보인다
        self.assertNotIn("산출물 없음", run(self.root, "show", session="b")[1])
        self.assertEqual(json.loads(session_file(self.root, "codex_a").read_text())["missing_noted"], ["a.md(E0001)"])
        self.assertEqual(json.loads(session_file(self.root, "codex_b").read_text())["missing_noted"], ["b.md(E0002)"])
        (self.root / "a.md").write_text("A 본문")
        run(self.root, "show", session="a")
        (self.root / "a.md").unlink()
        self.assertNotIn("artifacts_missing", self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "c"}, session="a")))
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["works"][0]["artifacts"]["missing"], ["a.md(E0001)", "b.md(E0002)"])
        bad = json.loads(session_file(self.root, "codex_a").read_text())
        session_file(self.root, "codex_a").write_text(json.dumps(dict(bad, missing_noted="x")))  # 잘못된 값: 손상이 아니라 빈 목록
        self.assertIn("a.md(E0001)", run(self.root, "show", session="a")[1])

    def test_artifacts_gone(self):
        """U12 B′: save artifacts_gone [{path, reason}] drops recorded paths the user confirmed deleted from the list (no more
        artifacts_missing, not in verify missing, shown as verify gone) and keeps changes.artifacts_gone in the ledger."""
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]}))
        for n in ("note.md", "b.md", "c.md"):
            (self.root / n).write_text("본문 " + n)
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": n} for n in ("note.md", "b.md", "c.md")],
                                        "check": {"C1": "미반영: 게시는 하지 않음"}}))
        (self.root / "note.md").unlink()
        (self.root / "c2.md").write_text("옮긴 b")
        self.assertEqual(self.ok(run(self.root, "skip", extra=["x"]))["artifacts_missing"], ["note.md(E0002)"])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["works"][0]["artifacts"],
                         {"missing": ["note.md(E0002)"], "changed": 0, "checked": 3})          # gone이 없으면 키도 없다
        for gone, extra, text in (([{"path": "x.md", "reason": "r"}], {}, "산출물 목록에 없는 경로입니다: x.md"),
                                  ([{"path": "note.md"}], {}, "reason이 비어 있습니다"),
                                  ([{"path": "note.md", "reason": "  "}], {}, "reason이 비어 있습니다"),
                                  ("note.md", {}, "artifacts_gone은"),
                                  ([{"path": "note.md", "reason": "r", "to": "y"}], {}, "artifacts_gone은"),
                                  ([{"path": "note.md", "reason": "r"}, {"path": "note.md", "reason": "r"}], {}, "두 번"),
                                  ([{"path": "b.md", "reason": "r"}], {"artifacts_moved": {"b.md": "c2.md"}}, "같은 save의")):
            r, out = run(self.root, "save", dict({"type": "CHECKPOINT", "summary": "지움", "artifacts_gone": gone}, **extra))
            self.assertEqual(r, 2, out)
            self.assertIn(text, json.loads(out)["error"])
        self.assertEqual(len((self.d / "works/t/events.jsonl").read_text().splitlines()), 2)
        out = self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "지움", "artifacts_gone": [
            {"path": "note.md", "reason": "사용자가 지웠다고 확인"}, {"path": "c.md", "reason": " 사용자가 필요 없다고 함 "}]}))
        self.assertNotIn("artifacts_missing", out)                                       # 파일이 남아 있는 c.md도 받는다
        ev = json.loads((self.d / "works/t/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(ev["changes"]["artifacts_gone"], [{"path": "note.md", "reason": "사용자가 지웠다고 확인"},
                                                           {"path": "c.md", "reason": "사용자가 필요 없다고 함"}])
        st = self.state("t")
        self.assertEqual([a["path"] for a in st["artifacts"]], ["b.md"])
        self.assertNotIn("artifacts_gone", st)                                           # state.json에 새 키 없음
        self.assertNotIn("note.md", (self.d / "works/t/state.md").read_text())
        v = self.ok(run(self.root, "verify", extra=["--all"]))
        self.assertTrue(v["ok"])
        self.assertEqual(v["works"][0]["artifacts"], {"missing": [], "changed": 0, "checked": 1, "gone": ["note.md(E0003)", "c.md(E0003)"]})
        self.refused(run(self.root, "save", {"type": "CHECKPOINT", "summary": "또", "artifacts_gone": [{"path": "note.md", "reason": "r"}]}),
                     "산출물 목록에 없는 경로입니다: note.md")
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "다시", "artifacts": [{"path": "c.md"}], "check": {"C1": "미반영: x"}}))
        self.assertEqual(self.ok(run(self.root, "verify"))["artifacts"]["gone"], ["note.md(E0003)"])  # 다시 기록한 경로는 gone에서 빠진다

    # --- U15 ---
    def call(self, fn, args, **patches):
        """An in-process command with module attributes patched (failure injection); (exit code, parsed JSON or None)."""
        buf, code = io.StringIO(), 0
        with mock.patch("sys.stdout", buf), contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(self.wl, name, value))
            try:
                fn(Namespace(**args))
            except SystemExit as e:
                code = e.code
        return code, (json.loads(buf.getvalue()) if buf.getvalue().strip() else None)

    def recipe(self):
        """recipe (E0001 decision+constraint, E0002 checkpoint) and memo (one constraint); session s1 (codex) on recipe, next turn."""
        self.ok(new_work(self.root, "memo"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "m", "quote": "메모", "constraints": ["메모는 한 줄"]}))
        self.ok(new_work(self.root, "recipe"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "가이드 형식", "quote": "표는 3열로",
                                        "decisions": [{"text": "표는 3열(읽기 쉬움)"}], "constraints": ["외부 게시 금지"]}))
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "진행"}))
        hook(self.root, "turn-start", session="s1", tool="codex")

    def test_reassign_new_creates_and_moves(self):
        self.recipe()
        argv = ["reassign", "recipe", "--new", "새 작업: Guide", "--events", "E0001", "--quote", "그건 새 작업 guide야"]
        out = self.ok(run(self.root, argv[0], extra=argv[1:]))
        self.assertEqual((out["from"], out["to"], out["created"], out["current_work"], out["refiled"], out["misfiled"]),
                         ("recipe", "guide", "guide", "guide", "E0001", "E0003"))
        self.assertEqual(out["decisions"], ["D1: 표는 3열(읽기 쉬움) [사용자]"])
        self.assertIn("다른 작업의 유효 제약은 이 작업에 적용되지 않습니다: memo 1개", out["notice"])
        w = self.index()["works"]["guide"]
        self.assertEqual((w["title"], w["status"], w["last_seq"]), ("Guide", "ACTIVE", 1))
        ev = self.events("guide")
        self.assertEqual((len(ev), ev[0]["type"], ev[0]["summary"], ev[0]["changes"]["goal"]), (1, "CORRECTION", "[refiled ← recipe] E0001", "Guide"))
        self.assertEqual(self.state("guide")["goal"], "Guide")
        self.assertEqual((self.state("recipe")["decisions"], self.state("recipe")["constraints"]), ([], []))
        self.assertEqual(self.events("recipe")[-1]["summary"], "[misfiled → guide] E0001")
        s = json.loads(session_file(self.root, "codex_s1").read_text())
        self.assertEqual((s["current_work"], s["new_work_id"], s["new_work_turn"], s["selected_turn"]), ("guide", "guide", 1, 1))
        self.assertTrue(self.ok(run(self.root, "verify", extra=["--all"]))["ok"])
        self.assertEqual(self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "이어감"}))["work"], "guide")  # 현재 작업 = guide
        self.refused(run(self.root, argv[0], extra=argv[1:]), "--new 제목의 작업 id guide가 이미 있습니다")   # 저장이 더 생긴 뒤: 이어 갈 대상 아님
        self.refused(run(self.root, "new-work", extra=["X", "--quote", "q"]), "이미 new-work로 작업 guide를")  # --new도 같은 턴 표식을 남긴다

    def test_reassign_new_refusals(self):
        self.recipe()
        self.refused(run(self.root, "reassign", extra=["recipe", "memo", "--new", "guide", "--events", "E0001", "--quote", "q"]),
                     "<맞는 id>(memo)와 --new를 함께 쓸 수 없습니다")
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", " 새 작업: ", "--events", "E0001", "--quote", "q"]), "--new의 제목이 비어")
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", "Memo", "--events", "E0001", "--quote", "q"]),
                     'reassign recipe memo --events E0001 --quote "<원문>"')                     # id 충돌: 그 작업으로 옮기라고 안내
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0009", "--quote", "q"]), "작업에 없는 사건")
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001"]), "사용자 원문")
        self.assertEqual(sorted(self.index()["works"]), ["memo", "recipe"])                       # 거부는 아무것도 만들지 않는다
        self.ok(run(self.root, "new-work", extra=["Other", "--quote", "q"]))                       # 이번 턴에 이미 새 작업
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001", "--quote", "q"]), "--force")
        self.assertNotIn("guide", self.index()["works"])
        out = self.ok(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001", "--quote", "q", "--force"]))
        self.assertEqual(out["created"], "guide")
        self.ok(new_work(self.root, "던전디펜스"))                                                # 한글만: work
        hook(self.root, "turn-start", session="s1", tool="codex")
        out = self.ok(run(self.root, "reassign", extra=["recipe", "--new", "던전 2화", "--events", "E0002", "--quote", "q"]))
        self.assertEqual(out["created"], "work-2")                                               # new-work와 같은 규칙(충돌이 아님)

    def test_reassign_new_partial_then_retry(self):
        """A failure after the new work exists: partial names it (created); the same command again finds it by its title and does
        the missing steps without making "<id>-2"."""
        self.recipe()
        self.wl = load_wl()
        args = dict(arg="recipe", arg2=None, new="guide", events="E0001", quote="새 작업 guide야", root=str(self.root), tool="codex",
                    session="s1", force=False)
        real, n = self.wl.commit, [0]
        def commit(*a, **kw):
            n[0] += 1
            if n[0] == 1:
                raise OSError("commit 실패(시험)")
            return real(*a, **kw)
        code, res = self.call(self.wl.cmd_reassign, args, commit=commit)
        self.assertEqual((code, res["partial"], res["done"], res["created"]), (2, True, [], "guide"))
        self.assertEqual((self.index()["works"]["guide"]["last_seq"], (self.d / "works/guide").is_dir()), (0, True))
        out = self.ok(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001", "--quote", "새 작업 guide야"]))
        self.assertEqual((out["to"], out["refiled"], out["misfiled"], out["current_work"]), ("guide", "E0001", "E0003", "guide"))
        self.assertNotIn("created", out)
        self.assertEqual(sorted(self.index()["works"]), ["guide", "memo", "recipe"])
        self.assertEqual(self.state("guide")["goal"], "guide")
        self.assertTrue(self.ok(run(self.root, "verify", extra=["--all"]))["ok"])
        self.refused(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001", "--quote", "q"]), "이미 옮겼습니다")

    # --- 2.27.0 fix (검증 지적 N01~N03) ---
    def test_reassign_new_refuses_other_sessions_empty_work(self):
        """N01: another session's empty work with the --new title is not continued (no session marker for this refile): it is a
        slug clash; and the same-turn new-work refusal still applies to reassign --new."""
        self.ok(new_work(self.root, "recipe", session="a"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "seed", "quote": "q", "decisions": [{"text": "three columns"}]}, session="a"))
        self.ok(new_work(self.root, "guide", session="other", quote="other guide"))
        argv = ["recipe", "--new", "guide", "--events", "E0001", "--quote", "new guide"]
        self.refused(run(self.root, "reassign", session="a", extra=argv), "작업 id guide가 이미 있습니다")
        self.assertFalse((self.d / "works/guide/events.jsonl").exists())                 # other의 빈 작업은 그대로
        self.assertEqual(json.loads(session_file(self.root, "codex_a").read_text())["current_work"], "recipe")
        self.refused(run(self.root, "reassign", session="a", extra=["recipe", "--new", "guide2", "--events", "E0001", "--quote", "q"]),
                     "이번 턴에 이미 new-work로 작업 recipe")                              # 같은 턴의 두 번째 생성은 거부
        self.assertNotIn("guide2", self.index()["works"])

    def test_reassign_new_partial_on_create_failure(self):
        """N02: a failure while creating the --new work is a partial result (done, created when the work is in index.json), not a
        plain refusal; the same command by the same session then continues, by another session it is a slug clash (N01)."""
        self.recipe()
        self.wl = load_wl()
        real = self.wl.write_index
        def before_write(*a, **kw):
            raise OSError("index 쓰기 실패(시험)")
        args = dict(arg="recipe", arg2=None, new="guide", events="E0001", quote="새 작업 guide야", root=str(self.root), tool="codex",
                    session="s1", force=False)
        code, res = self.call(self.wl.cmd_reassign, args, write_index=before_write)         # index에 쓰기 전 실패
        self.assertEqual((code, res["partial"], res["done"]), (2, True, []), res)
        self.assertNotIn("created", res)
        self.assertNotIn("guide", self.index()["works"])
        self.assertEqual(json.loads(session_file(self.root, "codex_s1").read_text())["new_work_from"], "recipe:E0001")
        out = self.ok(run(self.root, "reassign", extra=["recipe", "--new", "guide", "--events", "E0001", "--quote", "새 작업 guide야"]))
        self.assertEqual((out["created"], out["to"], sorted(self.index()["works"])), ("guide", "guide", ["guide", "memo", "recipe"]))
        hook(self.root, "turn-start", session="s1", tool="codex")
        n = [0]
        def after_write(*a, **kw):
            real(*a, **kw)
            n[0] += 1
            if n[0] == 1:
                raise OSError("index 뒤 실패(시험)")
        args.update(new="notes", events="E0002")
        code, res = self.call(self.wl.cmd_reassign, args, write_index=after_write)          # index에 쓴 뒤 실패
        self.assertEqual((code, res["partial"], res["done"], res["created"]), (2, True, [], "notes"), res)
        self.assertEqual(self.index()["works"]["notes"]["last_seq"], 0)
        argv = ["recipe", "--new", "notes", "--events", "E0002", "--quote", "notes야"]
        self.refused(run(self.root, "reassign", session="s9", extra=argv), "작업 id notes가 이미 있습니다")  # 다른 세션은 이어 가지 않는다
        out = self.ok(run(self.root, "reassign", extra=argv))
        self.assertEqual((out["to"], out["refiled"]), ("notes", "E0001"))
        self.assertNotIn("created", out)
        self.assertEqual(sorted(self.index()["works"]), ["guide", "memo", "notes", "recipe"])
        self.assertTrue(self.ok(run(self.root, "verify", extra=["--all"]))["ok"])

    def test_artifacts_gone_path_aliases(self):
        """N03: artifacts_gone compares paths as one file (b.md, ./b.md, the absolute path): an alias in the same save's artifacts
        or twice in artifacts_gone is refused, and an alias names the recorded artifact (its spelling is what the change keeps)."""
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q", "constraints": ["게시 금지"]}))
        for n in ("b.md", "c.md"):
            (self.root / n).write_text("본문 " + n)
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": "b.md"}, {"path": "c.md"}],
                                        "check": {"C1": "미반영: 게시는 하지 않음"}}))
        chk = {"check": {"C1": "미반영: x"}}
        for gone, extra, text in (([{"path": "b.md", "reason": "r"}], dict(chk, artifacts=[{"path": "./b.md"}]), "같은 save의"),
                                  ([{"path": "./b.md", "reason": "r"}], dict(chk, artifacts=[{"path": "b.md"}]), "같은 save의"),
                                  ([{"path": "b.md", "reason": "r"}], dict(chk, artifacts=[{"path": str(self.root / "b.md")}]), "같은 save의"),
                                  ([{"path": "b.md", "reason": "r"}, {"path": "./b.md", "reason": "r"}], {}, "두 번")):
            r, out = run(self.root, "save", dict({"type": "RESULT" if "artifacts" in extra else "CHECKPOINT", "summary": "지움",
                                                  "artifacts_gone": gone}, **extra))
            self.assertEqual(r, 2, out)
            self.assertIn(text, json.loads(out)["error"])
        self.assertEqual(len(self.events("t")), 2)
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "지움", "artifacts_gone": [
            {"path": "./b.md", "reason": "사용자가 지웠다고 확인"}, {"path": str(self.root / "c.md"), "reason": "필요 없다고 함"}]}))
        self.assertEqual(self.events("t")[-1]["changes"]["artifacts_gone"], [{"path": "b.md", "reason": "사용자가 지웠다고 확인"},
                                                                             {"path": "c.md", "reason": "필요 없다고 함"}])
        self.assertEqual(self.state("t")["artifacts"], [])
        self.assertEqual(self.ok(run(self.root, "verify", extra=["--all"]))["works"][0]["artifacts"]["gone"], ["b.md(E0003)", "c.md(E0003)"])
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "다시", "artifacts": [{"path": "./b.md"}], "check": {"C1": "미반영: x"}}))
        self.assertEqual(self.ok(run(self.root, "verify"))["artifacts"]["gone"], ["c.md(E0003)"])  # ./b.md로 다시 기록: 같은 파일

    def test_verify_gone_absolute_path_recorded_again(self):
        """fix2: verify's gone list compares with path_key too, so a gone file recorded again by its absolute path leaves it."""
        self.ok(new_work(self.root, "t"))
        self.ok(run(self.root, "save", {"type": "REQUEST", "summary": "x", "quote": "q"}))
        (self.root / "b.md").write_text("본문")
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "s", "artifacts": [{"path": "b.md"}]}))
        self.ok(run(self.root, "save", {"type": "CHECKPOINT", "summary": "지움", "artifacts_gone": [{"path": "b.md", "reason": "사용자 확인"}]}))
        self.assertEqual(self.ok(run(self.root, "verify"))["artifacts"]["gone"], ["b.md(E0003)"])
        self.ok(run(self.root, "save", {"type": "RESULT", "summary": "다시", "artifacts": [{"path": str(self.root / "b.md")}]}))
        self.assertNotIn("gone", self.ok(run(self.root, "verify"))["artifacts"])
