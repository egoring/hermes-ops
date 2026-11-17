#!/usr/bin/env python3
"""봇 스킬 자동 로드 평가 (모델 단위): 실제로 skill_view 를 부르는지 대화형 모드로 반복 측정.

방법 (agentskills.io 'Optimizing skill descriptions', Anthropic skill-creator 평가 방식):
  - 질문 20개 = 써야 함 10 (명시/바꿔 말하기 섞음) + 비슷하지만 쓰면 안 됨 10 (근접 오답)
  - 질문마다 N회 (기본 3) — 로드 판단은 확률적이라 한 번으로는 못 믿는다
  - 목표: 써야 함 질문의 로드율 >= 80%, 쓰면 안 됨 질문의 오로드율 <= 20%
  - 대화형 모드 (`hermes chat -q` 를 TTY로) — 1회성 -Q 모드는 스킬 안내 문구가 달라서 대표성이 없다
  - 도구는 skills 만 (평가 중 파일 쓰기·명령 실행 같은 부작용 방지)

사용: python3 skill_trigger_eval.py [--profiles reviewer-bot,coder-bot] [--runs 3] [--workers 6] [--only 0,3]
결과: ~/.hermes/logs/skill_trigger_eval/<시각>.jsonl + 요약 출력
"""
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

H = Path.home() / ".hermes"
OUT = H / "logs" / "skill_trigger_eval"
TIMEOUT = 100  # 로드 판단은 보통 첫 5초 안. 답변 완료까지 기다리지 않는다

# (질문, 허용 스킬 집합 | None = 아무 스킬도 로드하면 안 됨)
CASES = [
    ("결제 모듈 리팩터링했는데 어떤 테스트를 어디까지 짜야 할지 계획 세워줘", {"testing-strategy"}),
    ("주문 취소하면 재고가 복구되는 기능이야. 배포 전에 뭘 확인해야 안심할 수 있을지 케이스로 정리해줘", {"testing-strategy"}),
    ("처음 받은 고객 데이터 파일인데 컬럼이 뭐가 있고 빈 값이 얼마나 되는지부터 보고 싶어. 어떻게 볼까", {"explore-data", "data-analysis"}),
    ("지역별 월 매출 표가 있는데 어느 지역이 제일 많이 늘었는지 계산하는 방법 알려줘", {"analyze", "data-analysis", "explore-data"}),
    ("A안 쓴 사람 전환율 12%, B안 10%야. 이 차이가 우연인지 판단하고 싶어", {"statistical-analysis", "analyze"}),
    ("동료가 보낸 변경이야. 머지해도 되는지 봐줘:\n- if user.is_admin:\n+ if user.is_admin or user.id == 1:", {"code-review", "github-code-review"}),
    ("알림 서비스 큐를 Redis로 할지 SQS로 할지 정해야 해. 장단점 비교하고 골라줘", {"architecture", "system-design"}),
    ("사내 회의실 예약 시스템 API를 처음부터 잡으려고 해. 엔드포인트랑 데이터 구조 설계해줘", {"system-design", "architecture"}),
    ("오래된 코드베이스에서 뭐부터 고쳐야 할지 우선순위 매기는 기준 알려줘", {"tech-debt"}),
    ("새로 만든 CLI 도구 README 써줘. 설치, 사용법, 옵션 설명 들어가게", {"documentation"}),
    ("테스트라는 단어 영어 철자가 어떻게 돼?", None),
    ("CSV랑 TSV 차이 한 줄로만", None),
    ("평균이랑 중앙값 차이 한 문장으로", None),
    ("리뷰해줘서 고마워, 오늘은 여기까지 하자", None),
    ("아키텍처라는 말 어원이 뭐야", None),
    ("API 키 같은 걸 디스코드 채팅에 올리면 안 되지? 예/아니오로", None),
    ("문서 작업하느라 오늘 좀 피곤하다", None),
    ("깃허브 로고가 무슨 동물이었지", None),
    ("기술부채라는 말 처음 쓴 사람이 누구야", None),
    ("데이터랑 정보 차이를 비유 하나로 설명해줘", None),
]
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def run_one(profile: str, qi: int, k: int) -> dict:
    q, want = CASES[qi]
    t0 = time.time()
    p = subprocess.run(["script", "-q", "/dev/null", "timeout", str(TIMEOUT), "hermes", "-p", profile, "chat", "-t", "skills", "-q", q],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT + 30)
    out = ANSI.sub("", p.stdout)
    loaded = sorted(set(re.findall(r"📚 Skill ([\w./-]+)", out)))
    loaded = [s.rsplit("/", 1)[-1] for s in loaded]
    if want is None:
        ok = not loaded
    else:
        ok = bool(set(loaded) & want)
    return {"profile": profile, "qi": qi, "run": k, "kind": "pos" if want else "neg", "q": q,
            "loaded": loaded, "ok": ok, "sec": round(time.time() - t0, 1), "chars": len(out)}


def main() -> int:
    a = sys.argv[1:]
    profiles = (a[a.index("--profiles") + 1] if "--profiles" in a else "reviewer-bot,coder-bot").split(",")
    runs = int(a[a.index("--runs") + 1]) if "--runs" in a else 3
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 6
    only = [int(x) for x in a[a.index("--only") + 1].split(",")] if "--only" in a else range(len(CASES))
    jobs = [(p, qi, k) for p in profiles for qi in only for k in range(runs)]
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / time.strftime("%Y%m%d_%H%M.jsonl")
    res = []
    with ThreadPoolExecutor(workers) as ex, f.open("w") as fh:
        for r in ex.map(lambda j: run_one(*j), jobs):
            res.append(r)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
    print(f"결과 파일: {f}  ({len(res)}회)")
    for p in profiles:
        pos = [r for r in res if r["profile"] == p and r["kind"] == "pos"]
        neg = [r for r in res if r["profile"] == p and r["kind"] == "neg"]
        pr = sum(r["ok"] for r in pos) / max(len(pos), 1)
        nr = sum(not r["ok"] for r in neg) / max(len(neg), 1)
        print(f"\n== {p}: 써야 함 로드율 {pr:.0%} (목표 80% 이상) · 쓰면 안 됨 오로드율 {nr:.0%} (목표 20% 이하)")
        for qi in only:
            rs = [r for r in res if r["profile"] == p and r["qi"] == qi]
            if not rs:
                continue
            hit = sum(r["ok"] for r in rs)
            names = sorted({s for r in rs for s in r["loaded"]})
            short = [r for r in rs if r["chars"] < 3000]
            flag = " (출력 짧음: 실행 실패 의심)" if short else ""
            print(f"  {'써야' if rs[0]['kind'] == 'pos' else '안됨'} {hit}/{len(rs)}  {CASES[qi][0][:40].replace(chr(10), ' '):40}  로드: {names or '-'}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
