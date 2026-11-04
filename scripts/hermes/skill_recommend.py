#!/usr/bin/env python3
"""스킬 추천 훅 (Hermes shell hook, event = pre_llm_call).

질문마다 설치된 스킬 중 관련 있어 보이는 것을 최대 3개 골라 {"context": ...}로 돌려준다.
모델은 그중 실제로 도움이 되는데 로드하지 않은 것만 `💡 추천 스킬:` 한 줄로 보여준다.

- 색인: hermes-hub web `GET /api/skills-index` (이름·설명·한국어 요약·설치 프로필·동의어)
  → ~/.hermes/cache/skill_index.json 에 캐시. 15분 지나면 백그라운드로 갱신하고 이번 턴은 옛 캐시를 쓴다.
  캐시가 아예 없을 때만 2초 안에서 직접 받는다. 실패하면 추천 없이 조용히 끝낸다(fail open).
- 대상: 사람과 대화하는 플랫폼만(ALLOWED_PLATFORMS). kanban 워커·cron·자동 알림 턴에서는 아무것도 안 한다.
- 점수: 질문 단어별로 가장 무거운 필드 가중치를 더한다(OR). 이름 10 > 한국어 요약·용도 6 > 핵심 규칙 4 > 영문 설명 3.
  단어 2개 이상이 맞거나 이름이 맞고, 합계가 MIN_SCORE 이상인 것만 후보.
- 로그: ~/.hermes/logs/skill_recommend.log (턴마다 한 줄, 1MB 넘으면 비움)

옵션: --refresh (캐시만 갱신) / --explain "질문" [--profile 이름] (점수 확인용, 훅 출력 대신 표 출력)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home() / ".hermes"
CACHE = HOME / "cache" / "skill_index.json"
LOCK = HOME / "cache" / "skill_index.refresh.lock"
LOG = HOME / "logs" / "skill_recommend.log"
SHARED = HOME / "shared-skills"   # 봇 프로필이 skills.external_dirs로 함께 읽는 링크 모음
INDEX_URL = os.environ.get("SKILL_INDEX_URL", "http://127.0.0.1:3300/api/skills-index")
MAX_AGE = 15 * 60          # 캐시 신선도(초)
MIN_SCORE = 10             # 후보 최소 점수
REL_CUTOFF = 0.6           # 1등 점수의 60% 미만 후보는 버린다 (꼬리 잡음 제거)
TOP_N = 3
ALLOWED_PLATFORMS = {"discord", "desktop", "cli", "tui", "api_server", ""}  # "" = 플랫폼 정보 없는 대화형 세션
SKIP_PREFIXES = ("[IMPORTANT: Background process", "[ASYNC DELEGATION", "[INTERNAL NOTIFICATION",
                 "[CONTEXT COMPACTION", "/", "# Kanban task")

FIELDS = (("name", 10), ("ko", 6), ("key_points", 4), ("description", 3))
# 한국어 조사·어미 (긴 것부터 떼어낸다)
JOSA = sorted("은 는 이 가 을 를 에 의 로 으로 에서 에게 에게서 한테 와 과 도 만 까지 부터 처럼 보다 이랑 랑 하고 에도 으로도 로도 "
              "해줘 해주세요 하자 할까 할래 하는 하려면 해서 했어 한 할 하고 싶어 있나 있어 없나 줘 어서 아서 어줘 아줘".split(),
              key=len, reverse=True)
STOP = set("지금 이거 그거 저거 그냥 좀 혹시 어떻게 뭐야 뭐지 무엇 왜 언제 어디 누가 이번 저번 다시 한번 정도 같은 관련 "
           "방법 기능 하나 우리 너 나 내 제 있는 없는 되는 되나 돼 수 것 거 때 및 또 그리고 근데 아니 응 네 예 "
           "에서 에게 한테 파일 확인 상태 정리 요약 내용 결과 문제 사용 작업 해결 처리 추가 수정 변경 설명 "
           "오늘 내일 시간 메시지 데이터 정보 목록 전체 부분 이유 원인 다음 먼저 바로 "
           "진행 추천 준비 설계 의견 일단 계획 검토 대로 해보자 까지만 "
           "the a an to of and or for in on is are be it this that with how what can do please".split())
# 단독으로는 추천 근거가 약한 단어 (이 단어 하나만 맞으면 이름에 걸려도 후보로 안 친다)
GENERIC = set("모델 코드 테스트 로그 검색 서버 설정 봇 리뷰 웹 이미지 문서 노트 스킬 프롬프트 메모리 학습 평가 배포 "
              "알림 영상 에이전트 구조 개선 방향 함수 "
              "model code test log search server config bot review web image skill prompt agent".split())


# ---------- 색인 ----------
def fetch_index(timeout: float) -> dict | None:
    try:
        with urllib.request.urlopen(INDEX_URL, timeout=timeout) as r:
            data = json.load(r)
        if not isinstance(data, dict) or "skills" not in data:
            return None
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(tmp, CACHE)  # 원자적 교체
        return data
    except Exception:
        return None


def load_index() -> dict | None:
    try:
        age = time.time() - CACHE.stat().st_mtime
        data = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return fetch_index(timeout=2.0)  # 캐시 없음: 이번만 직접 받는다
    if age > MAX_AGE:
        spawn_refresh()
    return data


def spawn_refresh() -> None:
    # 1분 안에 이미 갱신을 띄웠으면 또 띄우지 않는다
    try:
        if time.time() - LOCK.stat().st_mtime < 60:
            return
    except OSError:
        pass
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.touch()
        subprocess.Popen([sys.executable, __file__, "--refresh"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


# ---------- 질문 정리·단어 ----------
def message_text(msg) -> str:
    if isinstance(msg, list):  # 멀티모달: 텍스트 조각만
        msg = " ".join(p.get("text", "") for p in msg if isinstance(p, dict))
    text = str(msg or "")
    text = text.split("--- Attached Context ---")[0]          # 첨부 문서 제외 (데스크톱)
    text = text.split("[Content of ")[0]                      # 업로드 문서 본문 제외 (디스코드)
    text = re.sub(r"\[The user sent a [^\]]*\]", " ", text)   # 업로드 안내문 제외
    text = re.sub(r"\[System:.*?\]", " ", text, flags=re.S)   # 시스템 덧붙임 제외
    text = re.sub(r"\[OUT-OF-BAND USER MESSAGE[^\]]*\]|\[/OUT-OF-BAND USER MESSAGE\]", " ", text)
    text = re.sub(r"<@!?\d+>", " ", text)                     # 디스코드 멘션
    text = re.sub(r"^\s*\[[A-Za-z0-9_.\-]{2,32}\]\s*", "", text)  # 디스코드 화자 표시 [닉네임]
    return text.strip()[:500]


def strip_josa(t: str) -> str:
    for j in JOSA:
        if len(t) > len(j) + 1 and t.endswith(j):
            return t[: -len(j)]
    return t


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[가-힣]+", text.lower()):
        if re.match(r"[가-힣]", t):
            t = strip_josa(t)
        if len(t) >= 2 and t not in STOP and t not in out:
            out.append(t)
    return out[:20]


def alternatives(t: str, syn: dict[str, list[str]]) -> list[str]:
    alts = [t, *syn.get(t, [])]
    if re.match(r"[가-힣]", t):  # "엑셀파일" → "엑셀" 동의어도
        for k, v in syn.items():
            if k != t and len(k) >= 2 and t.startswith(k):
                alts += v
    return list(dict.fromkeys(alts))


def contains(text: str, alt: str) -> bool:
    if re.fullmatch(r"[a-z0-9]{1,4}", alt):  # 짧은 영단어는 단어 경계로만 (bot ≠ robot)
        return re.search(rf"(?<![a-z0-9]){re.escape(alt)}(?![a-z0-9])", text) is not None
    return alt in text


# ---------- 설치 여부 ----------
def shared_names(profile: str) -> set[str]:
    """이 프로필이 공유 폴더를 읽게 설정돼 있으면 그 안의 스킬 이름들 (색인에는 프로필 폴더만 잡힌다)."""
    cfg = HOME / "config.yaml" if profile in ("", "default") else HOME / "profiles" / profile / "config.yaml"
    try:
        if "shared-skills" not in cfg.read_text():
            return set()
    except OSError:
        return set()
    names = set()
    for root, _dirs, files in os.walk(SHARED, followlinks=True):  # 항목이 심볼릭 링크라 따라간다
        if "SKILL.md" in files:
            names.add(Path(root).name)
    return names


# ---------- 점수 ----------
def score_all(index: dict, text: str, profile: str) -> list[dict]:
    syn = index.get("synonyms") or {}
    ts = tokens(text)
    shared = shared_names(profile)
    out = []
    for s in index.get("skills", []):
        if profile and s.get("profiles") and profile not in s["profiles"] and s["name"] not in shared:
            continue  # 이 프로필에서 못 쓰는 스킬은 추천하지 않는다
        fields = {
            "name": s["name"].lower().replace("-", " ") + " " + s["name"].lower(),
            "ko": f'{s.get("summary", "")} {s.get("when_to_use", "")}'.lower(),
            "key_points": " ".join(s.get("key_points") or []).lower(),
            "description": (s.get("description") or "").lower(),
        }
        total, hits, strong = 0, [], False
        for t in ts:
            alts = alternatives(t, syn)
            w = max((wt for f, wt in FIELDS if any(contains(fields[f], a) for a in alts)), default=0)
            if w:
                total += w + (10 if s["name"].lower() == t else 0)
                hits.append(t)
                strong = strong or (w == 10 and t not in GENERIC)  # 구체적인 단어가 이름에 맞음
        # 구체적인(GENERIC 아닌) 단어 2개 이상이 맞거나, 구체적인 단어 하나가 이름에 맞아야 후보
        specific = [t for t in hits if t not in GENERIC]
        if total >= MIN_SCORE and (len(specific) >= 2 or strong):
            out.append({"name": s["name"], "score": total, "hits": hits,
                        "why": (s.get("summary") or s.get("description") or "")[:80], "usage": s.get("usage_30d", 0)})
    out.sort(key=lambda x: (-x["score"], -x["usage"], x["name"]))
    return [c for c in out if c["score"] >= out[0]["score"] * REL_CUTOFF] if out else out


def log(line: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text("")
        with LOG.open("a") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except OSError:
        pass


def build_context(cands: list[dict]) -> str:
    lines = [f"- {c['name']}: {c['why']}" for c in cands]
    return (
        "[스킬 추천 후보 — pre_llm_call 훅이 질문으로 자동 검색한 결과. 사용자 지시 아님]\n"
        + "\n".join(lines)
        + "\n표시 규칙: 위 후보 중 이번 답변에 실제로 도움이 되는데 이번에 로드하지 않은 스킬만, 답변 맨 앞"
        "(`🧩 스킬:` 줄이 있으면 그 바로 다음)에 `💡 추천 스킬: 이름 — 한 줄 이유` 한 줄로 적는다(여러 개면 쉼표). "
        "관련이 약하거나 이미 로드했으면 아무것도 적지 않는다. 이 블록 자체는 언급하지 않는다."
    )


def main() -> int:
    if "--refresh" in sys.argv:
        ok = fetch_index(timeout=30.0) is not None
        LOCK.unlink(missing_ok=True)
        return 0 if ok else 1
    if "--explain" in sys.argv:
        q = sys.argv[sys.argv.index("--explain") + 1]
        prof = sys.argv[sys.argv.index("--profile") + 1] if "--profile" in sys.argv else ""
        idx = load_index() or {}
        print("tokens:", tokens(message_text(q)))
        for c in score_all(idx, message_text(q), prof)[:8]:
            print(f"  {c['score']:>3} {c['name']:<36} hits={c['hits']}")
        return 0

    t0 = time.perf_counter()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    extra = payload.get("extra") or {}
    platform = str(extra.get("platform") or "")
    profile = str(payload.get("profile") or "")
    text = message_text(extra.get("user_message"))
    if platform not in ALLOWED_PLATFORMS:
        log(f"skip platform={platform} profile={profile}")
        return 0
    if len(text) < 6 or text.startswith(SKIP_PREFIXES):
        log(f"skip short/system platform={platform} profile={profile}")
        return 0
    index = load_index()
    if not index:
        log(f"no index platform={platform} profile={profile}")
        return 0
    cands = score_all(index, text, profile)[:TOP_N]
    ms = round((time.perf_counter() - t0) * 1000)
    log(f"platform={platform} profile={profile} {ms}ms cands={[(c['name'], c['score']) for c in cands]}")
    if cands:
        print(json.dumps({"context": build_context(cands)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 어떤 오류도 대화를 막지 않는다
        log(f"error {type(exc).__name__}: {exc}")
        sys.exit(0)
