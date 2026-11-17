# Parking a scheduled card so auto-wake leaves it alone

Use this when the user says "hold it until I tell you" (e.g. "GPU 사용중이라 나중에 알려줄게") about a card that a worker already parked with `SCHEDULED_UNTIL=...`.

- `~/.hermes/scripts/kanban_wake.py` (runs every 15 min) reads only the reason of the **last `scheduled` event**. If that reason has `SCHEDULED_UNTIL=<time>` and the time has passed, it unblocks the card and a worker picks it up again.
- A scheduled card **cannot be scheduled again**. `hermes kanban schedule <id> ...` on it prints `cannot schedule <id>`.
- To re-park it, run both commands in one shell line so the dispatcher has no time to claim the card between them:
  `hermes kanban --board <b> unblock <id> >/dev/null && hermes kanban --board <b> schedule <id> "사용자 보류 ...: 재개는 reviewer가 unblock (SCHEDULED_UNTIL 없음)"`
- The new reason must **not** contain `SCHEDULED_UNTIL=`. Without it the wake script skips the card.
- After parking, verify that nothing ran in the gap. Check `hermes kanban runs <id>`: the new run should show 0s elapsed and no worker. Also check the external side effect, e.g. `platform-cli kernels status <slug>` returns 404, meaning no push happened.
- To resume, comment on the card with the user's go-ahead and reset any retry counters, then run `unblock`.
- Only do this while no worker is live on the card (C6 rule). If a worker is running, leave a comment instead.
