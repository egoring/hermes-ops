"""skill-label-guard: 답변의 `🧩 스킬:` 줄을 실제 skill_view 호출 기록과 맞춘다.

왜: 모델(특히 haiku)이 skill_view 를 호출하지 않고 `🧩 스킬: x` 만 적는 허위 표시가 있었다
(11-17 평가: helper-bot 🧩 답변의 40%). 🧩 는 사용자가 실제 스킬 사용을 확인하는 표시라 거짓이면 안 된다.

동작:
  - post_tool_call: 이 세션에서 성공한 skill_view 의 스킬 이름을 기억한다(프로세스 메모리).
  - transform_llm_output: 답변 앞부분의 `🧩 스킬:` 줄에서, 이 세션에서 실제로 로드된 적 없는 이름을 지운다.
    (이 세션 = 메모리 기록 ∪ 이 프로필 state.db 의 같은 세션 skill_view 기록. 같은 스레드에서 앞서 불러온 스킬은 인정)
    남는 이름이 없으면 줄을 통째로 지운다. 바꿀 게 없으면 None(원문 그대로).
  - 오류는 모두 삼키고 None → 원문 그대로 전달 (fail open, hold_stream 안 씀).
기록: <HERMES_HOME>/logs/skill_label_guard.log (고친 경우만)
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

PROFILE_HOME = Path(__file__).resolve().parents[2]  # <profile>/plugins/skill-label-guard/__init__.py
LOG = PROFILE_HOME / "logs" / "skill_label_guard.log"
LABEL = re.compile(r"^(\s*(?:\*\*)?🧩\s*스킬\s*(?:\*\*)?\s*[:：]\s*)(.+?)\s*$")
_loaded: dict[str, set[str]] = {}
AUTO_RE = re.compile(r'\[IMPORTANT: The "([^"]+)" skill is auto-loaded\.')


def _norm(name: str) -> str:
    n = name.strip().strip("`*_ ").lower()
    return n.rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def _log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _on_post_tool_call(tool_name: str = "", args=None, result=None, session_id: str = "", **_kw):
    try:
        if tool_name != "skill_view" or not session_id:
            return None
        a = args if isinstance(args, dict) else json.loads(args or "{}")
        ok = True
        try:
            r = json.loads(result) if isinstance(result, str) else result
            ok = bool(r.get("success", True)) if isinstance(r, dict) else True
        except (ValueError, TypeError):
            pass
        if ok and a.get("name"):
            _loaded.setdefault(session_id, set()).add(_norm(str(a["name"])))
    except Exception:  # noqa: BLE001 — 관찰 훅은 절대 대화를 막지 않는다
        pass
    return None


def _on_pre_llm_call(session_id: str = "", user_message=None, conversation_history=None, **_kw):
    """채널 자동 로드로 받은 스킬을 기억한다 (이번 턴 사용자 메시지 + 앞선 대화 기록)."""
    try:
        texts = [user_message] + [m.get("content") for m in (conversation_history or []) if isinstance(m, dict) and m.get("role") == "user"]
        for t in texts:
            if isinstance(t, str) and "skill is auto-loaded" in t:
                _loaded.setdefault(session_id, set()).update(_norm(n) for n in AUTO_RE.findall(t))
    except Exception:  # noqa: BLE001
        pass
    return None


def _db_loaded(session_id: str) -> set[str]:
    db = PROFILE_HOME / "state.db"
    if not session_id or not db.is_file():
        return set()
    out: set[str] = set()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
    try:
        # 채널 자동 로드(channel_skill_bindings)로 받은 스킬도 실제 로드다 — 첫 사용자 메시지 앞머리에 붙는다
        for (um,) in con.execute("select content from messages where session_id=? and role='user' and content like '[IMPORTANT: The %skill is auto-loaded%'", (session_id,)):
            out |= {_norm(n) for n in AUTO_RE.findall(um or "")}
        for (tc,) in con.execute("select tool_calls from messages where session_id=? and tool_calls like '%skill_view%'", (session_id,)):
            for x in json.loads(tc or "[]"):
                f = x.get("function") or {}
                if f.get("name") == "skill_view":
                    try:
                        n = json.loads(f.get("arguments") or "{}").get("name")
                    except ValueError:
                        n = None
                    if n:
                        out.add(_norm(str(n)))
    finally:
        con.close()
    return out


def fix_label(text: str, loaded: set[str]) -> str | None:
    """테스트 가능한 순수 함수: 고친 텍스트 또는 None(변경 없음)."""
    lines = text.split("\n")
    for i, line in enumerate(lines[:6]):  # 🧩 는 답변 맨 앞 (💡·빈 줄 몇 개 허용)
        m = LABEL.match(line)
        if not m:
            continue
        names = [n for n in re.split(r"\s*[,，、]\s*", m.group(2)) if n.strip()]
        keep = [n for n in names if _norm(n) in loaded]
        if len(keep) == len(names):
            return None
        if keep:
            lines[i] = m.group(1) + ", ".join(n.strip() for n in keep)
        else:
            del lines[i]
            if i < len(lines) and not lines[i].strip():  # 뒤따르는 빈 줄도 정리
                del lines[i]
        return "\n".join(lines)
    return None


def _on_transform(response_text=None, session_id: str = "", **_kw):
    try:
        if not isinstance(response_text, str) or "🧩" not in response_text[:600]:
            return None
        loaded = set(_loaded.get(session_id, set()))
        if not any(LABEL.match(l) and all(_norm(n) in loaded for n in re.split(r"\s*[,，、]\s*", LABEL.match(l).group(2)) if n.strip())
                   for l in response_text.split("\n")[:6]):
            loaded |= _db_loaded(session_id)
        fixed = fix_label(response_text, loaded)
        if fixed is not None:
            first = next((l for l in response_text.split("\n")[:6] if LABEL.match(l)), "")
            _log(f"session={session_id} fixed label {first.strip()[:120]!r} loaded={sorted(loaded)}")
        return fixed
    except Exception as e:  # noqa: BLE001
        _log(f"error {type(e).__name__}: {e}")
        return None


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("transform_llm_output", _on_transform)
