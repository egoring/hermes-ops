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

## Confirm profile↔account mapping from the gateway log

Do not infer which bot account a profile runs as by grepping its `.env` — duplicate keys make
that unreliable. The authoritative record is the connection line:

```bash
grep -o "Connected as [^ ]*" ~/.hermes/profiles/<bot>/logs/gateway.log | tail -1
```

## "Bot is typing" is not proof of token spend

The typing indicator can linger as a client-side artifact after a turn ends. Decide from the
logs and process state: a `Turn ended` line with no later `API call #` entries, plus `ps -o %cpu=`
at 0.0, means nothing is running. Conversely, `API call #N ... in=<big>` lines ARE spend, and
their input size shows how much history is being resent each turn — a long-lived thread that
resends a huge prefix every call is the signal to start a fresh thread.
