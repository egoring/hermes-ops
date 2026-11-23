"""scripts/eval_compare.py 단위 테스트 (임시 sqlite 픽스처, 표준 라이브러리 + PyYAML + pytest만 사용).

실행: python3 -m pytest scripts/tests/test_eval_compare.py -q
C5 카드 테스트 목록 1~14 (함수 이름의 t01~t14)와, 경계 사례·CLI 종료 코드를 더한 것이다.
"""
import json
import os
import random
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import eval_compare as ec  # noqa: E402
import kanban_metrics as km  # noqa: E402

KST = timezone(timedelta(hours=9))
DAY = 86400
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


def iso(epoch) -> str:
    return datetime.fromtimestamp(epoch, KST).isoformat(timespec="seconds")


class Board:
    """보드 하나의 런·이벤트를 모아 sqlite 로 저장한다. runs: (task_id, profile, outcome, error, started_at)."""

    def __init__(self):
        self.runs: list = []
        self.events: list = []

    def cards(self, prefix, t0, n, n_cr, step=3600):
        """카드 n장: coder review_requested 런 1개(t0 + i·step), 앞 n_cr장은 반려 이벤트도 1개."""
        for i in range(n):
            tid, t = f"{prefix}{i}", int(t0 + i * step)
            self.runs.append((tid, "coder-bot", "review_requested", None, t))
            self.events.append((tid, "review_requested", t + 10))
            if i < n_cr:
                self.events.append((tid, "changes_requested", t + 60))

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        for tid in {r[0] for r in self.runs} | {e[0] for e in self.events}:
            con.execute("insert into tasks (id, title, body, assignee, status) values (?,?,?,?,?)",
                        (tid, "", "", "coder-bot", "done"))
        for tid, prof, outcome, error, started in self.runs:
            con.execute("insert into task_runs (task_id, profile, outcome, error, started_at) values (?,?,?,?,?)",
                        (tid, prof, outcome, error, started))
        for tid, kind, created in self.events:
            con.execute("insert into task_events (task_id, kind, created_at) values (?,?,?)", (tid, kind, created))
        con.commit()
        con.close()
        return path


def units(board, prefix, n, n_cr):
    """합성 Unit: 카드 n장, 카드당 den 1, 앞 n_cr장은 num 1."""
    return [ec.Unit(board, f"{prefix}{i}", 1 if i < n_cr else 0, 1) for i in range(n)]


def change(at_epoch, kind="rule"):
    return {"at": iso(at_epoch), "profile": "all", "kind": kind, "note": "n", "ref": "r"}


# ───────── 1~3 층화 Δ·판정 ─────────

def test_t01_synthetic_delta_minus_010_is_better():
    before = units("X", "xb", 200, 60) + units("Y", "yb", 200, 60)   # 반려율 0.30
    after = units("X", "xa", 200, 40) + units("Y", "ya", 200, 40)    # 반려율 0.20
    s = ec.stratified_delta(before, after)
    assert s["delta"] == pytest.approx(-0.10, abs=0.01)
    lo, hi = ec.cluster_bootstrap(before, after)
    assert lo < -0.10 < hi
    assert ec.verdict(s["delta"], lo, hi) == "개선"


def test_t02_composition_change_only_is_not_a_change():
    # X 반려 0.40·Y 0.10 이 두 창에서 같고, 리뷰 요청 비중만 X 20% → 80%
    before = units("X", "xb", 80, 32) + units("Y", "yb", 320, 32)
    after = units("X", "xa", 320, 128) + units("Y", "ya", 80, 8)
    s = ec.stratified_delta(before, after)
    assert abs(s["delta"]) < 0.01
    assert s["simple_delta"] == pytest.approx(0.18, abs=0.01) and s["simple_delta"] >= 0.10
    lo, hi = ec.cluster_bootstrap(before, after)
    assert ec.verdict(s["delta"], lo, hi) == "변화 확인 못 함"


