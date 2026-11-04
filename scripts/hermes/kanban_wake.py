#!/usr/bin/env python3
"""kanban 자동 깨우기 (no_agent cron, 15분마다).

scheduled 상태 카드 중 마지막 scheduled 사유에 `SCHEDULED_UNTIL=<ISO8601>`이 있고
그 시각이 지난 카드를 `hermes kanban --board <b> unblock`으로 깨운다 → ready → 담당 봇이 다시 배정된다.

- `SCHEDULED_UNTIL=`이 없는 scheduled 카드(사람/리뷰어가 Park한 카드)는 건드리지 않는다.
- 시각에 타임존이 없으면 KST(+09:00)로 본다.
- 같은 카드를 MAX_WAKES번 넘게 자동으로 깨웠으면 더 깨우지 않고 한 번만 알린다(hang 의심).
- 깨운 카드·형식 오류·상한 도달이 있을 때만 Discord로 알린다(멘션 없음). 없으면 출력 없음.

상태: ~/.hermes/scripts/.kanban_wake_state.json (알린 형식 오류·상한 카드, 중복 알림 방지)
옵션: --dry-run  실제로 깨우지 않고 대상만 출력
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _notify  # noqa: E402

BOARDS = Path.home() / ".hermes" / "kanban" / "boards"
STATE_FILE = Path(__file__).with_name(".kanban_wake_state.json")
KST = timezone(timedelta(hours=9))
MAX_WAKES = 12            # 카드당 자동 깨우기 상한
WAKE_TAG = "[auto-wake]"  # unblock 코멘트 머리표 (깨운 횟수 집계용)
MARK = re.compile(r"SCHEDULED_UNTIL=(\S+)")  # 값 해석 실패는 형식 오류로 알린다


def parse_until(raw: str) -> datetime | None:
    """ISO8601 문자열 → aware datetime. 타임존 없으면 KST. 실패하면 None."""
    try:
        dt = datetime.fromisoformat(raw.rstrip(".,;|)"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)


def hermes_bin() -> str:
    # cron 환경 PATH에 hermes가 없을 수 있어 고정 경로를 먼저 본다
    for p in (Path.home() / ".local/bin/hermes", Path("/opt/homebrew/bin/hermes")):
        if p.exists():
            return str(p)
    return "hermes"


def main() -> int:
    dry = "--dry-run" in sys.argv
    try:
        state = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        state = {}
    alerted: dict = state.get("alerted", {})
    now = datetime.now(KST)
    lines: list[str] = []
    live_keys: set[str] = set()

    for bdir in sorted(p for p in BOARDS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        db = bdir / "kanban.db"
        if not db.exists():
            continue
        b = bdir.name
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)  # 읽기 전용
        try:
            rows = con.execute("SELECT id, title FROM tasks WHERE status='scheduled'").fetchall()
        except sqlite3.OperationalError:  # 초기화 안 된 빈 보드
            con.close()
            continue
        for tid, title in rows:
            row = con.execute(
                "SELECT payload FROM task_events WHERE task_id=? AND kind='scheduled' ORDER BY id DESC LIMIT 1",
                (tid,)).fetchone()
            reason = ""
            if row:
                try:
                    reason = json.loads(row[0]).get("reason") or ""
                except ValueError:
                    reason = row[0] or ""
            m = MARK.search(reason)
            if not m:
                continue  # 마커 없는 Park 카드: 사람이 깨운다
            key = f"{b}:{tid}"
            live_keys.add(key)
            until = parse_until(m.group(1))
            if until is None:
                if alerted.get(key) != "bad_format":
                    lines.append(f"⚠️ 형식 오류 `{b}` `{tid}` {title[:50]} — `SCHEDULED_UNTIL={m.group(1)}` 해석 불가")
                    alerted[key] = "bad_format"
                continue
            if now < until:
                continue
            wakes = con.execute(
                "SELECT count(*) FROM task_comments WHERE task_id=? AND body LIKE ?",
                (tid, f"%{WAKE_TAG}%")).fetchone()[0]  # CLI가 본문 앞에 "UNBLOCK: "을 붙인다
            if wakes >= MAX_WAKES:
                if alerted.get(key) != "cap":
                    lines.append(f"🛑 자동 깨우기 상한({MAX_WAKES}회) `{b}` `{tid}` {title[:50]} — hang 의심, 사람 판단 필요")
                    alerted[key] = "cap"
                continue
            late = int((now - until).total_seconds() // 60)
            note = f"{WAKE_TAG} SCHEDULED_UNTIL {until.strftime('%m/%d %H:%M')} 경과({late}분), {wakes + 1}/{MAX_WAKES}회째"
            if dry:
                lines.append(f"(dry-run) 깨울 대상 `{b}` `{tid}` {title[:50]} — {note}")
                continue
            r = subprocess.run([hermes_bin(), "kanban", "--board", b, "unblock", tid, "--reason", note],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                lines.append(f"⏰ 깨움 `{b}` `{tid}` {title[:50]} ({late}분 경과, {wakes + 1}/{MAX_WAKES})")
            else:
                lines.append(f"❌ 깨우기 실패 `{b}` `{tid}`: {(r.stderr or r.stdout).strip()[:150]}")
        con.close()

    alerted = {k: v for k, v in alerted.items() if k in live_keys}  # 끝난 카드는 정리
    if not dry:
        STATE_FILE.write_text(json.dumps({"alerted": alerted}))
    if not lines:
        return 0  # 조용히 종료
    text = "**kanban 자동 깨우기**\n" + "\n".join(f"• {l}" for l in lines)
    if dry:
        print("[dry-run]\n" + text)
        return 0
    ok = _notify.send(text, mention=False)
    print(("전송 완료\n" if ok else "전송 실패\n") + text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
