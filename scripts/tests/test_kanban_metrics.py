"""scripts/kanban_metrics.py 단위 테스트 (임시 sqlite 픽스처, 표준 라이브러리 + pytest만 사용).

실행: python3 -m pytest scripts/tests/test_kanban_metrics.py -q
케이스 (a)~(i)는 C1 카드 합격 기준 1의 최소 목록이고, 뒤쪽은 경계 사례를 더한 것이다.
"""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import kanban_metrics as km  # noqa: E402

KST = timezone(timedelta(hours=9))
SCHEMA = """
create table tasks (id text primary key, title text, body text, assignee text, status text,
                    created_at integer, model_override text);
create table task_runs (id integer primary key autoincrement, task_id text not null, profile text,
                        status text, outcome text, error text, started_at integer, ended_at integer);
create table task_events (id integer primary key autoincrement, task_id text not null, run_id integer,
                          kind text not null, payload text, created_at integer);
"""


def ts(y, m, d, h=12, mi=0):
    """KST 달력 시각 → epoch 초."""
    return int(datetime(y, m, d, h, mi, tzinfo=KST).timestamp())


# 2026-11-02(월)=W45, 11-09(월)=W46, 11-16(월)=W47
W45, W46, W47 = ts(2026, 11, 4), ts(2026, 11, 10), ts(2026, 11, 17)