def test_t03_worse_is_symmetric():
    before = units("X", "xb", 200, 40) + units("Y", "yb", 200, 40)   # 0.20
    after = units("X", "xa", 200, 60) + units("Y", "ya", 200, 60)    # 0.30
    s = ec.stratified_delta(before, after)
    assert s["delta"] == pytest.approx(0.10, abs=0.01)
    lo, hi = ec.cluster_bootstrap(before, after)
    assert lo > 0 and ec.verdict(s["delta"], lo, hi) == "악화"


def test_verdict_thresholds_and_direction():
    assert ec.verdict(-0.05, -0.10, -0.01) == "개선"
    assert ec.verdict(-0.049, -0.10, -0.01) == "변화 확인 못 함"      # Δ 가 −thr 보다 작지 않음
    assert ec.verdict(-0.10, -0.20, 0.01) == "변화 확인 못 함"        # CI 가 0 을 포함
    assert ec.verdict(0.06, 0.01, 0.12) == "악화"
    assert ec.verdict(0.04, 0.01, 0.12) == "변화 확인 못 함"
    # A2(통과율)는 오르면 개선이라 higher_is_better 로 부호를 뒤집는다
    assert ec.verdict(0.10, 0.05, 0.15, higher_is_better=True) == "개선"
    assert ec.verdict(-0.10, -0.15, -0.05, higher_is_better=True) == "악화"


# ───────── 4~5 포함 기준·최소 표본 ─────────

def test_t04_project_below_min_den_is_excluded_with_reason():
    before = units("X", "xb", 40, 8) + units("Z", "zb", 14, 3)        # Z 앞 창 Σden 14
    after = units("X", "xa", 40, 8) + units("Z", "za", 50, 10)
    s = ec.stratified_delta(before, after)
    assert set(s["included"]) == {"X"}
    assert "14 < 15" in s["excluded"]["Z"]
    assert s["included"]["X"]["w"] == 1.0
    only_after = ec.stratified_delta(units("X", "xb", 40, 8), units("X", "xa", 40, 8) + units("N", "na", 30, 3))
    assert only_after["excluded"]["N"] == "앞 창 0건"                 # 한 창에만 있는 프로젝트


def test_t04b_exactly_min_den_is_included():
    s = ec.stratified_delta(units("X", "xb", 15, 3), units("X", "xa", 15, 3))
    assert set(s["included"]) == {"X"} and s["excluded"] == {}
    s2 = ec.stratified_delta(units("X", "xb", 15, 3), units("X", "xa", 16, 3), min_den=16)
    assert s2["included"] == {} and "앞 창 15 < 16" in s2["excluded"]["X"]


def test_bootstrap_ci_is_a_90_percent_interval():
    # 한 프로젝트, 앞 0.30·뒤 0.20(각 200장) → Δ 의 표준오차 ≈ 0.043, 90% 구간 폭 ≈ 2 × 1.645 × 0.043 ≈ 0.14
    before, after = units("X", "xb", 200, 60), units("X", "xa", 200, 40)
    lo, hi = ec.cluster_bootstrap(before, after)
    assert 0.12 < hi - lo < 0.16
    lo80, hi80 = ec.cluster_bootstrap(before, after, ci=0.80)
    assert (hi80 - lo80) < (hi - lo)
    assert ec._quantile(list(range(101)), 0.05) == pytest.approx(5.0)
    assert ec._quantile([0.0, 10.0], 0.25) == pytest.approx(2.5)


