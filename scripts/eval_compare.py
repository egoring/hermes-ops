#!/usr/bin/env python3
"""변경 시각 앞뒤 창의 A1·A2·A5를 프로젝트(보드)로 층화해 비교한다 (읽기 전용, LLM 0).

사용:
  # 방식 1: 창을 직접 준다 (KST 날짜, 양끝 포함 → [시작일 00:00, 끝날 다음날 00:00))
  python3 eval_compare.py --metric A1 --before 2026-11-02:2026-11-08 --after 2026-11-09:2026-11-15
  # 방식 2: 변경 시각만 준다. 변경 기록부(--changes)로 창을 자르고, 표본이 모자라면 14→21→28일로 늘린다
  python3 eval_compare.py --metric A1 --change 2026-11-20T10:27+09:00
  # 변경 기록부 검사만
  python3 eval_compare.py --validate-changes ~/.hermes/evals/changes.yaml

지표 정의(A1 반려율·A2 첫 리뷰 통과율·A5 실패 런율)는 kanban_metrics.py 와 같고, 같은 보드 목록·연결·
인프라 실패 판별을 import 해서 쓴다. 비교 방법은 docs/09 §5.2.4:
  층 = 프로젝트(보드). 두 창 모두 Σden ≥ min_den 인 프로젝트만 넣는다.
  Δ = Σ w_p (r_뒤,p − r_앞,p), w_p = 뒤 창에서 넣은 프로젝트들 Σden 중 p 의 비율.
  불확실성 = 카드 단위 군집 부트스트랩(프로젝트 안에서 카드를 다시 뽑음) 90% CI.
  판정 = 개선 / 악화 / 변화 확인 못 함 (+ 표본 부족 / 판단 불가).
"변화 확인 못 함"은 효과가 없다는 뜻이 아니다. 창이 짧고 표본이 작아 못 잡은 것일 수 있다.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))  # kanban_metrics 를 같은 폴더에서 import
import kanban_metrics as km  # noqa: E402

KST = km.KST
CODER = km.CODER
DAY = 86400.0

# 지표별 이름과 방향. A2 는 통과율이라 오를수록 좋고, A1·A5 는 낮을수록 좋다.
METRICS = {
    "A1": {"name": "반려율(런 기준)", "higher_is_better": False},
    "A2": {"name": "첫 리뷰 통과율(카드 기준)", "higher_is_better": True},
    "A5": {"name": "실패 런율(인프라형 제외)", "higher_is_better": False},
}

PROFILES = frozenset({"coder-bot", "reviewer-bot", "helper-bot", "fable-bot", "all"})
KINDS = frozenset({"effort", "model", "soul", "skill", "plugin", "guard", "rule", "hermes"})
TZ_SUFFIX = "+09:00"

V_BETTER, V_WORSE, V_UNSURE = "개선", "악화", "변화 확인 못 함"
V_SMALL, V_UNJUDGEABLE = "표본 부족", "판단 불가"


class Unit(NamedTuple):
    """카드 하나(군집 단위). num/den 의 뜻은 지표마다 다르다(load_units 참고)."""
    board: str
    task_id: str
    num: int
    den: int


# ───────────────────────── 창 ─────────────────────────

def parse_window(s: str) -> tuple[float, float]:
    """'YYYY-MM-DD:YYYY-MM-DD'(KST, 양끝 날짜 포함) → [시작일 00:00, 끝날 다음날 00:00) epoch 초."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})", str(s).strip())
    if not m:
        raise ValueError(f"창 형식이 YYYY-MM-DD:YYYY-MM-DD 가 아니다: {s!r}")
    d0, d1 = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    if d1 < d0:
        raise ValueError(f"창의 끝 날짜가 시작 날짜보다 이르다: {s!r}")
    start = datetime.combine(d0, dtime.min, tzinfo=KST).timestamp()
    end = datetime.combine(d1 + timedelta(days=1), dtime.min, tzinfo=KST).timestamp()
    return start, end


