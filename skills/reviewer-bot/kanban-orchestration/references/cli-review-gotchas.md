# Kanban CLI review gotchas (hermes kanban)

- `request-changes` takes the reason as a POSITIONAL argument: `hermes kanban --board B request-changes <id> "[round N/3] 🔴 ..."`. Passing `--reason` fails with "unrecognized arguments".
- A card whose review run is live shows `running`. Both `assign` and `unblock` fail on it ("currently running (claimed)"). Kill the live worker (`ps ... "work kanban task <id>"`), run `reclaim <id>` (the card goes back to `review`), then call `request-changes` or `complete`.
- A review worker that parks a card waiting on an external chain sometimes uses `block`. Convert that to `assign coder-bot` + `schedule` immediately, because a repeated block triggers triage auto-decompose (see parking-external-waits.md).
- **If you review a card from the chat while its review run is live, two workers end up on the card.** A `handed off for review` notice starts a reviewer run within about a minute. When you then verify and route the card from the chat (`request-changes` with the GO scope), that run keeps going and a coder run also starts. The dispatcher later reports a false `crashed` for whichever worker lost the lock. Right after the chat-side verdict:
  1. List the card's workers: `ps -axo pid,etime,command | grep "work kanban task <id>"`.
  2. Read the card events to confirm the reviewer run has done nothing irreversible, then kill it.
  3. Keep exactly one coder run. Tell it on the card to check that no launcher is already running on the box before starting one.
- **Run process kills in a separate terminal call; never bundle them with read-only checks.** A `kill`/`pkill` inside a command can trigger the approval prompt. If nobody answers, the whole command is refused, including the verification you bundled with it, so nothing gets checked. Do the read-only verification first, then kill in its own call, or let the stale worker exit on its own.
- `unblock` takes its note as `--reason "..."`. A positional note is read as more task ids and fails with "not blocked/scheduled?". This is the opposite of `request-changes`, which takes its reason positionally. A release cron that calls `unblock` must use the flag.
- A card in `review` with no live run refuses both `schedule` and `request-changes` ("not in an active review run"). Run `reopen-review <id>` first, then `schedule <id> "<note>"`, and confirm the result with `show`.

## Writing gates for the remote platform notebook re-runs
- Never gate raw float outputs of GPU stages at 1e-6. Two runs of the same notebook differ by about 1e-4 because GPU ops are nondeterministic (RSNA P75 rev1 vs rev2: 8.3e-5). Gate the rank or submission outputs at Δ0, and record raw diffs only.
- An in-notebook time guard must use the same margin as the pre-registered GO rule. A ×1.3 + 40 min guard against a +1,800 s prereg margin would have silently skipped the new stage (RSNA P79 round 1) and wasted a submission on an output identical to the base.