def test_stratified_weights_use_after_window_and_no_included_gives_none():
    before = units("X", "xb", 100, 10) + units("Y", "yb", 100, 50)
    after = units("X", "xa", 30, 3) + units("Y", "ya", 90, 18)
    s = ec.stratified_delta(before, after)
    assert s["included"]["X"]["w"] == pytest.approx(30 / 120) and s["included"]["Y"]["w"] == pytest.approx(90 / 120)
    assert s["delta"] == pytest.approx(0.25 * (0.1 - 0.1) + 0.75 * (0.2 - 0.5))
    assert (s["den_b_total"], s["den_a_total"]) == (200, 120)
    none = ec.stratified_delta(units("X", "xb", 5, 1), units("X", "xa", 5, 1))
    assert none["delta"] is None and none["included"] == {} and none["simple_delta"] == 0.0
    with pytest.raises(ValueError):
        ec.cluster_bootstrap(units("X", "xb", 5, 1), units("X", "xa", 5, 1))


def test_t05_total_den_below_min_total_is_insufficient(tmp_path):
    b1, b2 = Board(), Board()
    for b, name in ((b1, "p"), (b2, "q")):                              # 프로젝트마다 창당 20건 → 합 40 < 60
        b.cards(name + "b", ts(2026, 11, 3), 20, 5)
        b.cards(name + "a", ts(2026, 11, 10), 20, 5)
    dbs = {"p": b1.save(tmp_path / "p.db"), "q": b2.save(tmp_path / "q.db")}
    res = ec.compare(dbs, "A1", before=ec.parse_window("2026-11-02:2026-11-08"),
                     after=ec.parse_window("2026-11-09:2026-11-15"))
    assert res["verdict"] == "표본 부족" and res["ci"] is None
    assert (res["den_b_total"], res["den_a_total"]) == (40, 40)
    assert "표본 부족" in ec.render(res)


# ───────── 6~8 방식 2: 창 자르기·늘리기 ─────────

AT = ts(2026, 11, 20, 10, 27)


def test_t06_other_change_5_days_before_is_unjudgeable():
    w = ec.windows_for_change(AT, [change(AT - 5 * DAY), change(AT)])
    assert w["status"] == "판단 불가" and w["reason"] == "다른 변경과 겹침"
    assert w["before_days"] == 5
    # 뒤쪽도 마찬가지
    w2 = ec.windows_for_change(AT, [change(AT), change(AT + 6 * DAY)])
    assert w2["status"] == "판단 불가" and w2["after_days"] == 6


def test_t06b_compare_reports_unjudgeable_without_reading_data(tmp_path):
    res = ec.compare({}, "A1", at=AT, changes=[change(AT - 5 * DAY), change(AT)])
    assert res["verdict"] == "판단 불가" and res["reason"] == "다른 변경과 겹침"
    assert res["delta"] is None and res["ci"] is None
    assert res["overlap"] and "판단 불가" in ec.render(res)


def test_t07_other_change_10_days_before_shortens_before_window(tmp_path):
    w = ec.windows_for_change(AT, [change(AT - 10 * DAY), change(AT)])
    assert w["status"] == "ok" and w["before_days"] == 10 and w["after_days"] == 14
    assert w["before"] == (AT - 10 * DAY, AT)                           # 마지막 그 변경 시각부터
    dbs = {}
    for name in ("p", "q"):
        b = Board()
        b.cards(name + "b", AT - 9 * DAY, 30, 10)                       # 앞 창(10일) 안
        b.cards(name + "a", AT + 1 * DAY, 30, 10)
        dbs[name] = b.save(tmp_path / f"{name}.db")
    res = ec.compare(dbs, "A1", at=AT, changes=[change(AT - 10 * DAY), change(AT)])
    assert res["windows"]["before"]["days"] == 10 and res["windows"]["after"]["days"] == 14
    assert res["verdict"] == "변화 확인 못 함"                          # 판정 진행(판단 불가 아님)
    assert any("잘라" in n for n in res["notes"])


def test_t07b_other_change_inside_after_window_cuts_it():
    w = ec.windows_for_change(AT, [change(AT), change(AT + 9 * DAY)])
    assert w["status"] == "ok" and w["after_days"] == 9 and w["after"] == (AT, AT + 9 * DAY)
    # 창 끝 시각 정확히 위의 변경은 창 밖(끝 미포함)이라 자르지 않는다
    assert ec.windows_for_change(AT, [change(AT + 14 * DAY)])["after_days"] == 14


