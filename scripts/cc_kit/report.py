#!/opt/anaconda3/bin/python3
"""cc_kit 결과 표: results/<run_id>/trials.jsonl → results/<run_id>/report.md (+ 과제×조건 표, A→B 짝 비교).

  report.py --run-id pilot
"""
from __future__ import annotations

import argparse
import json
import statistics as S
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


def rows_of(run_id: str) -> list[dict]:
    p = RESULTS / run_id / "trials.jsonl"
    last: dict[str, dict] = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            d = json.loads(ln)
            last[d["trial_id"]] = d  # 같은 trial_id 는 마지막 시도
    return list(last.values())


def cell(r: dict) -> dict:
    h = r.get("hidden") or {}
    hk = r.get("hooks") or {}
    return {
        "trial": r["trial_id"], "status": r.get("status"), "hidden": f"{h.get('passed')}/{h.get('expected')}",
        "clean": "yes" if r.get("clean") else "no", "visible": "all pass" if r.get("visible_all_pass") else
        "FAIL " + ",".join(str(i + 1) for i, a in enumerate(r.get("acceptance") or []) if not a.get("pass")),
        "wall_s": r.get("wall_s"), "turns": r.get("num_turns"), "cost": None if r.get("total_cost_usd") is None else round(r["total_cost_usd"], 3),
        "hooks": (f"{hk.get('lines')}줄 (pre 허용 {hk.get('pre_allow')}·차단 {hk.get('pre_block')}, stop 차단 {hk.get('stop_block')}, "
                  f"stop 허용 {hk.get('stop_allow')})") if r.get("condition") == "B" else "-",
        "protected": ",".join(r.get("protected_changed") or []) or "없음",
        "hermes": ",".join(r.get("hermes_marks") or []) or "없음",
        "failed": [f.split("::")[-1] for f in h.get("failed") or []],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    rows = sorted(rows_of(a.run_id), key=lambda r: (r["task"], r["condition"], r["rep"]))
    L = [f"# cc_kit 결과 — {a.run_id}", "",
         "조건 A = 카드만(effort 하네스와 같은 프롬프트) · 조건 B = 카드 + 키트(reviewer-bot 설계 문서·CLAUDE.md·보호 훅·Stop 훅).",
         "공통: Claude Code headless, claude-sonnet-5-5, effort high, 구독 로그인, 샌드박스. clean = 보이는 합격 명령 전부 + 숨은 시험 rate 1.0(effort 하네스 정의).",
         "비용 = Claude Code 가 보고한 total_cost_usd(API 단가 추정치 — 실제 청구는 구독).", "",
         "| 시행 | 상태 | 숨은 통과 | clean | 보이는 합격 명령 | 벽시계 s | 턴 | 비용 $(추정) | 훅 기록 | 보호 파일 변경 | ~/.hermes 접근 | 숨은 실패 |",
         "|---|---|---|---|---|---:|---:|---:|---|---|---|---|"]
    for r in rows:
        c = cell(r)
        L.append(f"| {c['trial']} | {c['status']} | {c['hidden']} | {c['clean']} | {c['visible']} | {c['wall_s']} | {c['turns']} | "
                 f"{c['cost']} | {c['hooks']} | {c['protected']} | {c['hermes']} | {', '.join(c['failed']) or '-'} |")
    # 조건별 요약
    L += ["", "## 조건별", "", "| 조건 | 시행 | clean 비율 | 숨은 통과 평균 | 벽시계 중앙값 s | 비용 합 $(추정) |", "|---|---:|---:|---:|---:|---:|"]
    for cond in sorted({r["condition"] for r in rows}):
        rs = [r for r in rows if r["condition"] == cond]
        ok = [r for r in rs if r.get("hidden")]
        L.append(f"| {cond} | {len(rs)} | {sum(1 for r in rs if r.get('clean')) / len(rs):.3f} | "
                 f"{S.mean([(r['hidden'].get('rate') or 0) for r in ok]) if ok else float('nan'):.3f} | "
                 f"{S.median([r.get('wall_s') or 0 for r in rs]):.0f} | {sum(r.get('total_cost_usd') or 0 for r in rs):.2f} |")
    # 과제 단위 짝 비교
    tasks = sorted({r["task"] for r in rows})
    diffs = []
    for t in tasks:
        ca = [r for r in rows if r["task"] == t and r["condition"] == "A"]
        cb = [r for r in rows if r["task"] == t and r["condition"] == "B"]
        if ca and cb:
            diffs.append(S.mean([1.0 if r.get("clean") else 0.0 for r in cb]) - S.mean([1.0 if r.get("clean") else 0.0 for r in ca]))
    if diffs:
        L += ["", f"과제 단위 clean 차이(B − A) 평균 {S.mean(diffs):+.3f} (과제 {len(diffs)}개, B 우세 {sum(d > 0 for d in diffs)} / 열세 "
                  f"{sum(d < 0 for d in diffs)} / 동점 {sum(d == 0 for d in diffs)}). 과제 1~2개로는 효과를 주장하지 않는다."]
    (RESULTS / a.run_id / "report_table.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
