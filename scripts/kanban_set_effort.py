#!/usr/bin/env python3
"""kanban 태스크 하나의 추론 강도(reasoning effort)를 지정/해제한다.

`hermes kanban` CLI에는 이 옵션이 없어서(v0.21.4), Hermes 내부 함수
`hermes_cli.kanban_db.set_reasoning_effort`를 그대로 부른다. 대시보드 API와 같은 경로다.

- 값은 태스크에 붙어서 그 태스크의 **다음 실행부터 모든 실행**에 적용된다
  (워커 실행 시 `--reasoning <값>`). 그래서 최종 점검은 별도 태스크로 만들고 거기에만 건다.
- running 중에 바꿔도 되지만 지금 도는 실행에는 적용되지 않는다(다음 실행부터).

사용:
  kanban_set_effort.py <task_id> xhigh [--board <slug>]   # 지정
  kanban_set_effort.py <task_id> --clear [--board <slug>]  # 해제 (프로필 기본값으로)
  kanban_set_effort.py <task_id> --show [--board <slug>]   # 현재 값
값: none, minimal, low, medium, high, xhigh, max, ultra
"""
import argparse
import os
import sys
from pathlib import Path

# Hermes 소스와 그 venv로 실행한다. 다른 파이썬으로 실행되면 Hermes venv로 다시 실행한다.
_AGENT = Path(os.environ.get("HERMES_AGENT_DIR", Path.home() / ".hermes/hermes-agent"))
_VENV_PY = _AGENT / "venv/bin/python3"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve() and not os.environ.get("_KSE_REEXEC"):
    os.environ["_KSE_REEXEC"] = "1"
    os.execv(str(_VENV_PY), [str(_VENV_PY), __file__, *sys.argv[1:]])
sys.path.insert(0, str(_AGENT))
from hermes_cli import kanban_db  # noqa: E402
from hermes_cli.kanban_db_connect import connect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("effort", nargs="?")
    ap.add_argument("--board", default=None, help="보드 slug (생략 시 현재 보드)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--clear", action="store_true")
    g.add_argument("--show", action="store_true")
    a = ap.parse_args()

    conn = connect(board=a.board)
    row = conn.execute("SELECT status, assignee, reasoning_effort, title FROM tasks WHERE id = ?", (a.task_id,)).fetchone()
    if row is None:
        print(f"태스크 없음: {a.task_id} (보드 {a.board or '현재'})")
        return 1
    status, assignee, cur, title = row
    if a.show or (not a.clear and not a.effort):
        print(f"{a.task_id} [{status}, {assignee}] effort={cur or '(프로필 기본값)'} — {title}")
        return 0
    new = None if a.clear else a.effort
    kanban_db.set_reasoning_effort(conn, a.task_id, new)  # 잘못된 값이면 ValueError
    after = conn.execute("SELECT reasoning_effort FROM tasks WHERE id = ?", (a.task_id,)).fetchone()[0]
    print(f"{a.task_id} [{status}, {assignee}] effort: {cur or '(기본)'} → {after or '(기본)'}")
    if status == "running":
        print("  주의: 지금 도는 실행엔 적용 안 됨. 다음 실행부터.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