def mkdb(path: Path, tasks=(), runs=(), events=()) -> Path:
    """tasks: dict(id, title, body, assignee, status) / runs: (task_id, profile, outcome, error, started_at)
    / events: (task_id, kind, created_at)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for t in tasks:
        con.execute(
            "insert into tasks (id, title, body, assignee, status, created_at) values (?,?,?,?,?,?)",
            (t["id"], t.get("title", ""), t.get("body", ""), t.get("assignee", "coder-bot"),
             t.get("status", "done"), 0))
    for task_id, prof, outcome, error, started in runs:
        con.execute("insert into task_runs (task_id, profile, outcome, error, started_at) values (?,?,?,?,?)",
                    (task_id, prof, outcome, error, started))
    for task_id, kind, created in events:
        con.execute("insert into task_events (task_id, kind, created_at) values (?,?,?)", (task_id, kind, created))
    con.commit()
    con.close()
    return path


def T(tid, **kw):
    return dict(id=tid, **kw)


# ───────── (a)(b) 첫 런 기준 담당 ─────────

def test_a_assignee_changed_card_counts_as_coder_first_run(tmp_path):
    db = mkdb(
        tmp_path / "b.db",
        tasks=[T("c1", assignee="reviewer-bot"),            # 리뷰 요청 때 assignee가 reviewer로 바뀜
               T("r1", assignee="reviewer-bot"),            # 처음부터 reviewer 일
               T("c2", assignee="coder-bot")],
        runs=[("c1", "coder-bot", "review_requested", None, W46),   # 첫 런 = coder
              ("c1", "reviewer-bot", "completed", None, W46 + 100),
              ("r1", "reviewer-bot", "completed", None, W46),
              ("c2", "coder-bot", "completed", None, W46)],
    )
    t = km.first_run_table({"x": db})
    b = t["boards"]["x"]
    assert b["cards_with_runs"] == 3
    assert b["first_run"] == {"coder-bot": 2, "reviewer-bot": 1, "fable-bot": 0, "helper-bot": 0, "other": 0}
    assert b["assignee_reviewer"] == 2
    assert b["illusion"] == 1                                # c1 한 건
    assert t["total"]["illusion"] == 1


def test_a_first_run_is_smallest_run_id_not_earliest_started_at(tmp_path):
    # id 가 작은 행이 첫 런이다(started_at 이 거꾸로여도).
    db = mkdb(tmp_path / "b.db", tasks=[T("c1", assignee="reviewer-bot")],
              runs=[("c1", "fable-bot", "completed", None, W46 + 500),
                    ("c1", "coder-bot", "completed", None, W46)])
    assert km.first_run_table({"x": db})["boards"]["x"]["first_run"]["fable-bot"] == 1


def test_b_cards_without_runs_and_unknown_profiles(tmp_path):
    db = mkdb(
        tmp_path / "b.db",
        tasks=[T("n1"), T("n2"), T("h1"), T("o1"), T("z1")],
        runs=[("h1", "helper-bot", "completed", None, W46),
              ("o1", "default-bot", "completed", None, W46),
              ("z1", None, "completed", None, W46)],
    )
    b = km.first_run_table({"x": db})["boards"]["x"]
    assert b["cards_with_runs"] == 3                         # 런 없는 n1·n2 는 빠진다
    assert sum(b["first_run"].values()) == b["cards_with_runs"]
    assert b["first_run"]["helper-bot"] == 1 and b["first_run"]["other"] == 2
    assert b["other_profiles"] == {"default-bot": 1, "(없음)": 1}


def test_first_run_table_marks_unreadable_board_and_continues(tmp_path):
    ok = mkdb(tmp_path / "ok.db", tasks=[T("a")], runs=[("a", "coder-bot", "completed", None, W46)])
    t = km.first_run_table({"gone": tmp_path / "nope.db", "ok": ok})
    assert "gone" in t["read_failures"] and "ok" in t["boards"]
    assert t["total"]["cards_with_runs"] == 1
    out = km.render_first_run(t)
    assert "읽기 실패" in out and "gone" in out


# ───────── (c) A1 ─────────

def test_c_a1_splits_weeks_and_ignores_cards_without_coder_runs(tmp_path):
    db = mkdb(
        tmp_path / "b.db",
        tasks=[T("c1"), T("x1", assignee="reviewer-bot")],
        runs=[("c1", "coder-bot", "review_requested", None, W45),
              ("c1", "coder-bot", "review_requested", None, W46),
              ("c1", "coder-bot", "completed", None, W46 + 3600),          # rr 아님
              ("c1", "reviewer-bot", "changes_requested", None, W46),      # 다른 프로필 런은 분모 아님
              ("x1", "reviewer-bot", "review_requested", None, W46)],
        events=[("c1", "changes_requested", W45 + 60),
                ("c1", "changes_requested", W46 + 60),
                ("c1", "changes_requested", W46 + 120),
                ("x1", "changes_requested", W46 + 60)],                    # coder 런 없는 카드 → 빠짐
    )
    t = km.weekly_project_table({"x": db})
    assert t["weeks"]["2026-W45"]["x"]["a1"]["rr"] == 1 and t["weeks"]["2026-W45"]["x"]["a1"]["cr"] == 1
    assert t["weeks"]["2026-W46"]["x"]["a1"]["rr"] == 1 and t["weeks"]["2026-W46"]["x"]["a1"]["cr"] == 2
    assert t["weeks"]["2026-W46"]["x"]["a1"]["rate"] == 2.0
    assert t["week_totals"]["2026-W46"]["a1"]["cr"] == 2


def test_c_a1_by_card_type_and_window(tmp_path):
    db = mkdb(
        tmp_path / "b.db",
        tasks=[T("i1", title="로그인 기능 추가"), T("d1", title="README 갱신"), T("a1", title="성능 측정")],
        runs=[("i1", "coder-bot", "review_requested", None, W46),
              ("d1", "coder-bot", "review_requested", None, W46),
              ("d1", "coder-bot", "review_requested", None, W46 + 10),
              ("a1", "coder-bot", "review_requested", None, W47)],
        events=[("d1", "changes_requested", W46 + 5), ("i1", "changes_requested", W46 + 5)],
    )
    t = km.weekly_project_table({"x": db})
    assert t["weeks"]["2026-W46"]["x"]["a1"]["by_type"] == {
        "구현": {"rr": 1, "cr": 1}, "문서": {"rr": 2, "cr": 1}, "분석": {"rr": 0, "cr": 0}}
    assert t["weeks"]["2026-W47"]["x"]["a1"]["by_type"]["분석"] == {"rr": 1, "cr": 0}
    # since/until: [since, until) — W46만
    t2 = km.weekly_project_table({"x": db}, since=ts(2026, 11, 9, 0, 0), until=ts(2026, 11, 16, 0, 0))
    assert list(t2["weeks"]) == ["2026-W46"]
    assert t2["type_fallback"]["total"]["target_cards"] == 3         # 대상 카드 수는 창과 무관


def test_a1_null_outcome_not_in_denominator_and_null_started_excluded(tmp_path):
    db = mkdb(
        tmp_path / "b.db", tasks=[T("c1")],
        runs=[("c1", "coder-bot", None, None, W46),                       # 실행 중: A1 분모 아님, A5 분모 포함
              ("c1", "coder-bot", "review_requested", None, None),         # started_at NULL: 주 계산에서 빠짐
              ("c1", "coder-bot", "review_requested", None, W46)],
    )
    t = km.weekly_project_table({"x": db})
    cell = t["weeks"]["2026-W46"]["x"]
    assert cell["a1"]["rr"] == 1
    assert cell["a5"]["coder_runs"] == 2
    assert t["excluded_null_started"] == {"boards": {"x": 1}, "total": 1}
    assert "뺀 런: 1건" in km.render_weekly_project(t)


# ───────── (d) A2 ─────────

def test_d_a2_pending_cards_leave_denominator(tmp_path):
    runs = [(c, "coder-bot", "review_requested", None, W46) for c in ("d1", "d2", "d3", "d4")]
    db = mkdb(
        tmp_path / "b.db", tasks=[T(c) for c in ("d1", "d2", "d3", "d4")], runs=runs,
        events=[("d1", "review_requested", W46), ("d1", "completed", W46 + 10),                 # 통과
                ("d2", "review_requested", W46), ("d2", "changes_requested", W46 + 5),
                ("d2", "review_requested", W46 + 20), ("d2", "completed", W46 + 30),            # 반려 1회 → 실패
                ("d3", "review_requested", W46),                                                # 미완
                ("d4", "review_requested", W45), ("d4", "review_requested", W46),               # 첫 리뷰는 W45
                ("d4", "completed", W46 + 10)],
    )
    t = km.weekly_project_table({"x": db})
    a2 = t["weeks"]["2026-W46"]["x"]["a2"]
    assert a2 == {"first_review_cards": 3, "completed": 2, "passed": 1, "pending": 1, "rate": 0.5}
    a2_45 = t["weeks"]["2026-W45"]["x"]["a2"]
    assert (a2_45["first_review_cards"], a2_45["completed"], a2_45["passed"]) == (1, 1, 1)
    assert "A2 미완" in km.render_weekly_project(t)


# ───────── (e) A3 ─────────

def test_e_a3_distribution_mean_and_all_time(tmp_path):
    tasks = [T("p0"), T("q0"), T("p1"), T("p2"), T("p3"), T("arch", status="archived"), T("late"), T("open")]
    ev = []
    for tid, n in (("p0", 0), ("q0", 0), ("p1", 1), ("p2", 2), ("p3", 3), ("arch", 1), ("late", 0), ("open", 4)):
        ev += [("%s" % tid, "changes_requested", W46) for _ in range(n)]
    ev += [("p0", "completed", W46 + 10), ("q0", "completed", W46 + 10), ("p1", "completed", W46 + 10),
           ("p2", "completed", W46 + 10), ("p3", "completed", W46 + 10), ("arch", "completed", W46 + 10),
           ("late", "completed", W46 + 10), ("late", "completed", W47)]          # 마지막 completed 는 W47
    runs = [(t["id"], "coder-bot", "review_requested", None, W46) for t in tasks]
    db = mkdb(tmp_path / "b.db", tasks=tasks, runs=runs, events=ev)
    t = km.weekly_project_table({"x": db})
    a3 = t["weeks"]["2026-W46"]["x"]["a3"]
    # W46 완료 = p0 q0 p1 p2 p3 arch (late 는 W47, open 은 completed 없음)
    assert a3["cards"] == 6 and a3["dist"] == {"0": 2, "1": 2, "2+": 2}
    assert a3["cr_sum"] == 0 + 0 + 1 + 2 + 3 + 1 and a3["mean"] == round(7 / 6, 3)
    assert t["weeks"]["2026-W47"]["x"]["a3"]["cards"] == 1
    # 전체 기간: 보관(arch) 제외, completed 있는 카드만 → p0 q0 p1 p2 p3 late
    allt = t["a3_all_time"]["total"]
    assert allt["cards"] == 6 and allt["dist"] == {"0": 3, "1": 1, "2+": 2} and allt["mean"] == 1.0


# ───────── (f) A5 ─────────

@pytest.mark.parametrize("error", [
    "pid 4321 not alive Worker's last output: ...", "Socket closed by peer", "HTTP 429 too many requests",
    "Gateway starting, try later", "anthropic rate_limit_error", "read TIMEOUT after 30s"])
def test_f_infra_errors(error):
    assert km.is_infra_failure("crashed", error) is True


@pytest.mark.parametrize("outcome,error", [
    ("crashed", "worker exited cleanly (rc=0) without kanban_complete"), ("reclaimed", None), ("gave_up", ""),
    ("completed", "socket"), (None, "pid 1 not alive"), ("review_requested", "429")])
def test_f_not_infra(outcome, error):
    assert km.is_infra_failure(outcome, error) is False


def test_f_a5_failure_rate_infra_split_and_rate_limited(tmp_path):
    runs = [
        ("c1", "coder-bot", "crashed", "pid 77 not alive", W46),
        ("c1", "coder-bot", "timed_out", "socket reset", W46),
        ("c1", "coder-bot", "gave_up", "got HTTP 429", W46),
        ("c1", "coder-bot", "crashed", "worker exited cleanly (rc=0)", W46),     # 기타
        ("c1", "coder-bot", "reclaimed", None, W46),                              # 기타
        ("c1", "coder-bot", "spawn_failed", "no such file", W46),                 # 기타
        ("c1", "coder-bot", "completed", None, W46),                              # 실패 아님
        ("c1", "coder-bot", None, None, W46),                                     # 실행 중: 분모만
        ("c1", "coder-bot", "rate_limited", None, W46),                           # 실패 목록 아님
        ("c1", "reviewer-bot", "rate_limited", None, W46),                        # 모든 프로필 집계
        ("c1", "reviewer-bot", "crashed", "pid 1 not alive", W46),                # coder 아님
    ]
    db = mkdb(tmp_path / "b.db", tasks=[T("c1")], runs=runs)
    cell = km.weekly_project_table({"x": db})["weeks"]["2026-W46"]["x"]
    assert cell["a5"] == {"coder_runs": 9, "failed": 6, "infra": 3, "other": 3, "rate": round(6 / 9, 4)}
    assert cell["rate_limited"] == 2


# ───────── (g) 카드 유형 ─────────

@pytest.mark.parametrize("title,body,expected", [
    ("로그인 구현", "버튼 추가", "구현"),
    ("README 갱신", "", "문서"),
    ("점수 측정", "A/B 비교", "분석"),
    ("기능 추가", "docs/04.md 를 고친다", "문서"),
    ("OOF 점수", "정리 필요", "문서"),                 # 문서·분석 단어가 같이 있으면 문서
    ("성능 평가", "x", "분석"),
    ("버그 수정", None, "구현"),                       # body NULL
    ("파일 이름 notes.md 변경", "", "문서"),
    ("mdx 파서", "", "구현"),                          # .md 는 \b 로 끝나야 한다
])
def test_g_card_type(title, body, expected):
    assert km.card_type(title, body) == expected


def test_g_fallback_ratio_line(tmp_path):
    db = mkdb(tmp_path / "b.db", tasks=[T("i1", title="추가"), T("d1", title="문서"), T("n1", title="무관")],
              runs=[("i1", "coder-bot", "completed", None, W46), ("d1", "coder-bot", "completed", None, W46),
                    ("n1", "reviewer-bot", "completed", None, W46)])           # n1 은 대상 카드 아님
    t = km.weekly_project_table({"x": db})
    assert t["type_fallback"]["total"] == {"implementation_no_keyword": 1, "target_cards": 2, "ratio": 0.5}
    assert "키워드 없이 구현으로 떨어진 대상 카드 비율: 1/2 (50%)" in km.render_weekly_project(t)


# ───────── (h) 보드 목록 ─────────

def _layout(home: Path) -> Path:
    mkdb(home / "kanban.db")
    mkdb(home / "kanban" / "boards" / "alpha" / "kanban.db")
    mkdb(home / "kanban" / "boards" / "beta" / "kanban.db")
    mkdb(home / "kanban" / "boards" / "_archived" / "kanban.db")                 # 뺀다
    (home / "kanban" / "boards" / "empty").mkdir()                               # kanban.db 없음 → 뺀다
    (home / "kanban" / "boards" / "stray.db").write_bytes(b"")                    # 폴더 아님 → 뺀다
    return home


def test_h_list_boards_finds_default_and_boards_and_skips_archived(tmp_path):
    home = _layout(tmp_path / "hh")
    got = km.list_boards(root=home)
    assert list(got) == ["default", "alpha", "beta"]
    assert got["default"] == home / "kanban.db" and got["alpha"] == home / "kanban" / "boards" / "alpha" / "kanban.db"
    # HOME 을 넘겨도(그 아래 .hermes) 같은 결과
    h2 = tmp_path / "fakehome"
    _layout(h2 / ".hermes")
    assert list(km.list_boards(root=h2)) == ["default", "alpha", "beta"]
    assert km.list_boards(root=tmp_path / "nothing") == {}


# ───────── (i) KST 주 경계 ─────────

def test_i_kst_week_boundaries():
    assert km.kst_week(ts(2026, 11, 15, 23, 30)) == "2026-W46"         # 일요일 23:30 KST → 그 주
    assert km.kst_week(ts(2026, 11, 16, 0, 10)) == "2026-W47"          # 월요일 00:10 KST → 다음 주
    # UTC 로는 일요일 15:30 이지만 KST 로는 월요일 00:30
    assert km.kst_week(datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc).timestamp()) == "2026-W47"
    assert km.kst_week(datetime(2026, 11, 15, 14, 59, tzinfo=timezone.utc).timestamp()) == "2026-W46"
    assert km.kst_week(ts(2027, 1, 1, 10, 0)) == "2026-W53"            # ISO 연도가 달력 연도와 다른 날


# ───────── 읽기 전용 · CLI ─────────

def test_read_only_connections_and_mtime_unchanged(tmp_path):
    src = (SCRIPTS / "kanban_metrics.py").read_text()
    calls = [ln for ln in src.splitlines() if "sqlite3.connect(" in ln]
    assert calls and all("mode=ro" in ln for ln in calls)
    db = mkdb(tmp_path / "b.db", tasks=[T("c1")], runs=[("c1", "coder-bot", "review_requested", None, W46)])
    before = os.stat(db).st_mtime_ns
    km.first_run_table({"x": db})
    km.weekly_project_table({"x": db})
    km.render(km.board_metrics("x", db, 0), None)
    assert os.stat(db).st_mtime_ns == before
    with pytest.raises(sqlite3.OperationalError):                               # 쓰기 시도는 실패해야 한다
        km.connect(db).execute("insert into tasks (id, title) values ('z', 'z')")


def test_weekly_project_table_marks_unreadable_board(tmp_path):
    ok = mkdb(tmp_path / "ok.db", tasks=[T("a")], runs=[("a", "coder-bot", "review_requested", None, W46)])
    t = km.weekly_project_table({"gone": tmp_path / "nope.db", "ok": ok})
    assert "gone" in t["read_failures"] and t["boards"] == ["ok"]
    assert t["week_totals"]["2026-W46"]["a1"]["rr"] == 1
    assert "읽기 실패" in km.render_weekly_project(t)


def _run_cli(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(SCRIPTS / "kanban_metrics.py"), *args],
                          capture_output=True, text=True, env=env)


def test_cli_default_board_included_and_json(tmp_path):
    home = tmp_path / "h"
    mkdb(home / ".hermes" / "kanban.db", tasks=[T("d1", assignee="reviewer-bot")],
         runs=[("d1", "coder-bot", "review_requested", None, W46)], events=[("d1", "changes_requested", W46)])
    mkdb(home / ".hermes" / "kanban" / "boards" / "alpha" / "kanban.db", tasks=[T("a1")],
         runs=[("a1", "coder-bot", "review_requested", None, W46)])
    r = _run_cli(home, "--days", "36500", "--weekly")                           # 기존 호출 형태
    assert r.returncode == 0 and "## 보드 `default`" in r.stdout and "## 보드 `alpha`" in r.stdout
    r = _run_cli(home, "default", "--by", "first-run", "--json")                # 위치 인자로 default
    data = json.loads(r.stdout)
    assert r.returncode == 0 and list(data["first_run"]["boards"]) == ["default"]
    assert data["first_run"]["boards"]["default"]["illusion"] == 1
    r = _run_cli(home, "--weekly", "--by-project", "--json")
    d = json.loads(r.stdout)["by_project"]
    assert d["week_totals"]["2026-W46"]["a1"] == {
        "rr": 2, "cr": 1, "rate": 0.5, "by_type": {"구현": {"rr": 2, "cr": 1}, "문서": {"rr": 0, "cr": 0}, "분석": {"rr": 0, "cr": 0}}}
    r = _run_cli(home, "--weekly", "--by-project")
    assert r.returncode == 0 and "| 2026-W46 | default |" in r.stdout and "**전체**" in r.stdout
    r = _run_cli(home, "--json")                                                # --json 단독은 오류
    assert r.returncode == 2
    r = _run_cli(home, "nosuch", "--by", "first-run")                           # 모르는 보드: 읽기 실패로 표시하고 종료 0
    assert r.returncode == 0 and "읽기 실패" in r.stdout
