#!/usr/bin/env python3
"""C9(11-04 15:41, 공용 AGENTS.md 반영 시각) 전후 판정 — 읽기 전용, LLM 0.

기준선(04_운영지표 §3.1, 10/05~11/04)의 원래 분류 쿼리는 남아 있지 않다.
그래서 같은 규칙을 앞·뒤 창에 똑같이 적용해 비교한다(절대값은 기준선 21·65와 다를 수 있다).

분류 규칙(고정):
- crashed 중 '대기형': worker_output에 `sleep N`(N≥30) 또는 poll/폴링/기다리/wait for
- blocked 중 '외부 대기': reason에 대기/기다/끝나면/완료되면/진행 중/실행 중/학습 중/돌고/ETA/timeout,
  단 승인·결정·사용자·override가 있으면 '승인·결정 대기'로 따로 센다.
- 정규화: 같은 창의 spawned(런 시작) 100건당.
"""
from __future__ import annotations
import json, re, sqlite3, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
C9 = datetime(2026, 11, 4, 15, 41, 9, tzinfo=KST).timestamp()
BEFORE = (C9 - 30 * 86400, C9)
AFTER = (C9, time.time())
HOME = Path.home() / ".hermes"
DBS = {"default": HOME / "kanban.db"}
for p in sorted((HOME / "kanban" / "boards").glob("*/kanban.db")):
    if p.stat().st_size > 0:  # _archived 아래는 glob 깊이가 달라 빠진다
        DBS[p.parent.name] = p

SLEEP = re.compile(r"\bsleep\s+(\d+)")
WAITY = re.compile(r"poll|폴링|기다리|wait(ing)? for", re.I)
EXT = re.compile(r"대기|기다|끝나면|완료되면|진행 ?중|실행 ?중|학습 ?중|돌고|ETA|timeout|타임아웃", re.I)
APPR = re.compile(r"승인|결정|사용자|override|확인 필요", re.I)


def classify_crash(payload: dict) -> bool:
    out = payload.get("worker_output") or ""
    if any(int(n) >= 30 for n in SLEEP.findall(out)):
        return True
    return bool(WAITY.search(out))


def classify_block(payload: dict) -> str:
    r = payload.get("reason") or ""
    if APPR.search(r):
        return "approval"
    if EXT.search(r):
        return "external"
    return "other"


def window(lo, hi):
    agg = {"spawned": 0, "crashed": 0, "crash_wait": 0, "blocked": 0, "block_ext": 0,
           "block_appr": 0, "scheduled": 0, "per_board": {}}
    for name, path in DBS.items():
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        b = {"spawned": 0, "crashed": 0, "crash_wait": 0, "blocked": 0, "block_ext": 0, "scheduled": 0}
        for kind, payload in con.execute(
                "select kind, payload from task_events where created_at>=? and created_at<? "
                "and kind in ('spawned','crashed','blocked','scheduled')", (lo, hi)):
            try:
                p = json.loads(payload) if payload else {}
            except ValueError:
                p = {}
            if kind == "spawned":
                b["spawned"] += 1
            elif kind == "scheduled":
                b["scheduled"] += 1
            elif kind == "crashed":
                b["crashed"] += 1
                b["crash_wait"] += classify_crash(p)
            elif kind == "blocked":
                b["blocked"] += 1
                c = classify_block(p)
                b["block_ext"] += c == "external"
                agg["block_appr"] += c == "approval"
        con.close()
        for k, v in b.items():
            agg[k] += v
        agg["per_board"][name] = b
    return agg


def rate(n, d):
    return round(100 * n / d, 2) if d else None


if __name__ == "__main__":
    a, b = window(*BEFORE), window(*AFTER)
    days_a, days_b = (BEFORE[1] - BEFORE[0]) / 86400, (AFTER[1] - AFTER[0]) / 86400
    rows = [("spawned(런)", "spawned"), ("crashed", "crashed"), ("crashed 중 대기형", "crash_wait"),
            ("blocked", "blocked"), ("blocked 중 외부 대기", "block_ext"), ("blocked 중 승인·결정", "block_appr"),
            ("scheduled(C9 권장 경로)", "scheduled")]
    print(f"창: 앞 {days_a:.1f}일 / 뒤 {days_b:.1f}일, 보드 {list(DBS)}")
    print("| 지표 | 앞(건) | 뒤(건) | 앞(100런당) | 뒤(100런당) |")
    print("|---|---|---|---|---|")
    for label, k in rows:
        ra = rate(a[k], a["spawned"]) if k != "spawned" else "-"
        rb = rate(b[k], b["spawned"]) if k != "spawned" else "-"
        print(f"| {label} | {a[k]} | {b[k]} | {ra} | {rb} |")
    print("\n보드별 (앞→뒤) spawned / crash_wait / block_ext / scheduled")
    for name in DBS:
        pa, pb = a["per_board"][name], b["per_board"][name]
        print(f"- {name}: {pa['spawned']}→{pb['spawned']} / {pa['crash_wait']}→{pb['crash_wait']} / "
              f"{pa['block_ext']}→{pb['block_ext']} / {pa['scheduled']}→{pb['scheduled']}")
    json.dump({"before": a, "after": b, "c9": C9}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1) if len(sys.argv) > 1 else None
