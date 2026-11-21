#!/usr/bin/env python3
"""kanban 보드 운영 지표를 마크다운(또는 JSON)으로 출력한다 (읽기 전용).

사용:
  python3 kanban_metrics.py                 # 모든 보드(default 포함), 전체 기간
  python3 kanban_metrics.py <board> --days 7   # board 에 default 도 줄 수 있다
  python3 kanban_metrics.py --weekly        # 주별 추이 표 추가
  python3 kanban_metrics.py --by first-run  # 첫 런 프로필 기준 담당 표 (보드별 한 줄)
  python3 kanban_metrics.py --weekly --by-project [--days N]   # KST ISO 주 x 보드: A1·A2·A3·A5 + 카드 유형
  ... --json                                # 위 두 표를 JSON 으로 ({"first_run": ..., "by_project": ...})

지표 정의는 docs/04_운영지표.md 참고. DB는 모두 읽기 전용(URI mode=ro)으로 연다.
보드 = ~/.hermes/kanban.db (slug default) + ~/.hermes/kanban/boards/*/kanban.db (_archived 제외).
"""
import argparse
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

OPEN_STATES = ("ready", "running", "review", "blocked", "todo", "triage", "scheduled")

KST = timezone(timedelta(hours=9))
CODER = "coder-bot"
# A5: 실패로 세는 런 outcome
FAIL_OUTCOMES = frozenset({"crashed", "gave_up", "timed_out", "reclaimed", "spawn_failed"})
# A5: 인프라형 실패 = error 문구가 이 정규식에 맞는 것
INFRA_RE = re.compile(r"pid \d+ not alive|socket|Gateway starting|rate_limit|429|timeout", re.I)
# 카드 유형: 먼저 맞는 것 (문서 > 분석 > 구현)
DOC_RE = re.compile(r"문서|README|정리|보고|docs/|\.md\b")
ANALYSIS_RE = re.compile(r"측정|분석|비교|A/B|OOF|평가|재현|집계")
CARD_TYPES = ("구현", "문서", "분석")
# 첫 런 프로필 열 (그 밖은 other = 기타)
FIRST_RUN_PROFILES = ("coder-bot", "reviewer-bot", "fable-bot", "helper-bot")


# ───────────────────────── 보드 목록·연결 ─────────────────────────

def _hermes_home(root: Path | None = None) -> Path:
    """Hermes 홈. 기본 ~/.hermes. root 아래에 .hermes 폴더가 있으면(HOME을 넘긴 경우) 그것을 쓴다."""
    if root is None:
        return Path.home() / ".hermes"
    root = Path(root)
    return root / ".hermes" if (root / ".hermes").is_dir() else root


def list_boards(root: Path | None = None) -> dict[str, Path]:
    """{slug: kanban.db 경로}. default(루트 kanban.db) 먼저, boards/* 는 이름순, _archived 제외."""
    home = _hermes_home(root)
    out: dict[str, Path] = {}
    if (home / "kanban.db").is_file():
        out["default"] = home / "kanban.db"
    boards_dir = home / "kanban" / "boards"
    if boards_dir.is_dir():
        for p in sorted(boards_dir.iterdir()):
            if p.name == "_archived" or not p.is_dir() or not (p / "kanban.db").is_file():
                continue
            out.setdefault(p.name, p / "kanban.db")
    return out


def connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{quote(str(db))}?mode=ro", uri=True)  # 읽기 전용
    con.row_factory = sqlite3.Row
    return con


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


# ───────────────────────── 공통 보조 ─────────────────────────

def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b * 100:.0f}%)" if b else "0/0"