def test_t08_sample_short_at_14_days_extends_to_21(tmp_path):
    dbs = {}
    for name in ("p", "q"):
        b = Board()
        # 프로젝트당 14일 안에 20건, 15~21일 사이에 15건 더 (창마다)
        b.cards(f"{name}bn", AT - 13 * DAY, 20, 4)
        b.cards(f"{name}bf", AT - 20 * DAY, 15, 3)
        b.cards(f"{name}an", AT + 1 * DAY, 20, 4)
        b.cards(f"{name}af", AT + 15 * DAY, 15, 3)
        dbs[name] = b.save(tmp_path / f"{name}.db")
    res = ec.compare(dbs, "A1", at=AT, changes=[change(AT)])
    assert res["days"] == 21 and res["days_tried"] == [14, 21]
    assert res["verdict"] != "표본 부족"
    assert (res["den_b_total"], res["den_a_total"]) == (70, 70)
    assert res["windows"]["before"]["days"] == 21 and res["windows"]["after"]["days"] == 21
    text = ec.render(res)
    assert "days = 21" in text and "21일" in text


def test_t08b_still_short_at_28_gives_insufficient_and_cut_stops_extension(tmp_path):
    dbs = {}
    for name in ("p", "q"):
        b = Board()
        b.cards(f"{name}bn", AT - 13 * DAY, 16, 3)
        b.cards(f"{name}bf", AT - 25 * DAY, 5, 1)
        b.cards(f"{name}an", AT + 1 * DAY, 16, 3)
        b.cards(f"{name}af", AT + 22 * DAY, 5, 1)
        dbs[name] = b.save(tmp_path / f"{name}.db")
    res = ec.compare(dbs, "A1", at=AT, changes=[change(AT)])
    assert res["verdict"] == "표본 부족" and res["days_tried"] == [14, 21, 28]
    # 다른 변경으로 앞 창이 잘리면 더 늘리지 않는다
    cut = ec.compare(dbs, "A1", at=AT, changes=[change(AT - 10 * DAY), change(AT)])
    assert cut["verdict"] == "표본 부족" and cut["days_tried"] == [14]


# ───────── 9~10 부트스트랩 ─────────

def test_t09_bootstrap_same_seed_same_ci():
    before = units("X", "xb", 60, 18) + units("Y", "yb", 60, 12)
    after = units("X", "xa", 60, 12) + units("Y", "ya", 60, 9)
    a = ec.cluster_bootstrap(before, after, n=500, seed=3)
    b = ec.cluster_bootstrap(before, after, n=500, seed=3)
    c = ec.cluster_bootstrap(before, after, n=500, seed=4)
    assert a == b
    assert len(c) == 2 and c[0] <= c[1]                                 # 다른 seed 는 값만 다를 수 있다


def test_t10_resample_unit_is_the_card():
    big = ec.Unit("p", "big", 10, 10)                                   # rr 10·cr 10 인 카드 하나
    small = [ec.Unit("p", f"s{i}", 0, 1) for i in range(90)]            # rr 1·cr 0 카드 90장
    pool = [big] + small
    ids = {id(u) for u in pool}
    for seed in range(5):
        r = ec._resample(pool, random.Random(seed))
        assert len(r) == len(pool) and all(id(u) in ids for u in r)     # 원소가 원래 Unit 그대로
        k = sum(u is big for u in r)
        assert sum(u.num for u in r) == 10 * k                          # 큰 카드의 num·den 이 함께 움직인다
        assert sum(u.den for u in r) == 10 * k + (len(pool) - k)


