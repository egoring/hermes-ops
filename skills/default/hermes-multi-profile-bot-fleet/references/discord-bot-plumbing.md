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

## Domain channels and channel-bound skills ("스킬을 나누고 싶다")

When the user wants coding/competition/design split, keep the bots split by ROLE and split the
domain by workspace/channel instead: domain bots lose the opus-design → sonnet-build → opus-review
cross-check (or need domains × roles bots) and pin one model to all of a domain's work. Measure
first — if the trigger eval shows ~0% false loads, mixing is not hurting answers and the gain is
organization only; say so.

What Hermes can scope (check the code of the installed version before promising more):

| Mechanism | Config | Effect | Limit |
|---|---|---|---|
| Project skills | `<git root>/.hermes/skills/` + `skills.trusted_project_dirs` | listed only when the session cwd's git root is trusted; override same-named profile skills | bots with `terminal.cwd` = that root see them in every Discord turn; nested repos are their own root |
| Channel auto-load | `discord.channel_skill_bindings: [{id: '<channel>', skills: [a, b]}]` | skill bodies prepended to the FIRST message of every new session in that channel (threads inherit via parent id) | pushes, never hides; costs the full SKILL.md tokens on every new session there |
| Platform hide | `skills.platform_disabled.<platform>` | hide per platform | no per-channel visibility |
| Per channel | `channel_overrides` (model, provider, system_prompt), `channel_prompts` | | no cwd, no skill list |

There is no per-channel skill visibility. Channel auto-load alone is the usual answer: bind 1–2
small, broadly useful skills (a few k chars, e.g. code-review + testing-strategy for a coding
channel), leave big project skills to on-demand loading.

Setup for a new domain channel:
1. User creates the channel and gives the id (right-click → Copy Channel ID).
2. Back up every bot `config.yaml`. In EACH bot add the id to `discord.allowed_channels`
   (comma-separated string) — otherwise the bot silently ignores the channel — and add the
   `channel_skill_bindings` entry. Re-parse with `yaml.safe_load` to confirm.
3. Confirm every bound skill resolves in every bot (`HERMES_HOME=<profile>` + venv
   `tools.skills_tool.skill_view(<name>)` → `success`); a missing one only logs
   `Auto-skill '<x>' not found`.
4. Make hooks/plugins tolerate the auto-load prefix (see `shell-hooks.md` → Channel auto-load).
5. Gates are adapter settings: a config re-scan does not rebuild connected adapters, so if the bot
   ignores the new channel, `hermes -p <bot> gateway restart` per bot (approval) and look for
   `Auto-loaded skill(s) [...]` in `gateway.log` on the first test message.
   If the bot answers in the channel but neither `Auto-loaded skill(s)` nor `Auto-skill '<x>' not
   found` appears, the loader never ran: either the event lost `auto_skill` or the gateway did not
   treat the session as new (`created_at == updated_at` check in `run_turn_prepare`). Don't guess
   from code — drop a temporary probe plugin into each bot (`pre_gateway_dispatch` logging
   `event.auto_skill` + `source.chat_id/parent_chat_id`, `pre_llm_call` logging whether
   `user_message` holds the `auto-loaded` marker; enable live, no restart), have the user send one
   message, read the probe log, then disable and delete the probe.
   Known cause on v0.23.0 (still on upstream main): `session_authority._reserve_route` calls
   `get_or_create_session` at admission, then turn prep calls it again and touches `updated_at`, so
   `_is_new_session` is never true and bindings never load. Workaround plugin (no core patch,
   live-enable, no restart): `pre_gateway_dispatch` → when `event.auto_skill` is set and
   `source.auto_thread_created` is true, call `gateway._hmwa_auto_load_skills(event, skills, "",
   key)` (same payload format as native), then set `event.auto_skill = None` so a future upstream
   fix cannot double-inject. It covers fresh-mention threads only (`/new` inside a thread gets
   nothing). Source kept in `~/.hermes/plugins-src/channel-skill-autoload/`.