def _epoch(v) -> float:
    """ISO 8601 문자열·datetime·숫자 → epoch 초. 시간대가 없는 문자열·datetime 은 오류."""
    if isinstance(v, bool):
        raise ValueError(f"시각이 아니다: {v!r}")
    if isinstance(v, (int, float)):
        return float(v)
    dt = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).strip())
    if dt.tzinfo is None:
        raise ValueError(f"시간대가 없다: {v!r}")
    return dt.timestamp()


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d %H:%M")


def _days(a: float, b: float) -> float:
    return round((b - a) / DAY, 4)


# ───────────────────────── 변경 기록부 ─────────────────────────

def load_changes(path) -> list[dict]:
    """changes.yaml 의 `changes:` 목록. 파일이 없으면 빈 목록. 구조가 틀리면 ValueError.

    `at` 가 YAML datetime 으로 읽히면 ISO 문자열로 되돌린다(시간대 없으면 검사에서 걸린다).
    """
    p = Path(path).expanduser()
    if not p.is_file():
        return []
    import yaml  # 변경 기록부를 읽을 때만 필요

    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"{p.name}: YAML 을 읽지 못했다: {e}") from e
    if data is None:
        return []
    if not isinstance(data, dict) or "changes" not in data:
        raise ValueError(f"{p.name}: 최상위 키 `changes:` 가 없다")
    items = data["changes"]
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{p.name}: `changes:` 아래가 목록이 아니다")
    out = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("at"), datetime):
            it = {**it, "at": it["at"].isoformat()}
        out.append(it)
    return out


def validate_changes(items) -> list[str]:
    """변경 기록부 항목 검사. 오류 문장 목록(없으면 []). 항목·필드마다 오류는 최대 1개."""
    if not isinstance(items, list):
        return ["changes 가 목록이 아니다"]
    errs: list[str] = []
    latest: tuple[float, int] | None = None  # 지금까지 본 가장 늦은 시각 (시각 오름차순 검사)
    for i, it in enumerate(items, 1):
        tag = f"#{i}"
        if not isinstance(it, dict):
            errs.append(f"{tag}: 항목이 키-값 묶음이 아니다")
            continue
        at = it.get("at")
        t = None
        if not isinstance(at, str) or not at.strip():
            errs.append(f"{tag}: at 가 없다")
        elif not at.strip().endswith(TZ_SUFFIX):
            errs.append(f"{tag}: at {at!r} 에 {TZ_SUFFIX} 시간대가 없다")
        else:
            try:
                t = _epoch(at)
            except ValueError:
                errs.append(f"{tag}: at {at!r} 은 ISO 8601 시각이 아니다")
        if t is not None:
            if latest is not None and t < latest[0]:
                errs.append(f"{tag}: at {at!r} 가 #{latest[1]} 보다 이르다 (시각 오름차순이어야 한다)")
            else:
                latest = (t, i)
        for key, allowed in (("profile", PROFILES), ("kind", KINDS)):
            v = it.get(key)
            if v not in allowed:
                errs.append(f"{tag}: {key} {v!r} 은 허용값({'|'.join(sorted(allowed))})이 아니다")
        for key in ("note", "ref"):
            v = it.get(key)
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{tag}: {key} 가 비었다")
    return errs


def windows_for_change(at: float, changes: list[dict], days: int = 14, min_days: int = 7,
                       max_days: int = 28) -> dict:
    """변경 시각 at 앞뒤 창. 앞 [at−days, at), 뒤 [at, at+days).

    다른 변경이 앞 창 안에 있으면 마지막 그 변경 시각부터, 뒤 창 안에 있으면 첫 그 변경 시각 전까지로 줄인다.
    어느 쪽이든 min_days 보다 짧아지면 status = "판단 불가". 같은 시각의 항목(자기 자신 포함)은
    같은 변경으로 본다. days 는 max_days 를 넘지 않는다.

    반환: {status: "ok"|"판단 불가", reason?, at, days, before: (시작, 끝), after: (시작, 끝),
           before_days, after_days, cut_before, cut_after (잘라낸 다른 변경의 시각 또는 None)}
    """
    days = min(days, max_days)
    others = sorted(t for t in (_epoch(c["at"]) for c in changes) if abs(t - at) > 1e-6)
    b_start, a_end = at - days * DAY, at + days * DAY
    cut_b = max((t for t in others if b_start <= t < at), default=None)
    cut_a = min((t for t in others if at < t < a_end), default=None)
    if cut_b is not None:
        b_start = cut_b
    if cut_a is not None:
        a_end = cut_a
    res = {
        "status": "ok", "at": at, "days": days,
        "before": (b_start, at), "after": (at, a_end),
        "before_days": _days(b_start, at), "after_days": _days(at, a_end),
        "cut_before": cut_b, "cut_after": cut_a,
    }
    if res["before_days"] < min_days - 1e-9 or res["after_days"] < min_days - 1e-9:
        res.update(status=V_UNJUDGEABLE, reason="다른 변경과 겹침", min_days=min_days)
    return res