def test_t10b_cluster_ci_is_wider_than_independent_runs():
    def pool(clustered):
        if clustered:
            return [ec.Unit("p", "big", 10, 10)] + [ec.Unit("p", f"s{i}", 0, 1) for i in range(90)]
        return [ec.Unit("p", f"r{i}", 1 if i < 10 else 0, 1) for i in range(100)]   # 같은 합(10/100), 카드 100장
    widths = []
    for clustered in (True, False):
        lo, hi = ec.cluster_bootstrap(pool(clustered), pool(clustered), n=1000, seed=1)
        widths.append(hi - lo)
    assert widths[0] > 2 * widths[1]


# ───────── 11~13 kanban_metrics 와 같은 지표 규칙 ─────────

def rand_board(seed: int) -> Board:
    """주 경계 시각·NULL 시작·다른 프로필·인프라형 오류가 섞인 무작위 보드."""
    rng = random.Random(seed)
    w45 = ts(2026, 11, 2, 0)
    b = Board()
    outcomes = ["review_requested", "review_requested", "completed", "crashed", "gave_up", "timed_out",
                "reclaimed", "spawn_failed", "blocked", None]
    errors = [None, "pid 123 not alive", "boom", "socket closed", "HTTP 429", "stale lock"]
    for i in range(70):
        tid = f"c{i}"
        for _ in range(rng.randint(1, 4)):
            prof = rng.choice(["coder-bot", "coder-bot", "coder-bot", "reviewer-bot"])
            roll = rng.random()
            if roll < 0.05:
                started = None                                          # NULL 시작 런은 주 계산에서 빠진다
            elif roll < 0.15:
                started = w45 + rng.choice([0, 7 * DAY, 14 * DAY, 21 * DAY - 1])   # 주 경계 시각
            else:
                started = w45 + rng.randint(0, 21 * DAY - 1)
            b.runs.append((tid, prof, rng.choice(outcomes), rng.choice(errors), started))
        for kind in ("review_requested", "changes_requested", "changes_requested", "completed"):
            for _ in range(rng.choice([0, 0, 1, 2])):
                b.events.append((tid, kind, w45 + rng.choice([rng.randint(0, 21 * DAY - 1), 7 * DAY, 14 * DAY])))
    for i in range(10):                                                 # coder 런이 없는 카드는 빠진다
        b.runs.append((f"r{i}", "reviewer-bot", "review_requested", None, w45 + i * 3600))
        b.events.append((f"r{i}", "changes_requested", w45 + i * 3600 + 5))
    return b


WEEKS = {"2026-W45": "2026-11-02:2026-11-08", "2026-W46": "2026-11-09:2026-11-15", "2026-W47": "2026-11-16:2026-11-22"}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t11_a1_a2_a5_match_kanban_metrics_by_project(tmp_path, seed):
    db = rand_board(seed).save(tmp_path / "x.db")
    table = km.weekly_project_table({"x": db})
    for wk, win in WEEKS.items():
        cell = table["weeks"].get(wk, {}).get("x")
        start, end = ec.parse_window(win)
        u1 = ec.load_units({"x": db}, start, end, "A1")
        u2, info = ec.load_units_detail({"x": db}, start, end, "A2")
        u5 = ec.load_units({"x": db}, start, end, "A5")
        if cell is None:
            assert not u1 and not u2 and not u5
            continue
        assert (sum(u.den for u in u1), sum(u.num for u in u1)) == (cell["a1"]["rr"], cell["a1"]["cr"])
        assert (sum(u.den for u in u2), sum(u.num for u in u2), info["pending"]) == (
            cell["a2"]["completed"], cell["a2"]["passed"], cell["a2"]["pending"])
        assert (sum(u.den for u in u5), sum(u.num for u in u5)) == (cell["a5"]["coder_runs"], cell["a5"]["other"])
    # 세 주를 하나의 창으로 합쳐도 같다
    start, end = ec.parse_window("2026-11-02:2026-11-22")
    u1 = ec.load_units({"x": db}, start, end, "A1")
    assert sum(u.den for u in u1) == sum(c["x"]["a1"]["rr"] for c in table["weeks"].values() if "x" in c)