6. "Bot didn't see my question" with no `inbound message` line: read the channel through the
   bot's token (`GET /channels/<id>/messages`, token never printed) and check each message's
   `mentions`. Discord's autocomplete offers each bot's managed ROLE under the same name; a role
   mention (`<@&role_id>`, empty `mentions`) never passes `require_mention` (the adapter has no
   role/mention_patterns support), and picking a sibling bot sends everything to it. Give the user
   paste-ready raw user mentions `<@bot_user_id>` per bot in test tables instead of names.
7. User tests: in the new channel one should-load question per bound skill, one question needing
   an extra unbound skill (auto-load must not block other loads), and the same question in the old
   channel (no auto-load there).

## "The bot isn't answering" — triage order

Work from the gateway outward. Each step rules a layer in or out:
1. `gateway_state.json` → each `<profile>:discord` `state`/`error_code`. Classify by code first:
   `discord_connect_error` with `Cannot connect to host discord.com:443 [No route to host]` is the
   **host network** (usually several bots at once; confirm with `curl https://discord.com/api/v10/gateway`
   and `ping 1.1.1.1`, check `netstat -rn -f inet6` for a default route via `utun*`) — nothing to
   fix in Hermes, adapters reconnect within ~5 min of recovery. `discord_websocket_health_stale`
   (`socket_closed`, `latency_exceeded`) is **gateway lag** (see Recurring disconnects). A `fatal`
   adapter retries on its own about every 5 min. The log shows
   `Secondary discord reconnect retry in 300s (profile: <bot>)`, and success is
   `✓ discord reconnected (profile: <bot>)`. Check the token with `GET /users/@me` and the
   `session_start_limit.remaining` from `GET /gateway/bot` before blaming it; with both fine,
   waiting for the next retry is the fix.
2. `grep "inbound message: platform=discord user=<name>"` in `gateway.log`. No line after the
   user's last answered message means it never reached Hermes. The usual causes are another
   thread, a channel post without a mention, or a send during a disconnect window. Ask them to
   resend in the same thread and watch for the line.
3. Inbound present but the reply is ~200 chars with `api_calls=0`: look for `No Anthropic
   credentials found` / `refresh token ... terminally invalid` in the bot's `agent.log`. The
   shared OAuth login died, usually for every profile at once, so probe each bot with a one-shot
   `chat -Q`. `hermes -p <bot> auth list` shows the source: `claude_code` means the bots borrow
   Claude Code's login — confirm with `claude -p "ok"` (`OAuth session expired`), then the user
   runs `claude` → `/login` once in their own terminal (browser flow; you cannot do it) and that
   fixes every profile. Otherwise `hermes -p <bot> auth add anthropic` per profile. Verify per bot
   with a one-shot and a fresh `API call #1: model=` line in its `agent.log` — no gateway restart.
   After re-login the token may live only in the macOS keychain (`~/.claude/.credentials.json`
   absent); that is fine if the one-shots succeed. Offer the long-lived `claude setup-token` in
   the bots' `.env` as the alternative when expiries recur (bots and Claude Code share one
   refresh token). Kanban tasks that crashed during the outage need re-running.
4. Replies are posted but the user saw nothing: quiet hours suppress @mentions, so there is no
   phone notification. Tell them to open the thread.

Recurring disconnects: count `Can't keep up … behind` and `[Discord] Disconnected` per day and per
profile before proposing a cause. Then put the warning timestamps next to the cron runs and kanban
events in the preceding minute. Report the correlation as a correlation. Prefer trimming
finished-target cron jobs over a full gateway restart, which reconnects every bot and needs
approval. Remedies in order of cost: (1) disable finished-target cron jobs and lengthen poll
intervals; (2) move monitor scripts out of the gateway to launchd + a notify script; (3)
`gateway.standalone: true` for the heaviest bot — it shields the SIBLINGS from that bot's load but
not the bot itself, adds a process (~600 MB), and kanban notify delivery across processes must be
verified first. Splitting one bot into two profiles does nothing under multiplex (same process,
one more connection).

## "Bot is typing" is not proof of token spend

The typing indicator can linger as a client-side artifact after a turn ends. Decide from the
logs and process state: a `Turn ended` line with no later `API call #` entries, plus `ps -o %cpu=`
at 0.0, means nothing is running. Conversely, `API call #N ... in=<big>` lines ARE spend, and
their input size shows how much history is being resent each turn — a long-lived thread that
resends a huge prefix every call is the signal to start a fresh thread.
