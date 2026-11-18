"""channel-skill-autoload: Discord channel_skill_bindings 자동 로드 우회 (Hermes v0.23.0 버그).

버그: session_authority._reserve_route 가 get_or_create_session 으로 세션을 먼저 만들고, 턴 준비
(run_turn_prepare) 가 다시 get_or_create_session 을 불러 updated_at 을 갱신 → `_is_new_session`
(created_at == updated_at) 이 항상 False → `_hmwa_auto_load_skills` 가 실행되지 않는다.

우회: pre_gateway_dispatch 에서, 바인딩이 있고(event.auto_skill) 이번 멘션으로 새 스레드가 만들어진
경우(source.auto_thread_created)에만 게이트웨이 자신의 `_hmwa_auto_load_skills` 를 호출해 같은 형식의
본문을 event.text 앞에 붙인다. 그 뒤 event.auto_skill 을 비워, upstream 이 고쳐져도 두 번 붙지 않게 한다.
오류는 삼키고 원래 흐름 그대로 (fail open). 기록: <프로필>/logs/channel_skill_autoload.log
upstream 수정 후 제거한다.
"""
import time
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "logs" / "channel_skill_autoload.log"


def _w(msg: str) -> None:
    try:
        with LOG.open("a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _on_dispatch(event=None, gateway=None, **_kw):
    try:
        skills = getattr(event, "auto_skill", None)
        src = getattr(event, "source", None)
        if not skills or src is None or gateway is None:
            return None
        if not getattr(src, "auto_thread_created", False):
            return None  # 기존 스레드 안의 후속 메시지: 이미 첫 턴에 들어갔다
        if "skill is auto-loaded" in (event.text or ""):
            return None
        fn = getattr(gateway, "_hmwa_auto_load_skills", None)
        if fn is None:
            _w("gateway has no _hmwa_auto_load_skills (Hermes changed) — skipped")
            return None
        before = len(event.text or "")
        fn(event, skills, "", f"channel-autoload:{getattr(src, 'chat_id', '')}")
        loaded = "skill is auto-loaded" in (event.text or "")
        if loaded:
            event.auto_skill = None  # 네이티브 경로가 고쳐져도 중복 주입 방지
        _w(f"chat={getattr(src, 'chat_id', '')} parent={getattr(src, 'parent_chat_id', '')} skills={skills} "
           f"loaded={loaded} chars {before}->{len(event.text or '')}")
    except Exception as e:  # noqa: BLE001
        _w(f"error {type(e).__name__}: {e}")
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", _on_dispatch)