def test_a1_card_with_three_review_runs_and_two_rejections_is_one_unit(tmp_path):
    b = Board()
    t = ts(2026, 11, 3)
    for i in range(3):
        b.runs.append(("c1", "coder-bot", "review_requested", None, t + i * 100))
    b.events += [("c1", "changes_requested", t + 50), ("c1", "changes_requested", t + 150)]
    b.runs.append(("c2", "coder-bot", "completed", None, t))             # den 0·num 0 → 넣지 않는다
    b.runs.append(("c3", "coder-bot", "completed", None, t))
    b.events.append(("c3", "changes_requested", t + 5))                  # den 0·num 1 은 넣는다
    db = b.save(tmp_path / "x.db")
    got = ec.load_units({"x": db}, *ec.parse_window("2026-11-02:2026-11-08"), "A1")
    assert got == [ec.Unit("x", "c1", 2, 3), ec.Unit("x", "c3", 1, 0)]


def test_window_boundary_start_inclusive_end_exclusive(tmp_path):
    start, end = ec.parse_window("2026-11-02:2026-11-08")
    assert (start, end) == (ts(2026, 11, 2, 0), ts(2026, 11, 9, 0))
    b = Board()
    for tid, t in (("in", start), ("out", end), ("last", end - 1)):
        b.runs.append((tid, "coder-bot", "review_requested", None, t))
    db = b.save(tmp_path / "x.db")
    got = ec.load_units({"x": db}, start, end, "A1")
    assert sorted(u.task_id for u in got) == ["in", "last"]
    for bad in ("2026-11-08:2026-11-02", "2026-11-02", "11-02:11-08", "2026-13-01:2026-13-02"):
        with pytest.raises(ValueError):
            ec.parse_window(bad)


def test_t12_a2_unfinished_cards_leave_the_denominator_and_are_counted(tmp_path):
    b = Board()
    t = ts(2026, 11, 3)
    for tid in ("ok", "rework", "open", "later"):
        b.runs.append((tid, "coder-bot", "review_requested", None, t))
    b.events += [
        ("ok", "review_requested", t), ("ok", "completed", t + 100),                       # 첫 통과
        ("rework", "review_requested", t), ("rework", "changes_requested", t + 10),
        ("rework", "review_requested", t + 20), ("rework", "completed", t + 100),          # 반려 뒤 완료
        ("open", "review_requested", t),                                                   # 안 끝남
        ("later", "review_requested", ts(2026, 11, 12)), ("later", "completed", ts(2026, 11, 12, 13)),  # 첫 리뷰가 창 밖
    ]
    db = b.save(tmp_path / "x.db")
    got, info = ec.load_units_detail({"x": db}, *ec.parse_window("2026-11-02:2026-11-08"), "A2")
    assert sorted(got) == [ec.Unit("x", "ok", 1, 1), ec.Unit("x", "rework", 0, 1)]
    assert info["pending"] == 1
    res = ec.compare({"x": db}, "A2", before=ec.parse_window("2026-11-02:2026-11-08"),
                     after=ec.parse_window("2026-11-09:2026-11-15"))
    assert res["pending"] == {"before": 1, "after": 0} and res["higher_is_better"] is True
    assert "아직 안 끝나 분모에서 뺀 카드: 앞 1장" in ec.render(res)


def test_t13_a5_infra_failures_are_not_in_numerator(tmp_path):
    b = Board()
    t = ts(2026, 11, 3)
    b.runs += [
        ("c1", "coder-bot", "crashed", "pid 123 not alive", t),          # 인프라형 → num 에서 빠짐
        ("c1", "coder-bot", "crashed", "boom", t + 10),                  # 기타 실패 → num
        ("c1", "coder-bot", "completed", None, t + 20),
        ("c1", "coder-bot", None, None, t + 30),                         # 실행 중: 분모만
        ("c1", "reviewer-bot", "crashed", "boom", t + 40),               # 다른 프로필: 제외
        ("c2", "coder-bot", "gave_up", "429 too many", t),               # 인프라형
        ("c2", "coder-bot", "timed_out", "tool stuck", t + 5),           # 기타 실패
    ]
    db = b.save(tmp_path / "x.db")
    got = ec.load_units({"x": db}, *ec.parse_window("2026-11-02:2026-11-08"), "A5")
    assert got == [ec.Unit("x", "c1", 1, 4), ec.Unit("x", "c2", 1, 2)]