# ───────────────────────── 단위(카드) 적재 ─────────────────────────

def _load_board(board: str, db: Path, start: float, end: float, metric: str) -> tuple[list[Unit], int]:
    """보드 하나의 Unit 목록과 (A2) 아직 안 끝난 카드 수. kanban_metrics 의 주 × 보드 규칙을 창에 그대로 쓴다."""
    with closing(km.connect(db)) as con:
        runs = [tuple(r) for r in con.execute(
            "select task_id, profile, outcome, error, started_at from task_runs")]
        events = [tuple(r) for r in con.execute(
            "select task_id, kind, created_at from task_events "
            "where kind in ('review_requested', 'changes_requested', 'completed')")]

    def in_window(ts) -> bool:
        return ts is not None and start <= ts < end  # 시작 포함, 끝 미포함

    target = {tid for tid, prof, *_ in runs if prof == CODER}  # coder-bot 런이 하나라도 있는 카드
    units: list[Unit] = []
    pending = 0

    if metric == "A1":
        den: Counter = Counter()
        num: Counter = Counter()
        for tid, prof, outcome, _err, started in runs:
            if prof == CODER and outcome == "review_requested" and in_window(started):
                den[tid] += 1
        for tid, kind, created in events:
            if kind == "changes_requested" and tid in target and in_window(created):
                num[tid] += 1
        units = [Unit(board, t, num[t], den[t]) for t in sorted(den.keys() | num.keys())]
    elif metric == "A2":
        ev: dict[str, dict] = defaultdict(lambda: {"rr": [], "cr": 0, "done": False})
        for tid, kind, created in events:
            if tid not in target or created is None:
                continue
            if kind == "review_requested":
                ev[tid]["rr"].append(created)
            elif kind == "changes_requested":
                ev[tid]["cr"] += 1  # 창 제한 없이 그 카드의 전체 반려 수 (kanban_metrics 와 같다)
            else:
                ev[tid]["done"] = True
        for tid in sorted(ev):
            e = ev[tid]
            if not e["rr"] or not in_window(min(e["rr"])):  # 첫 review_requested 가 창 안에 있는 카드
                continue
            if e["done"]:
                units.append(Unit(board, tid, int(e["cr"] == 0), 1))
            else:
                pending += 1
    elif metric == "A5":
        den = Counter()
        num = Counter()
        for tid, prof, outcome, error, started in runs:
            if prof != CODER or not in_window(started):
                continue
            den[tid] += 1  # outcome NULL(실행 중)도 분모에 포함
            if outcome in km.FAIL_OUTCOMES and not km.is_infra_failure(outcome, error):
                num[tid] += 1
        units = [Unit(board, t, num[t], den[t]) for t in sorted(den)]
    else:
        raise ValueError(f"지원하지 않는 지표: {metric!r} (A1·A2·A5)")
    return units, pending


def load_units_detail(dbs: dict[str, Path], start: float, end: float, metric: str) -> tuple[list[Unit], dict]:
    """load_units + 부가 정보 {pending: A2 에서 분모에서 뺀 안 끝난 카드 수, read_failures: {보드: 사유}}.

    보드 하나를 못 읽어도 나머지는 계속하고 read_failures 에 적는다.
    """
    if metric not in METRICS:
        raise ValueError(f"지원하지 않는 지표: {metric!r} (A1·A2·A5)")
    units: list[Unit] = []
    pending = 0
    failures: dict[str, str] = {}
    for board, db in dbs.items():
        try:
            u, p = _load_board(board, Path(db), start, end, metric)
        except sqlite3.Error as e:
            failures[board] = f"{type(e).__name__}: {e}"
            continue
        units += u
        pending += p
    return units, {"pending": pending, "read_failures": failures}


