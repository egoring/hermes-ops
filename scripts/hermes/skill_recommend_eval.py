#!/usr/bin/env python3
"""skill_recommend.py 평가: (1) 기대값 회귀 테스트 (2) 최근 디스코드 실제 질문 재생.

사용: python3 ~/.hermes/hooks/skill_recommend_eval.py [--since "2026-11-11 18:20"] [--until ...] [-v]
훅을 고친 뒤 매번 돌린다. 회귀 FAIL이 0이고, 재생에서 엉뚱한 후보가 줄었는지 본다.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter

H = os.path.expanduser("~/.hermes")
HOOK = H + "/hooks/skill_recommend.py"

# (프로필, 첫 턴?, 질문, 반드시 포함 | None=추천 없어야 함)
CASES = [
    ("coder-bot", True, "처음 받은 매출 CSV 데이터 품질 점검 순서 알려줘", "explore-data"),
    ("coder-bot", True, "이 데이터셋 결측치랑 이상치 확인해줘", "explore-data"),
    ("coder-bot", True, "두 그룹 차이가 통계적으로 유의한지 봐줘", "statistical-analysis"),
    ("coder-bot", True, "동료가 올린 PR을 리뷰하려는데 확인할 항목 정리해줘", "code-review"),
    ("default", True, "langfuse로 트레이싱 붙이려면?", "langfuse"),
    ("default", True, "기술부채 정리 우선순위 잡아줘", "tech-debt"),
    ("default", True, "pdf에서 텍스트 뽑아줘", "pdf"),
    ("default", True, "엑셀 파일 읽어서 요약해줘", "microsoft-office"),
    ("default", True, "유튜브 영상 요약해줘", "youtube-content"),
    ("default", True, "논문 찾아서 정리해줘", "arxiv"),
    ("reviewer-bot", True, "칸반 카드 리뷰어한테 넘겨줘", "kanban"),
    ("reviewer-bot", True, "캐글 리더보드 순위 확인해줘", "competition"),
    ("coder-bot", False, "pdf에서 텍스트 뽑아줘", "pdf"),                # 중간 턴이라도 짧고 구체적이면
    ("coder-bot", False, "langfuse 트레이싱 붙여줘", None),             # coder-bot엔 langfuse 없음
    ("coder-bot", True, "안녕", None),
    ("default", True, "오늘 저녁 뭐 먹지", None),
    ("reviewer-bot", True, "추천대로 진행하고 일단 설계랑 준비까지만 해보자", None),
    ("reviewer-bot", False, "지금 거기서 답변하는 ai 모델이 뭐야", None),
    ("reviewer-bot", False, "내가 직접 테스트할수있게 환경도 세팅해줘", None),
    ("reviewer-bot", False, "일단 설계먼저 하고 정해줄건 나중에 한번에 하자", None),
    ("reviewer-bot", True, "[someuser] [kanban] Task t_1 completed. Title: 리뷰", None),
]


def run(profile, first, msg):
    out = subprocess.run(["/usr/bin/python3", HOOK], capture_output=True, text=True,
                         input=json.dumps({"profile": profile, "extra": {"user_message": msg, "platform": "discord", "is_first_turn": first}})).stdout
    return [x[2:].split(":")[0] for x in (json.loads(out)["context"].splitlines() if out else []) if x.startswith("- ")]


def main():
    args = sys.argv[1:]
    since = args[args.index("--since") + 1] if "--since" in args else "2026-11-11 18:20"
    until = args[args.index("--until") + 1] if "--until" in args else "9999"
    verbose = "-v" in args
    fails = 0
    for prof, first, q, want in CASES:
        got = run(prof, first, q)
        ok = (not got) if want is None else any(want in g for g in got)
        fails += not ok
        if verbose or not ok:
            print(f"{'PASS' if ok else 'FAIL'} {prof:12} {'첫' if first else '중'} {q[:34]:34} -> {got or '없음'} (기대 {want or '없음'})")
    print(f"회귀: {len(CASES) - fails}/{len(CASES)} 통과")

    # 디스코드 실제 질문 재생 (로그에 남은 턴을 state.db 원문으로 다시 돌림)
    lines = [l for l in open(H + "/logs/skill_recommend.log", errors="ignore")
             if since <= l[:16] <= until and re.search(r" platform=discord profile=\S+ \d+ms", l)]
    n = had = now = 0
    names = Counter()
    shown = []
    for l in lines:
        ts, prof = re.search(r"^(\S+ \S+) platform=\S* profile=(\S+)", l).groups()
        db = f"{H}/profiles/{prof}/state.db"
        if not os.path.isfile(db):
            continue
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = c.execute("select id, session_id, content from messages where role='user' and abs(timestamp-strftime('%s',?,'-9 hours'))<=3 "
                        "order by abs(timestamp-strftime('%s',?,'-9 hours')) limit 1", (ts, ts)).fetchone()
        if not row:
            continue
        mid, sid, content = row
        first = c.execute("select count(*) from messages where session_id=? and id<?", (sid, mid)).fetchone()[0] == 0
        got = run(prof, first, content)
        n += 1
        had += "cands=[(" in l
        now += bool(got)
        names.update(got)
        if got:
            shown.append(("첫" if first else "중", re.sub(r"^\s*\[[A-Za-z0-9_.\-]{2,32}\]\s*", "", content)[:48].replace("\n", " "), got))
    print(f"재생: 디스코드 턴 {n}개, 후보 붙음 {had}(당시) → {now}(지금)")
    print("  지금 후보 빈도:", names.most_common(8))
    for s in shown[: (40 if verbose else 12)]:
        print("  ", s)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