def test_unreadable_board_is_reported_and_others_continue(tmp_path):
    b = Board()
    b.cards("c", ts(2026, 11, 3), 3, 1)
    ok = b.save(tmp_path / "ok.db")
    got, info = ec.load_units_detail({"gone": tmp_path / "nope.db", "ok": ok},
                                     *ec.parse_window("2026-11-02:2026-11-08"), "A1")
    assert len(got) == 3 and "gone" in info["read_failures"]
    with pytest.raises(ValueError):
        ec.load_units({"ok": ok}, 0, 1, "A9")


def test_loading_does_not_modify_the_database(tmp_path):
    b = Board()
    b.cards("c", ts(2026, 11, 3), 5, 2)
    db = b.save(tmp_path / "x.db")
    before = db.read_bytes()
    ec.compare({"x": db}, "A1", before=ec.parse_window("2026-11-02:2026-11-08"),
               after=ec.parse_window("2026-11-09:2026-11-15"))
    assert db.read_bytes() == before


# ───────── 14 변경 기록부 ─────────

def good(at="2026-11-20T10:27+09:00", **kw):
    return {"at": at, "profile": "coder-bot", "kind": "effort", "note": "메모", "ref": "D1", **kw}


def test_t14_validate_changes_each_defect_is_one_error():
    assert ec.validate_changes([good(), good("2026-11-21T09:00+09:00", kind="model", profile="all")]) == []
    assert len(ec.validate_changes([good("2026-11-20T10:27")])) == 1                 # +09:00 없음
    assert len(ec.validate_changes([good("2026-11-20T10:27+00:00")])) == 1           # 다른 시간대
    assert len(ec.validate_changes([good(kind="tuning")])) == 1                      # 잘못된 kind
    assert len(ec.validate_changes([good(profile="x-bot")])) == 1
    assert len(ec.validate_changes([good(note="  ")])) == 1                          # 빈 note
    assert len(ec.validate_changes([good(ref="")])) == 1
    rev = ec.validate_changes([good("2026-11-20T10:27+09:00"), good("2026-11-19T10:27+09:00")])
    assert len(rev) == 1 and "#2" in rev[0]                                          # 시각 역순
    assert len(ec.validate_changes([good("not-a-time+09:00")])) == 1
    assert len(ec.validate_changes([{"at": "2026-11-20T10:27+09:00"}])) == 4         # profile·kind·note·ref 없음
    assert ec.validate_changes("x") and ec.validate_changes(["x"])
    # 같은 시각 두 항목은 역순이 아니다
    assert ec.validate_changes([good(), good()]) == []