def load_units(dbs: dict[str, Path], start: float, end: float, metric: str) -> list[Unit]:
    """창 [start, end) 의 카드 단위 (board, task_id, num, den).

    A1: den = coder-bot review_requested 런 수(started_at 이 창 안), num = changes_requested 이벤트 수(창 안).
    A2: 첫 review_requested 이벤트가 창 안이고 completed 인 카드 = den 1, 반려 0회면 num 1. 안 끝난 카드는 뺀다
        (수는 load_units_detail 의 pending).
    A5: den = coder 런 수(started_at 이 창 안), num = 그중 FAIL_OUTCOMES 이면서 인프라형이 아닌 런 수.
    """
    return load_units_detail(dbs, start, end, metric)[0]


# ───────────────────────── 층화 추정·부트스트랩·판정 ─────────────────────────

def _sum_by_board(units: list[Unit]) -> dict[str, tuple[int, int]]:
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for u in units:
        acc[u.board][0] += u.num
        acc[u.board][1] += u.den
    return {b: (n, d) for b, (n, d) in acc.items()}


def stratified_delta(before: list[Unit], after: list[Unit], min_den: int = 15) -> dict:
    """프로젝트별 r = Σnum/Σden. 두 창 모두 Σden ≥ min_den 인 프로젝트만 넣고, Δ = Σ w_p (r_뒤 − r_앞).

    w_p = 뒤 창에서 넣은 프로젝트들 Σden 중 p 의 비율. simple_delta = 층화 없이 전체 Σnum/Σden 의 차이(참고용).
    den_b_total·den_a_total = 넣은 프로젝트들의 앞·뒤 창 Σden (최소 표본 검사에 쓴다).
    넣은 프로젝트가 0개면 delta = None.
    """
    nb, na = _sum_by_board(before), _sum_by_board(after)
    included: dict[str, dict] = {}
    excluded: dict[str, str] = {}
    for p in sorted(set(nb) | set(na)):
        (num_b, den_b), (num_a, den_a) = nb.get(p, (0, 0)), na.get(p, (0, 0))
        why = []
        for label, d in (("앞 창", den_b), ("뒤 창", den_a)):
            if d < min_den:
                why.append(f"{label} 0건" if d == 0 else f"{label} {d} < {min_den}")
        if why:
            excluded[p] = ", ".join(why)
        else:
            included[p] = {"den_b": den_b, "num_b": num_b, "den_a": den_a, "num_a": num_a, "w": 0.0}
    den_a_total = sum(v["den_a"] for v in included.values())
    den_b_total = sum(v["den_b"] for v in included.values())
    delta = None
    if included:
        delta = 0.0
        for v in included.values():
            v["w"] = v["den_a"] / den_a_total
            delta += v["w"] * (v["num_a"] / v["den_a"] - v["num_b"] / v["den_b"])
    all_b = sum(d for _, d in nb.values())
    all_a = sum(d for _, d in na.values())
    simple = None
    if all_b and all_a:
        simple = sum(n for n, _ in na.values()) / all_a - sum(n for n, _ in nb.values()) / all_b
    return {"delta": delta, "simple_delta": simple, "included": included, "excluded": excluded,
            "den_b_total": den_b_total, "den_a_total": den_a_total}


def _resample(units: list[Unit], rng: random.Random) -> list[Unit]:
    """카드(Unit) 단위 복원추출. 뽑힌 원소는 원래 Unit 그대로라 한 카드의 num·den 이 함께 움직인다."""
    return rng.choices(units, k=len(units))


