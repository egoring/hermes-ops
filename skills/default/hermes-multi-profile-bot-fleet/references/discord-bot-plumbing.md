# Discord bot plumbing

## Mentions must be the angle-bracket form

Only `<@USER_ID>` renders as a real mention and fires a notification. `@username`, a bare id, or
a display name is plain text — the user sees words, gets nothing on their phone. Put the literal
token in the bot's SOUL.md and say why, or the bot writes the readable-looking form.

Find the numeric id: Discord Settings → Advanced → Developer Mode, then right-click the user →
Copy User ID. A user id is not a secret and may be written into prompts and scripts.

An id the user hands over may be a guild id rather than a user id — this has burned a whole
debugging session. Resolve it before wiring it in:

```bash
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/users/<ID>     # username => user
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/guilds/<ID>    # name => guild
```

The same confusion applies to channel vs guild ids in `discord.allowed_channels`; a wrong value
there drops every inbound message with an `Ignoring message in non-allowed channel` log line and
no user-visible error.

## allowed_mentions needs `parse` alongside `users`

Posting with `{"allowed_mentions": {"users": [id]}}` is rejected with HTTP 403. Send both keys:

```python
"allowed_mentions": {"parse": [], "users": [USER_ID]}
```

`parse: []` denies @everyone/@here/roles while the explicit users list still pings the one person.
A 403 here is a payload-shape error, not a permissions problem — confirm by posting a plain
`{"content": "..."}` message first; if that returns 200 the bot's channel permissions are fine.

## `.env` may hold the same key several times — last wins

Repeated setup flows append rather than replace, so a profile `.env` can carry several
`DISCORD_BOT_TOKEN=` lines. Hermes uses the LAST definition. A helper script that reads the
first match will authenticate as a different bot than the gateway does, and messages arrive
under the wrong account name. Read the last occurrence:

```python
token = None
for line in open(env_file):
    if line.startswith("DISCORD_BOT_TOKEN="):
        token = line.split("=", 1)[1].strip()   # keep overwriting: last wins
```

Cross-wired duplicates are common: each profile's FIRST token line can be a sibling bot's token
(setup run in the wrong profile, then re-run). Clean up only after auditing:
1. Per profile, hash every `DISCORD_BOT_TOKEN` line (`sha256(...)[:8]`, never print values) and
   compare the LAST hash across profiles — overlap means two profiles log in as one account.
2. Resolve each distinct hash to its account with `GET /api/v10/users/@me` (`Authorization: Bot
   <token>`) and check it matches the profile's role.
3. Back up `.env` → `.env.bak_<ts>_dedupe` (chmod 600 — it still holds every token), keep only
   the last line, and re-hash: last-line hash before == after means the gateway keeps its
   connection (no reconnect, no restart). Confirm `gateway_state.json` still shows each
   `<profile>:discord` connected and one helper-script send succeeds.
When a new token lands, also hash-compare it against any token that was pasted in chat — equal
means the user did not reset it.

## Confirm profile↔account mapping

Do not infer the account from a grep of `.env` (duplicates) or from `Connected as` log lines:
under a multiplexed gateway those lines are old and carry no profile name, so a per-profile grep
returns the same account for every bot. Authoritative: the `/users/@me` lookup on the last-line
token above, plus `✓ discord connected (profile: <bot>)` in `~/.hermes/logs/gateway.log` and
`gateway_state.json` for liveness.

## Tagging a second bot inside another bot's thread

When the user asks "if I tag bot B in bot A's thread, will it answer?" — yes (the thread's
parent channel is allowed), and B starts its OWN session for that thread. Check two per-profile
gates in the adapter defaults before saying it just works:
- `discord.allow_bots` defaults to `none`: B's history backfill (last ≤50 messages) DROPS every
  other bot's message, so B sees only the user's lines — none of A's analysis or numbers. Set
  `allow_bots: mentions` on B to include them as context (it still only responds to bots that
  mention it).
- `discord.thread_require_mention` defaults to `false`: once B has participated in a thread it
  answers every later untagged message there too, so A and B both reply. Set it `true` on a bot
  meant to be called on demand (e.g. a final-check bot) and leave the conversational bot as is.
Both are adapter settings: apply with `hermes -p <bot> gateway restart` (a config re-scan does not
rebuild a connected adapter); they then hold in existing threads as well.

## "The bot isn't answering" — triage order

Work from the gateway outward. Each step rules a layer in or out:
1. `gateway_state.json` → each `<profile>:discord` `state`/`error_code`. A `fatal`
   `discord_websocket_health_stale` adapter retries on its own about every 5 min. The log shows
   `Secondary discord reconnect retry in 300s (profile: <bot>)`, and success is
   `✓ discord reconnected (profile: <bot>)`. Check the token with `GET /users/@me` and the
   `session_start_limit.remaining` from `GET /gateway/bot` before blaming it.
2. `grep "inbound message: platform=discord user=<name>"` in `gateway.log`. No line after the
   user's last answered message means it never reached Hermes. The usual causes are another
   thread, a channel post without a mention, or a send during a disconnect window. Ask them to
   resend in the same thread and watch for the line.
3. Inbound present but the reply is ~200 chars with `api_calls=0`: look for `No Anthropic
   credentials found` / `refresh token ... terminally invalid` in the bot's `agent.log`. The
   shared OAuth login died, usually for every profile at once, so probe each bot with a one-shot
   `chat -Q`. The user must re-login (`hermes -p <bot> auth add anthropic` per profile, or
   re-login the runtime the profiles borrow). The fix takes effect on the next message with no
   gateway restart. Kanban tasks that crashed during the outage need re-running.
4. Replies are posted but the user saw nothing: quiet hours suppress @mentions, so there is no
   phone notification. Tell them to open the thread.

Recurring disconnects: count `Can't keep up … behind` and `[Discord] Disconnected` per day and per
profile before proposing a cause. Then put the warning timestamps next to the cron runs and kanban
events in the preceding minute. Report the correlation as a correlation. Prefer trimming
finished-target cron jobs over a full gateway restart, which reconnects every bot and needs
approval.

## "Bot is typing" is not proof of token spend

The typing indicator can linger as a client-side artifact after a turn ends. Decide from the
logs and process state: a `Turn ended` line with no later `API call #` entries, plus `ps -o %cpu=`
at 0.0, means nothing is running. Conversely, `API call #N ... in=<big>` lines ARE spend, and
their input size shows how much history is being resent each turn — a long-lived thread that
resends a huge prefix every call is the signal to start a fresh thread.