def test_load_changes_from_yaml(tmp_path):
    p = tmp_path / "changes.yaml"
    assert ec.load_changes(p) == []                                                  # 파일 없음 → 빈 목록
    p.write_text('changes:\n  - {at: "2026-11-20T10:27+09:00", profile: coder-bot, kind: effort, note: n, ref: r}\n'
                 '  - {at: 2026-11-21T09:00:00+09:00, profile: all, kind: rule, note: n, ref: r}\n', encoding="utf-8")
    items = ec.load_changes(p)
    assert [i["at"][:16] for i in items] == ["2026-11-20T10:27", "2026-11-21T09:00"]
    assert ec.validate_changes(items) == []                                          # YAML datetime 도 문자열로
    p.write_text("changes: []\n", encoding="utf-8")
    assert ec.load_changes(p) == []
    p.write_text("foo: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ec.load_changes(p)


# ───────── CLI ─────────

def make_home(tmp_path) -> Path:
    home = tmp_path / "home"
    for name, path in (("default", home / ".hermes" / "kanban.db"),
                       ("alpha", home / ".hermes" / "kanban" / "boards" / "alpha" / "kanban.db"),
                       ("beta", home / ".hermes" / "kanban" / "boards" / "beta" / "kanban.db")):
        b = Board()
        b.cards(name + "b", ts(2026, 11, 3), 40, 12)
        b.cards(name + "a", ts(2026, 11, 10), 40, 8)
        b.save(path)
    return home


def run_cli(home, *args):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run([sys.executable, str(SCRIPTS / "eval_compare.py"), *args], capture_output=True,
                          text=True, env=env)


def test_cli_human_json_and_exit_codes(tmp_path):
    home = make_home(tmp_path)
    args = ("--metric", "A1", "--before", "2026-11-02:2026-11-08", "--after", "2026-11-09:2026-11-15")
    r = run_cli(home, *args)                                                          # changes.yaml 없음 → 경고 없이 진행
    assert r.returncode == 0 and r.stderr == ""
    for needle in ("alpha", "beta", "default", "층화 Δ", "90% CI", "단순 Δ", "참고: 판정에 쓰지 않음", "판정:"):
        assert needle in r.stdout
    j = run_cli(home, *args, "--json")
    res = json.loads(j.stdout)
    assert j.returncode == 0 and set(res["included"]) == {"alpha", "beta", "default"}
    assert res["delta"] == pytest.approx(-0.10) and res["den_b_total"] == 120
    assert res["verdict"] in ("개선", "변화 확인 못 함")
    assert run_cli(home, "--metric", "A1", "--before", "bad", "--after", "2026-11-09:2026-11-15").returncode == 2
    assert run_cli(home, "--metric", "A1", "--before", "2026-11-02:2026-11-08").returncode == 2   # 창 하나만
    assert run_cli(home, "--metric", "A1", "--change", "2026-11-20T10:27").returncode == 2        # 시간대 없음
    assert run_cli(home, "--metric", "A3", *args[2:]).returncode == 2                              # 모르는 지표
    bad = tmp_path / "bad.yaml"
    bad.write_text('changes:\n  - {at: "2026-11-20T10:27", profile: all, kind: rule, note: n, ref: r}\n', encoding="utf-8")
    v = run_cli(home, "--validate-changes", str(bad))
    assert v.returncode == 1 and "+09:00" in v.stdout
    assert run_cli(home, *args, "--changes", str(bad)).returncode == 2                             # 잘못된 기록부로 비교 금지
    assert run_cli(home, "--validate-changes", str(tmp_path / "none.yaml")).returncode == 2


def test_cli_change_mode_uses_changes_file_and_warns_in_windows(tmp_path):
    home = make_home(tmp_path)
    cf = tmp_path / "c.yaml"
    cf.write_text('changes:\n  - {at: "2026-11-09T12:00+09:00", profile: all, kind: rule, note: 중간 변경, ref: r}\n'
                  '  - {at: "2026-11-20T10:27+09:00", profile: coder-bot, kind: effort, note: n, ref: r}\n',
                  encoding="utf-8")
    ok = run_cli(home, "--metric", "A1", "--before", "2026-11-02:2026-11-08", "--after", "2026-11-09:2026-11-15",
                 "--changes", str(cf))
    assert ok.returncode == 0 and "주의: 뒤 창 안에 다른 변경이 있다" in ok.stdout and "중간 변경" in ok.stdout
    r = run_cli(home, "--metric", "A1", "--change", "2026-11-20T10:27+09:00", "--changes", str(cf))
    assert r.returncode == 0 and "판정: 판단 불가" not in r.stdout                                   # 11-09 변경은 11일 앞이라 자른다
    assert "앞 창을 다른 변경" in r.stdout
    assert (tmp_path / "c.yaml").read_text(encoding="utf-8").count("changes") == 1               # 기록부는 읽기만