def _quantile(sorted_vals: list[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def cluster_bootstrap(before: list[Unit], after: list[Unit], n: int = 2000, seed: int = 0,
                      ci: float = 0.90, min_den: int = 15) -> tuple[float, float]:
    """넣은 프로젝트 안에서 카드 단위로 창마다 따로 복원추출해 층화 Δ 를 n 번 다시 계산 → (하한, 상한) 백분위 CI.

    포함 프로젝트와 가중치 w_p 는 원표본 기준으로 고정한다. 넣은 프로젝트가 0개면 ValueError.
    """
    strat = stratified_delta(before, after, min_den)
    if not strat["included"]:
        raise ValueError("넣은 프로젝트가 없어 부트스트랩을 할 수 없다")
    projects = sorted(strat["included"])
    weight = {p: strat["included"][p]["w"] for p in projects}
    by_b: dict[str, list[Unit]] = defaultdict(list)
    by_a: dict[str, list[Unit]] = defaultdict(list)
    for u in before:
        if u.board in weight:
            by_b[u.board].append(u)
    for u in after:
        if u.board in weight:
            by_a[u.board].append(u)

    rng = random.Random(seed)
    deltas: list[float] = []
    attempts = 0
    while len(deltas) < n and attempts < n * 5:
        attempts += 1
        d = 0.0
        for p in projects:
            rb, ra = _resample(by_b[p], rng), _resample(by_a[p], rng)
            den_b, den_a = sum(u.den for u in rb), sum(u.den for u in ra)
            if den_b == 0 or den_a == 0:  # 비율을 못 정하는 복제는 버린다(Σden ≥ min_den 이라 드물다)
                break
            d += weight[p] * (sum(u.num for u in ra) / den_a - sum(u.num for u in rb) / den_b)
        else:
            deltas.append(d)
    if not deltas:
        raise ValueError("부트스트랩 복제를 만들지 못했다")
    deltas.sort()
    tail = (1.0 - ci) / 2.0
    return _quantile(deltas, tail), _quantile(deltas, 1.0 - tail)


def verdict(delta: float, lo: float, hi: float, thr: float = 0.05, higher_is_better: bool = False) -> str:
    """개선(hi < 0 이고 Δ ≤ −thr) / 악화(lo > 0 이고 Δ ≥ +thr) / 변화 확인 못 함.

    기본은 낮을수록 좋은 지표(A1·A5). 통과율(A2)처럼 높을수록 좋으면 higher_is_better=True 로 부호를 뒤집는다.
    """
    if higher_is_better:
        delta, lo, hi = -delta, -hi, -lo
    if hi < 0 and delta <= -thr:
        return V_BETTER
    if lo > 0 and delta >= thr:
        return V_WORSE
    return V_UNSURE


# ───────────────────────── 비교 ─────────────────────────

def _window_info(win: tuple[float, float]) -> dict:
    return {"start": _fmt(win[0]), "end": _fmt(win[1]), "start_epoch": win[0], "end_epoch": win[1],
            "days": _days(*win)}


def _changes_in(changes: list[dict], wins: dict[str, tuple[float, float]]) -> list[dict]:
    out = []
    for c in changes:
        t = _epoch(c["at"])
        for name, (s, e) in wins.items():
            if s <= t < e:
                out.append({"at": c["at"], "window": name, "profile": c.get("profile"),
                            "kind": c.get("kind"), "note": c.get("note")})
    return out


def _project_table(before: list[Unit], after: list[Unit], strat: dict) -> dict:
    nb, na = _sum_by_board(before), _sum_by_board(after)
    table = {}
    for p in sorted(set(nb) | set(na)):
        (num_b, den_b), (num_a, den_a) = nb.get(p, (0, 0)), na.get(p, (0, 0))
        inc = strat["included"].get(p)
        table[p] = {"num_b": num_b, "den_b": den_b, "num_a": num_a, "den_a": den_a,
                    "included": inc is not None, "w": inc["w"] if inc else None,
                    "reason": strat["excluded"].get(p)}
    return table


def _judge(dbs: dict[str, Path], metric: str, b_win: tuple[float, float], a_win: tuple[float, float],
           min_den: int, min_total: int, boot: int, seed: int) -> dict:
    """고정된 두 창을 비교한다(자르거나 늘리지 않음)."""
    before, info_b = load_units_detail(dbs, b_win[0], b_win[1], metric)
    after, info_a = load_units_detail(dbs, a_win[0], a_win[1], metric)
    strat = stratified_delta(before, after, min_den)
    res = {
        "metric": metric, "metric_name": METRICS[metric]["name"],
        "higher_is_better": METRICS[metric]["higher_is_better"],
        "windows": {"before": _window_info(b_win), "after": _window_info(a_win)},
        "min_den": min_den, "min_total": min_total, "boot": boot, "seed": seed, "threshold": 0.05,
        "delta": strat["delta"], "simple_delta": strat["simple_delta"], "ci": None, "ci_level": 0.90,
        "included": strat["included"], "excluded": strat["excluded"],
        "den_b_total": strat["den_b_total"], "den_a_total": strat["den_a_total"],
        "projects": _project_table(before, after, strat),
        "pending": {"before": info_b["pending"], "after": info_a["pending"]} if metric == "A2" else None,
        "read_failures": {"before": info_b["read_failures"], "after": info_a["read_failures"]},
        "notes": [],
    }
    if not strat["included"]:
        res["verdict"], res["reason"] = V_SMALL, f"두 창 모두 Σden ≥ {min_den} 인 프로젝트가 없다"
    elif min(strat["den_b_total"], strat["den_a_total"]) < min_total:
        res["verdict"] = V_SMALL
        res["reason"] = (f"넣은 프로젝트 Σden 앞 {strat['den_b_total']}·뒤 {strat['den_a_total']} "
                         f"(창마다 {min_total} 이상 필요)")
    else:
        lo, hi = cluster_bootstrap(before, after, n=boot, seed=seed, min_den=min_den)
        res["ci"] = [lo, hi]
        res["verdict"] = verdict(strat["delta"], lo, hi, higher_is_better=METRICS[metric]["higher_is_better"])
    if a_win[1] > time.time():
        res["notes"].append("뒤 창이 아직 끝나지 않았다(지금까지의 데이터).")
    return res


def _unjudgeable(metric: str, w: dict, min_den: int, min_total: int, boot: int, seed: int) -> dict:
    """windows_for_change 가 판단 불가를 낸 경우의 결과(데이터는 읽지 않는다)."""
    return {
        "metric": metric, "metric_name": METRICS[metric]["name"],
        "higher_is_better": METRICS[metric]["higher_is_better"],
        "windows": {"before": _window_info(w["before"]), "after": _window_info(w["after"])},
        "min_den": min_den, "min_total": min_total, "boot": boot, "seed": seed, "threshold": 0.05,
        "verdict": V_UNJUDGEABLE, "reason": w["reason"], "min_days": w["min_days"],
        "delta": None, "simple_delta": None, "ci": None, "ci_level": 0.90,
        "included": {}, "excluded": {}, "den_b_total": 0, "den_a_total": 0, "projects": {},
        "pending": None, "read_failures": {"before": {}, "after": {}}, "notes": [],
    }


def compare(dbs: dict[str, Path], metric: str, *, before: tuple[float, float] | None = None,
            after: tuple[float, float] | None = None, at: float | None = None,
            changes: list[dict] | None = None, min_den: int = 15, min_total: int = 60,
            boot: int = 2000, seed: int = 0) -> dict:
    """방식 1(before·after 창 그대로) 또는 방식 2(at: 변경 시각 → windows_for_change 로 창 결정).

    방식 2: 넣은 프로젝트 Σden 이 어느 창이든 min_total 미만이면 days 를 14 → 21 → 28 로 늘려 다시 본다.
    다른 변경으로 창이 잘렸으면 더 늘리지 않는다. 그래도 모자라면 표본 부족.
    """
    if metric not in METRICS:
        raise ValueError(f"지원하지 않는 지표: {metric!r} (A1·A2·A5)")
    changes = list(changes or [])
    if before is not None and after is not None and at is None:
        res = _judge(dbs, metric, before, after, min_den, min_total, boot, seed)
        res["mode"] = "windows"
        res["changes_in_windows"] = _changes_in(changes, {"앞 창": before, "뒤 창": after})
        return res
    if at is None or before is not None or after is not None:
        raise ValueError("before·after 를 함께 주거나, at 하나만 준다")

    tried: list[int] = []
    for days in (14, 21, 28):
        w = windows_for_change(at, changes, days=days)
        tried.append(days)
        if w["status"] != "ok":
            res = _unjudgeable(metric, w, min_den, min_total, boot, seed)
            res["overlap"] = [c for c in _changes_in(changes, {"앞 창": (at - days * DAY, at), "뒤 창": (at, at + days * DAY)})
                              if abs(_epoch(c["at"]) - at) > 1e-6]
            break
        res = _judge(dbs, metric, w["before"], w["after"], min_den, min_total, boot, seed)
        res["cut"] = {"before": w["cut_before"], "after": w["cut_after"]}
        for key, label in (("before", "앞 창"), ("after", "뒤 창")):
            if w[f"cut_{key}"] is not None:
                res["notes"].append(f"{label}을 다른 변경({_fmt(w[f'cut_{key}'])} KST)에서 잘라 {w[f'{key}_days']:g}일로 줄였다.")
        if res["verdict"] != V_SMALL or w["cut_before"] is not None or w["cut_after"] is not None:
            break  # 판정이 났거나, 다른 변경으로 창이 잘려 더 늘려도 소용없다
    res["mode"] = "change"
    res["at"] = datetime.fromtimestamp(at, KST).isoformat(timespec="minutes")
    res["days"] = tried[-1]
    res["days_tried"] = tried
    if res["verdict"] != V_UNJUDGEABLE and tried[-1] != 14:
        res["notes"].append(f"표본이 모자라 창을 {tried[-1]}일로 늘렸다(시도: {'→'.join(map(str, tried))}).")
    return res


# ───────────────────────── 출력 ─────────────────────────

def _rate(n: int, d: int) -> str:
    return f"{n / d:.3f}" if d else "-"


def render(res: dict) -> str:
    m = res["metric"]
    better = "높을수록 좋음" if res.get("higher_is_better") else "낮을수록 좋음"
    out = [f"## {m} {res['metric_name']} 앞뒤 비교 — 프로젝트(보드)로 층화, {better}", ""]
    for key, label in (("before", "앞 창"), ("after", "뒤 창")):
        w = res["windows"][key]
        out.append(f"- {label}: {w['start']} ~ {w['end']} KST (끝 미포함, {w['days']:g}일)")
    if res["mode"] == "change":
        out.append(f"- 기준 변경: {res['at']} (days = {res['days']}, 시도 {'→'.join(map(str, res['days_tried']))})")
    for c in res.get("changes_in_windows", []):
        out.append(f"주의: {c['window']} 안에 다른 변경이 있다 — {c['at']} {c.get('profile')}/{c.get('kind')} {c.get('note')}")
    for c in res.get("overlap", []):
        out.append(f"주의: {c['window']} 안에 다른 변경이 있다 — {c['at']} {c.get('profile')}/{c.get('kind')} {c.get('note')}")
    for note in res["notes"]:
        out.append(f"- 참고: {note}")
    out.append("")
    if res["verdict"] == V_UNJUDGEABLE:
        out += [f"판정: {V_UNJUDGEABLE} — {res['reason']} (창이 {res['min_days']}일보다 짧아진다: "
                f"앞 {res['windows']['before']['days']:g}일·뒤 {res['windows']['after']['days']:g}일)"]
        return "\n".join(out)
    out += ["| 프로젝트 | 앞 num/den (rate) | 뒤 num/den (rate) | w | 넣음/뺌 |", "|---|---|---|---|---|"]
    for p, t in res["projects"].items():
        w = f"{t['w']:.3f} ({t['den_a']}/{res['den_a_total']})" if t["included"] else "-"
        state = "넣음" if t["included"] else f"뺌: {t['reason']}"
        out.append(f"| {p} | {t['num_b']}/{t['den_b']} ({_rate(t['num_b'], t['den_b'])}) "
                   f"| {t['num_a']}/{t['den_a']} ({_rate(t['num_a'], t['den_a'])}) | {w} | {state} |")
    out.append("")
    out.append(f"- 넣은 프로젝트 Σden: 앞 {res['den_b_total']}·뒤 {res['den_a_total']} (창마다 {res['min_total']} 이상 필요)")
    if res["pending"] is not None:
        out.append(f"- 아직 안 끝나 분모에서 뺀 카드: 앞 {res['pending']['before']}장·뒤 {res['pending']['after']}장")
    for key, label in (("before", "앞 창"), ("after", "뒤 창")):
        for slug, msg in res["read_failures"][key].items():
            out.append(f"경고: 보드 `{slug}` 읽기 실패({label}) — {msg}")
    if res["delta"] is not None:
        tag = "" if res["ci"] else " (참고: 표본 부족이라 CI·판정 없음)"
        out.append(f"- 층화 Δ(뒤 − 앞): {res['delta']:+.4f}{tag}")
    if res["ci"]:
        lo, hi = res["ci"]
        out.append(f"- {res['ci_level'] * 100:.0f}% CI: [{lo:+.4f}, {hi:+.4f}] "
                   f"(카드 단위 군집 부트스트랩 {res['boot']}회, seed {res['seed']})")
    if res["simple_delta"] is not None:
        out.append(f"- 단순 Δ: {res['simple_delta']:+.4f} — 참고: 판정에 쓰지 않음 (프로젝트 구성 변화 확인용)")
    out.append("")
    reason = f" — {res['reason']}" if res.get("reason") else ""
    out.append(f"판정: {res['verdict']}{reason}")
    if res["verdict"] == V_UNSURE:
        out.append("※ \"변화 확인 못 함\"은 효과가 없다는 뜻이 아니다. 이 비교는 반려율이 약 0.07 넘게 움직이는 변화만 잡는다(09 §5.2.4-7).")
    return "\n".join(out)


# ───────────────────────── CLI ─────────────────────────

def main(argv: list[str] | None = None) -> int:
    default_changes = Path.home() / ".hermes" / "evals" / "changes.yaml"
    ap = argparse.ArgumentParser(description="변경 전후 A1·A2·A5 층화 비교 (읽기 전용, LLM 0)")
    ap.add_argument("--metric", choices=sorted(METRICS), help="비교할 지표")
    ap.add_argument("--before", help="앞 창 YYYY-MM-DD:YYYY-MM-DD (KST, 양끝 포함) — 방식 1")
    ap.add_argument("--after", help="뒤 창 YYYY-MM-DD:YYYY-MM-DD — 방식 1")
    ap.add_argument("--change", help="변경 시각(ISO 8601, 시간대 필수) — 방식 2: 변경 기록부로 창을 정한다")
    ap.add_argument("--changes", default=str(default_changes), help="변경 기록부 경로 (기본 %(default)s, 없으면 빈 목록)")
    ap.add_argument("--min-den", type=int, default=15, help="프로젝트를 넣는 최소 Σden (창마다)")
    ap.add_argument("--min-total", type=int, default=60, help="넣은 프로젝트 Σden 합의 최소값 (창마다)")
    ap.add_argument("--boot", type=int, default=2000, help="부트스트랩 횟수")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", action="store_true", help="같은 내용을 JSON 으로")
    ap.add_argument("--validate-changes", metavar="PATH", help="변경 기록부 검사만 하고 끝낸다")
    a = ap.parse_args(argv)

    try:
        if a.validate_changes:
            path = Path(a.validate_changes).expanduser()
            if not path.is_file():
                raise ValueError(f"파일이 없다: {path}")
            errs = validate_changes(load_changes(path))
            if errs:
                print("\n".join(f"오류: {e}" for e in errs))
                return 1
            print(f"OK: 항목 {len(load_changes(path))}개, 오류 0")
            return 0

        if not a.metric:
            ap.error("--metric 이 필요하다")
        if a.change:
            if a.before or a.after:
                ap.error("--change 는 --before/--after 와 함께 쓰지 않는다")
        elif not (a.before and a.after):
            ap.error("--before 와 --after 를 함께 주거나, --change 를 준다")
        if a.min_den < 1 or a.min_total < 1 or a.boot < 1:
            ap.error("--min-den, --min-total, --boot 는 1 이상이어야 한다")

        changes = load_changes(a.changes)
        errs = validate_changes(changes)
        if errs:
            raise ValueError(f"변경 기록부 {a.changes} 오류 {len(errs)}건: " + "; ".join(errs))
        kw = dict(changes=changes, min_den=a.min_den, min_total=a.min_total, boot=a.boot, seed=a.seed)
        dbs = km.list_boards()
        if a.change:
            res = compare(dbs, a.metric, at=_epoch(a.change), **kw)
        else:
            res = compare(dbs, a.metric, before=parse_window(a.before), after=parse_window(a.after), **kw)
    except ValueError as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2

    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
