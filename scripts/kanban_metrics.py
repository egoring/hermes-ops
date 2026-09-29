#!/usr/bin/env python3
"""kanban 보드 운영 지표를 마크다운으로 출력한다 (읽기 전용).

사용:
  python3 kanban_metrics.py                 # 모든 보드, 전체 기간
  python3 kanban_metrics.py <board> --days 7
  python3 kanban_metrics.py --weekly        # 주별 추이 표 추가

지표 정의는 docs/04_운영지표.md 참고. DB는 read-only(URI mode=ro)로 연다.
"""
import argparse
import json
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BOARDS_DIR = Path.home() / ".hermes/kanban/boards"
OPEN_STATES = ("ready", "running", "review", "blocked", "todo", "triage", "scheduled")


def connect(board: str) -> sqlite3.Connection:
    db = BOARDS_DIR / board / "kanban.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # 읽기 전용
    con.row_factory = sqlite3.Row
    return con


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b * 100:.0f}%)" if b else "0/0"


def board_metrics(board: str, since: float) -> dict:
    con = connect(board)
    ev = con.execute(
        "select task_id, kind, payload, created_at from task_events where created_at >= ?", (since,)
    ).fetchall()
    runs = con.execute(
        "select task_id, profile, status, outcome, error, started_at, ended_at "
        "from task_runs where started_at >= ?", (since,)
    ).fetchall()
    tasks = con.execute("select id, title, assignee, status, created_at, model_override from tasks").fetchall()

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


def weekly(board: str, since: float) -> list:
    con = connect(board)
    rows = con.execute(
        "select strftime('%Y-%W', created_at, 'unixepoch', 'localtime') wk, kind, count(*) n "
        "from task_events where created_at >= ? and kind in "
        "('created','completed','review_requested','changes_requested','crashed','reclaimed','blocked') "
        "group by 1, 2 order by 1", (since,)
    ).fetchall()
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
    for prof, c in sorted(m["by_prof"].items()):
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*", help="보드 slug (생략 시 전부)")
    ap.add_argument("--days", type=int, help="최근 N일만")
    ap.add_argument("--weekly", action="store_true", help="주별 추이 표 추가")
    a = ap.parse_args()
    since = time.time() - a.days * 86400 if a.days else 0
    boards = a.boards or sorted(p.name for p in BOARDS_DIR.iterdir() if (p / "kanban.db").exists())
    for b in boards:
        print(render(board_metrics(b, since), a.days))
        if a.weekly:
            print("\n| 주(연-주차) | 생성 | 완료 | 리뷰요청 | 반려 | 크래시 | 회수 | block |")
            print("|---|---|---|---|---|---|---|---|")
            for wk, c in weekly(b, since):
                print(f"| {wk} | {c['created']} | {c['completed']} | {c['review_requested']} | "
                      f"{c['changes_requested']} | {c['crashed']} | {c['reclaimed']} | {c['blocked']} |")
        print()


if __name__ == "__main__":
    main()
