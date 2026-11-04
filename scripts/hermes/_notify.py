"""cron 스크립트 공용: Discord 채널로 메시지 보내기 (helper-bot 계정).

resource_alert.py 와 같은 방식. 토큰 값은 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

USER_ID = "<ID>"
CHANNEL_ID = "<ID>"
ENV_FILE = os.path.expanduser("~/.hermes/profiles/helper-bot/.env")
LIMIT = 1900  # Discord 2000자 제한 여유


def _token() -> str | None:
    token = None  # 여러 줄이면 마지막 정의 (Hermes와 같은 규칙)
    try:
        with open(ENV_FILE) as fh:
            for line in fh:
                if line.startswith("DISCORD_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return token


def send(text: str, mention: bool = False) -> bool:
    """text 를 채널에 보낸다. 길면 줄 단위로 잘라 여러 번 보낸다."""
    token = _token()
    if not token:
        print("토큰 없음 — 전송 생략", file=sys.stderr)
        return False
    if mention:
        text = f"<@{USER_ID}> " + text
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > LIMIT:
            chunks.append(cur)
            cur = ""
        cur += line[:LIMIT]
    if cur:
        chunks.append(cur)
    ok = True
    for c in chunks:
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
            data=json.dumps({"content": c, "allowed_mentions": {"parse": [], "users": [USER_ID]}}).encode(),
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                     "User-Agent": "DiscordBot (hermes-ops-cron, 1.0)"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                ok = ok and resp.status in (200, 201)
        except Exception as exc:
            print(f"전송 실패: {exc}", file=sys.stderr)
            ok = False
    return ok