def _rate(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def kst_week(ts: float) -> str:
    """epoch 초 → KST(UTC+9) ISO 주 'YYYY-Www'."""
    y, w, _ = datetime.fromtimestamp(ts, KST).isocalendar()
    return f"{y}-W{w:02d}"


def card_type(title: str, body: str) -> str:
    """title+body 를 규칙으로 분류: 문서 > 분석 > 구현(그 밖)."""
    text = f"{title or ''}\n{body or ''}"
    if DOC_RE.search(text):
        return "문서"
    if ANALYSIS_RE.search(text):
        return "분석"
    return "구현"


def is_infra_failure(outcome: str | None, error: str | None) -> bool:
    """실패 런(outcome ∈ FAIL_OUTCOMES) 중 error 가 인프라형 문구인가."""
    return outcome in FAIL_OUTCOMES and bool(error) and INFRA_RE.search(error) is not None


# ───────────────────────── 기존 보드 지표 ─────────────────────────

def board_metrics(board: str, db: Path, since: float) -> dict:
    con = connect(db)
    ev = con.execute(
        "select task_id, kind, payload, created_at from task_events where created_at >= ?", (since,)
    ).fetchall()
    runs = con.execute(
        "select task_id, profile, status, outcome, error, started_at, ended_at "
        "from task_runs where started_at >= ?", (since,)
    ).fetchall()
    tasks = con.execute("select id, title, assignee, status, created_at, model_override from tasks").fetchall()
    con.close()

    kinds = Counter(r["kind"] for r in ev)

    # 리뷰: review_requested가 1번이라도 있던 태스크 = 리뷰 받은 태스크
    reviewed = {r["task_id"] for r in ev if r["kind"] == "review_requested"}
    cr_per_task = Counter(r["task_id"] for r in ev if r["kind"] == "changes_requested")
    rejected = [t for t in reviewed if cr_per_task.get(t)]
    rounds = [cr_per_task.get(t, 0) for t in reviewed]

    # 회수: stale(잠금 만료, 작업 유실 위험) vs manual(사람/봇이 수동)
    stale = manual = 0
    for r in ev:
        if r["kind"] == "reclaimed":
            p = json.loads(r["payload"] or "{}")
            if p.get("stale_lock"):
                stale += 1
            else:
                manual += 1

    # 사용자 승인 요청을 block으로 보낸 경우 (결정 권한 규칙 위반 신호)
    approval_blocks = 0
    for r in ev:
        if r["kind"] in ("blocked", "block_loop_detected"):
            reason = str(json.loads(r["payload"] or "{}").get("reason", ""))
            if "승인" in reason or "approval" in reason.lower():
                approval_blocks += 1

    # 프로필별 run
    by_prof = defaultdict(lambda: Counter())
    dur = defaultdict(list)
    for r in runs:
        by_prof[r["profile"]][r["outcome"] or r["status"]] += 1
        by_prof[r["profile"]]["_total"] += 1
        if r["ended_at"] and r["started_at"]:
            dur[r["profile"]].append((r["ended_at"] - r["started_at"]) / 60)

    created = [t for t in tasks if (t["created_at"] or 0) >= since]
    now = time.time()
    open_tasks = [
        (t["id"], t["status"], t["assignee"], (now - (t["created_at"] or now)) / 3600, t["title"])
        for t in tasks if t["status"] in OPEN_STATES
    ]
    return dict(
        board=board, kinds=kinds, created=len(created),
        completed=kinds.get("completed", 0),
        reviewed=len(reviewed), rejected=len(rejected), cr_total=sum(cr_per_task.values()),
        max_round=max(rounds) if rounds else 0,
        hit_cap=sum(1 for x in rounds if x >= 3),
        stale=stale, manual=manual, approval_blocks=approval_blocks,
        by_prof=by_prof, dur=dur, open_tasks=open_tasks,
        model_override=sum(1 for t in created if t["model_override"]),
    )


def weekly(db: Path, since: float) -> list:
    con = connect(db)
    rows = con.execute(
        "select strftime('%Y-%W', created_at, 'unixepoch', 'localtime') wk, kind, count(*) n "
        "from task_events where created_at >= ? and kind in "
        "('created','completed','review_requested','changes_requested','crashed','reclaimed','blocked') "
        "group by 1, 2 order by 1", (since,)
    ).fetchall()
    con.close()
    table = defaultdict(Counter)
    for r in rows:
        table[r["wk"]][r["kind"]] = r["n"]
    return sorted(table.items())


def render(m: dict, days: int | None) -> str:
    k = m["kinds"]
    span = f"최근 {days}일" if days else "전체 기간"
    out = [f"## 보드 `{m['board']}` — {span} (생성 {datetime.now():%Y-%m-%d %H:%M})", ""]
    out += [
        "| 지표 | 값 | 볼 점 |", "|---|---|---|",
        f"| 태스크 생성 / 완료 | {m['created']} / {m['completed']} | |",
        f"| 리뷰 받은 태스크 중 반려 1회 이상 | {pct(m['rejected'], m['reviewed'])} | 오르면 반려 사유 분류 |",
        f"| 반려 총횟수 / 최대 라운드 / 3회 상한 도달 | {m['cr_total']} / {m['max_round']} / {m['hit_cap']} | 상한 도달은 재설계 신호 |",
        f"| 크래시 (프로세스 사라짐) | {k.get('crashed', 0)} | 원인 미확정 — 이슈 표 참고 |",
        f"| 회수: 잠금 만료 / 수동 | {m['stale']} / {m['manual']} | 잠금 만료는 작업 유실 |",
        f"| 규칙 위반 종료 (protocol_violation) | {k.get('protocol_violation', 0)} | 0이어야 함 |",
        f"| 승인 요청을 block으로 보냄 | {m['approval_blocks']} | 0이어야 함 (결정 권한 규칙) |",
        f"| block 반복 감지 | {k.get('block_loop_detected', 0)} | 0이어야 함 |",
        f"| 태스크별 모델 지정 사용 | {m['model_override']} | 모델 배정 규칙 적용 여부 |",
        "",
        "| 프로필 | run | 완료 | 리뷰요청 | 반려받음 | 크래시 | 회수 | block | 중앙 시간(분) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for prof, c in sorted(m["by_prof"].items(), key=lambda kv: str(kv[0])):
        d = m["dur"].get(prof) or [0]
        out.append(
            f"| {prof} | {c['_total']} | {c['completed']} | {c['review_requested']} | "
            f"{c['changes_requested']} | {c['crashed']} | {c['reclaimed']} | {c['blocked']} | "
            f"{statistics.median(d):.1f} |"
        )
    if m["open_tasks"]:
        out += ["", "| 열린 태스크 | 상태 | 담당 | 경과(시간) | 제목 |", "|---|---|---|---|---|"]
        for tid, st, who, age, title in sorted(m["open_tasks"], key=lambda x: -x[3]):
            out.append(f"| {tid} | {st} | {who} | {age:.0f} | {title[:40]} |")
    return "\n".join(out)


# ───────────────────────── 첫 런 기준 담당 ─────────────────────────

def first_run_table(dbs: dict[str, Path]) -> dict:
    """보드별: 런 있는 카드 수, 첫 런(task_runs 가장 작은 id) 프로필별 카드 수, 담당 착시 건수.

    착시 = tasks.assignee='reviewer-bot' 인데 첫 런 프로필이 reviewer-bot 이 아닌 카드.
    열을 못 읽은 보드는 read_failures 에만 넣고 나머지는 계속한다.
    """
    boards: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for slug, db in dbs.items():
        try:
            with closing(connect(db)) as con:
                first = [(r[0], r[1]) for r in con.execute(
                    "select r.task_id, r.profile from task_runs r "
                    "where r.id = (select min(id) from task_runs where task_id = r.task_id)")]
                assignee = {r[0]: r[1] for r in con.execute("select id, assignee from tasks")}
        except sqlite3.Error as e:
            failures[slug] = _err(e)
            continue
        cols = Counter()
        other = Counter()
        illusion = 0
        for tid, prof in first:
            if prof in FIRST_RUN_PROFILES:
                cols[prof] += 1
            else:
                cols["other"] += 1
                other[str(prof) if prof is not None else "(없음)"] += 1
            if assignee.get(tid) == "reviewer-bot" and prof != "reviewer-bot":
                illusion += 1
        boards[slug] = {
            "cards_with_runs": len(first),
            "first_run": {p: cols[p] for p in (*FIRST_RUN_PROFILES, "other")},
            "other_profiles": dict(other),
            "assignee_reviewer": sum(1 for a in assignee.values() if a == "reviewer-bot"),
            "illusion": illusion,
        }
    total = {
        "cards_with_runs": sum(b["cards_with_runs"] for b in boards.values()),
        "first_run": {p: sum(b["first_run"][p] for b in boards.values()) for p in (*FIRST_RUN_PROFILES, "other")},
        "assignee_reviewer": sum(b["assignee_reviewer"] for b in boards.values()),
        "illusion": sum(b["illusion"] for b in boards.values()),
    }
    return {"boards": boards, "total": total, "read_failures": failures}


def render_first_run(t: dict) -> str:
    out = [
        "## 첫 런 프로필 기준 담당 (task_runs 가장 작은 id 의 profile)", "",
        "| 보드 | 런 있는 카드 | coder-bot | reviewer-bot | fable-bot | helper-bot | 기타 | assignee=reviewer-bot | 그중 첫 런은 다른 봇 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def row(name: str, b: dict) -> str:
        f = b["first_run"]
        return (f"| {name} | {b['cards_with_runs']} | {f['coder-bot']} | {f['reviewer-bot']} | {f['fable-bot']} | "
                f"{f['helper-bot']} | {f['other']} | {b['assignee_reviewer']} | {b['illusion']} |")

    for slug, b in t["boards"].items():
        out.append(row(slug, b))
    out.append(row("**합계**", t["total"]))
    for slug, msg in t["read_failures"].items():
        out += ["", f"읽기 실패: `{slug}` — {msg}"]
    return "\n".join(out)


# ───────────────────────── 주 × 보드 (A1·A2·A3·A5) ─────────────────────────

def _board_weekly(db: Path, since: float | None, until: float | None):
    """보드 하나의 주별 카운터. 반환: (week→Counter, a3 전체기간 Counter, 유형 폴백 (구현 수, 대상 카드 수), NULL 시작 런 수)."""
    with closing(connect(db)) as con:
        tasks = {r[0]: (r[1], r[2], r[3]) for r in con.execute("select id, title, body, status from tasks")}
        runs = [tuple(r) for r in con.execute(
            "select task_id, profile, outcome, error, started_at from task_runs")]
        events = [tuple(r) for r in con.execute(
            "select task_id, kind, created_at from task_events "
            "where kind in ('review_requested', 'changes_requested', 'completed')")]

    def in_window(ts: float | None) -> bool:
        return ts is not None and (since is None or ts >= since) and (until is None or ts < until)

    target = {tid for tid, prof, *_ in runs if prof == CODER}
    ctype = {t: card_type(*tasks.get(t, ("", "", None))[:2]) for t in target}
    weeks: dict[str, Counter] = defaultdict(Counter)
    null_started = 0

    for tid, prof, outcome, error, started in runs:
        if started is None:
            null_started += 1
            continue
        if not in_window(started):
            continue
        c = weeks[kst_week(started)]
        if outcome == "rate_limited":
            c["rate_limited"] += 1  # 모든 프로필
        if prof != CODER:
            continue
        c["a5_runs"] += 1  # outcome NULL(실행 중)도 분모에 포함
        if outcome in FAIL_OUTCOMES:
            c["a5_fail"] += 1
            c["a5_infra" if is_infra_failure(outcome, error) else "a5_other"] += 1
        if outcome == "review_requested":  # A1 분모 (NULL 은 아님)
            c["rr"] += 1
            c[f"rr:{ctype[tid]}"] += 1

    ev: dict[str, dict[str, list]] = defaultdict(lambda: {"review_requested": [], "changes_requested": [], "completed": []})
    for tid, kind, created in events:
        if tid in target and created is not None:
            ev[tid][kind].append(created)
    for tid, e in ev.items():
        for created in e["changes_requested"]:  # A1 분자 (이벤트 주)
            if in_window(created):
                c = weeks[kst_week(created)]
                c["cr"] += 1
                c[f"cr:{ctype[tid]}"] += 1

    a3_all: Counter = Counter()
    for tid in target:
        e = ev.get(tid)
        if not e:
            continue
        cr_n = len(e["changes_requested"])
        done = bool(e["completed"])
        if e["review_requested"]:  # A2: 첫 리뷰 요청 이벤트의 주
            first = min(e["review_requested"])
            if in_window(first):
                c = weeks[kst_week(first)]
                c["a2_first"] += 1
                if done:
                    c["a2_done"] += 1
                    c["a2_pass"] += cr_n == 0
                else:
                    c["a2_pending"] += 1
        if done:
            bucket = "2+" if cr_n >= 2 else str(cr_n)
            last = max(e["completed"])  # A3: 마지막 completed 이벤트의 주
            if in_window(last):
                c = weeks[kst_week(last)]
                c["a3_n"] += 1
                c[f"a3_{bucket}"] += 1
                c["a3_sum"] += cr_n
            if tasks.get(tid, ("", "", None))[2] != "archived":  # 전체 기간 분포는 보관 카드 제외
                a3_all["n"] += 1
                a3_all[bucket] += 1
                a3_all["sum"] += cr_n
    fallback = (sum(1 for t in ctype.values() if t == "구현"), len(target))
    weeks = {w: c for w, c in weeks.items() if any(c.values())}  # 비프로필 런만 있던 빈 주는 뺀다
    return weeks, a3_all, fallback, null_started


def _cell(c: Counter) -> dict:
    return {
        "a1": {
            "rr": c["rr"], "cr": c["cr"], "rate": _rate(c["cr"], c["rr"]),
            "by_type": {t: {"rr": c[f"rr:{t}"], "cr": c[f"cr:{t}"]} for t in CARD_TYPES},
        },
        "a2": {
            "first_review_cards": c["a2_first"], "completed": c["a2_done"], "passed": c["a2_pass"],
            "pending": c["a2_pending"], "rate": _rate(c["a2_pass"], c["a2_done"]),
        },
        "a3": {
            "cards": c["a3_n"], "dist": {k: c[f"a3_{k}"] for k in ("0", "1", "2+")},
            "cr_sum": c["a3_sum"], "mean": round(c["a3_sum"] / c["a3_n"], 3) if c["a3_n"] else None,
        },
        "a5": {
            "coder_runs": c["a5_runs"], "failed": c["a5_fail"], "infra": c["a5_infra"],
            "other": c["a5_other"], "rate": _rate(c["a5_fail"], c["a5_runs"]),
        },
        "rate_limited": c["rate_limited"],
    }


def _a3_all_cell(c: Counter) -> dict:
    return {
        "cards": c["n"], "dist": {k: c[k] for k in ("0", "1", "2+")}, "cr_sum": c["sum"],
        "mean": round(c["sum"] / c["n"], 3) if c["n"] else None,
    }


def weekly_project_table(dbs: dict[str, Path], since: float | None = None, until: float | None = None) -> dict:
    """KST ISO 주 × 보드 A1·A2·A3·A5 (+A1 카드 유형별). since/until 은 epoch 초 [since, until).

    weeks[주][보드] / week_totals[주] 셀 = {a1, a2, a3, a5, rate_limited}. a3_all_time 은 주 구분 없는
    전체 기간(보관 카드 제외, window 무시). 보드를 못 열면 read_failures 에 넣고 계속한다.
    """
    per: dict[str, dict[str, Counter]] = defaultdict(dict)  # 주 → 보드 → Counter
    a3_boards: dict[str, dict] = {}
    a3_sum = Counter()
    fb_boards: dict[str, dict] = {}
    fb_n = fb_t = 0
    null_started: dict[str, int] = {}
    failures: dict[str, str] = {}
    ok: list[str] = []
    for slug, db in dbs.items():
        try:
            weeks, a3_all, (fb_impl, fb_target), nulls = _board_weekly(db, since, until)
        except sqlite3.Error as e:
            failures[slug] = _err(e)
            continue
        ok.append(slug)
        for wk, c in weeks.items():
            per[wk][slug] = c
        a3_boards[slug] = _a3_all_cell(a3_all)
        a3_sum.update(a3_all)
        fb_boards[slug] = {"implementation_no_keyword": fb_impl, "target_cards": fb_target, "ratio": _rate(fb_impl, fb_target)}
        fb_n += fb_impl
        fb_t += fb_target
        null_started[slug] = nulls
    out_weeks: dict[str, dict] = {}
    totals: dict[str, dict] = {}
    for wk in sorted(per):
        out_weeks[wk] = {b: _cell(c) for b, c in sorted(per[wk].items())}
        tot = Counter()
        for c in per[wk].values():
            tot.update(c)
        totals[wk] = _cell(tot)
    return {
        "since": since, "until": until, "boards": ok,
        "weeks": out_weeks, "week_totals": totals,
        "a3_all_time": {"basis": "대상 카드 중 completed 이벤트가 있는 카드, status != archived, 기간 제한 없음",
                        "boards": a3_boards, "total": _a3_all_cell(a3_sum)},
        "type_fallback": {"boards": fb_boards, "total": {
            "implementation_no_keyword": fb_n, "target_cards": fb_t, "ratio": _rate(fb_n, fb_t)}},
        "excluded_null_started": {"boards": null_started, "total": sum(null_started.values())},
        "read_failures": failures,
    }


def render_weekly_project(t: dict) -> str:
    out = [
        "## 주(KST ISO) × 보드 — A1·A2·A3·A5 (대상 카드 = coder-bot 런이 있는 카드)", "",
        "| 주 | 보드 | A1 리뷰요청 | A1 반려 | A1 반려율 | 구현 rr/cr | 문서 rr/cr | 분석 rr/cr "
        "| A2 통과/분모 | A2 미완 | A3 완료 | A3 0/1/2+ | A3 평균 "
        "| A5 coder 런 | A5 실패 | 인프라/기타 | A5 실패율 | rate_limited |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def row(wk: str, name: str, x: dict) -> str:
        a1, a2, a3, a5 = x["a1"], x["a2"], x["a3"], x["a5"]
        ty = a1["by_type"]
        rate = f"{a1['rate']:.2f}" if a1["rate"] is not None else "-"
        mean = f"{a3['mean']:.2f}" if a3["mean"] is not None else "-"
        d = a3["dist"]
        return (
            f"| {wk} | {name} | {a1['rr']} | {a1['cr']} | {rate} "
            f"| {ty['구현']['rr']}/{ty['구현']['cr']} | {ty['문서']['rr']}/{ty['문서']['cr']} | {ty['분석']['rr']}/{ty['분석']['cr']} "
            f"| {pct(a2['passed'], a2['completed'])} | {a2['pending']} | {a3['cards']} | {d['0']}/{d['1']}/{d['2+']} | {mean} "
            f"| {a5['coder_runs']} | {a5['failed']} | {a5['infra']}/{a5['other']} "
            f"| {pct(a5['failed'], a5['coder_runs'])} | {x['rate_limited']} |"
        )

    for wk, boards in t["weeks"].items():
        for b, x in boards.items():
            out.append(row(wk, b, x))
        out.append(row(wk, "**전체**", t["week_totals"][wk]))
    allt = t["a3_all_time"]["total"]
    fb = t["type_fallback"]["total"]
    out += [
        "",
        f"- A3 전체 기간(보관 제외, completed 있는 대상 카드): {allt['cards']}장, 0/1/2+ = "
        f"{allt['dist']['0']}/{allt['dist']['1']}/{allt['dist']['2+']}, 평균 {allt['mean']}",
        f"- started_at NULL 이라 주 계산에서 뺀 런: {t['excluded_null_started']['total']}건",
        f"- 키워드 없이 구현으로 떨어진 대상 카드 비율: {pct(fb['implementation_no_keyword'], fb['target_cards'])}",
    ]
    for slug, msg in t["read_failures"].items():
        out.append(f"- 읽기 실패: `{slug}` — {msg}")
    return "\n".join(out)


# ───────────────────────── CLI ─────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*", help="보드 slug (default 포함, 생략 시 전부)")
    ap.add_argument("--days", type=int, help="최근 N일만")
    ap.add_argument("--weekly", action="store_true", help="주별 추이 표 추가")
    ap.add_argument("--by", choices=["first-run"], help="first-run: 첫 런 프로필 기준 담당 표")
    ap.add_argument("--by-project", action="store_true", help="KST ISO 주 × 보드 A1·A2·A3·A5 표 (--weekly 와 함께 써도 된다)")
    ap.add_argument("--json", action="store_true", help="--by first-run / --by-project 결과를 JSON 으로")
    a = ap.parse_args()
    if a.json and not (a.by or a.by_project):
        ap.error("--json 은 --by first-run 또는 --by-project 와 함께 쓴다")

    known = list_boards()
    names = a.boards or list(known)
    dbs = {n: known.get(n) or _hermes_home() / "kanban" / "boards" / n / "kanban.db" for n in names}

    if a.by or a.by_project:
        res, parts = {}, []
        if a.by == "first-run":
            res["first_run"] = first_run_table(dbs)
            parts.append(render_first_run(res["first_run"]))
        if a.by_project:
            since = time.time() - a.days * 86400 if a.days else None
            res["by_project"] = weekly_project_table(dbs, since=since)
            parts.append(render_weekly_project(res["by_project"]))
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else "\n\n".join(parts))
        return

    since = time.time() - a.days * 86400 if a.days else 0
    for b, db in dbs.items():
        try:
            print(render(board_metrics(b, db, since), a.days))
            if a.weekly:
                print("\n| 주(연-주차) | 생성 | 완료 | 리뷰요청 | 반려 | 크래시 | 회수 | block |")
                print("|---|---|---|---|---|---|---|---|")
                for wk, c in weekly(db, since):
                    print(f"| {wk} | {c['created']} | {c['completed']} | {c['review_requested']} | "
                          f"{c['changes_requested']} | {c['crashed']} | {c['reclaimed']} | {c['blocked']} |")
        except sqlite3.Error as e:
            print(f"## 보드 `{b}` — 읽기 실패: {_err(e)}")
        print()


if __name__ == "__main__":
    main()
