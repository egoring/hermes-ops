# Scheduling waits and avoiding duplicate cards

## SCHEDULED_UNTIL must use hour 00-23
- `kanban_wake.py` parses the value with `datetime.fromisoformat`. `T24:00:00` raises an error, and the card is reported as a format error and **never wakes**.
- After a worker schedules a card, run `python ~/.hermes/scripts/kanban_wake.py --dry-run` to confirm the value parses.
- You cannot re-schedule a card that is already `scheduled` (`hermes kanban schedule` returns "cannot schedule"). To fix it:
  1. Comment with the correct format, e.g. `2026-11-09T00:30:00+09:00`.
  2. `unblock` the card (only when no worker is running).
  3. The next worker queries the status once and re-schedules with the corrected time.

## Holding a card the user paused ("the GPU is busy, I'll tell you")
- When the user pauses a card whose worker already parked it with a `SCHEDULED_UNTIL=` retry, the auto-wake will still fire it. Re-park it without the marker. `schedule` refuses an already-`scheduled` card, so run both steps in one shell command while no worker is live: `hermes kanban --board <b> unblock <id> && hermes kanban --board <b> schedule <id> "<user hold reason, no SCHEDULED_UNTIL>"`. Run separately, the card sits in `ready` long enough for the dispatcher to claim it and push.
- Put the resume rule in the reason: the reviewer unblocks on the user's word, and any external rejection caused by the user's own use (e.g. a session-limit refusal) resets the card's retry count.
- Verify afterwards: `runs <id>` shows no new worker, `kanban_wake.py --dry-run` does not list the card, and the external resource is untouched (e.g. `platform-cli kernels status` → not found / no new version).

## Never block a card that is only waiting
- A `block` on a long external wait (TPU queue, the remote platform scoring) can loop into `block_loop_detected` and **auto-decomposition**.
- One such decomposition produced six child cards, one of them "push kernel exactly once". That child would have made a second, unapproved external push.
- In the card body, tell the worker:
  - Keep scheduling until a hard deadline, e.g. push+48h.
  - At the deadline, leave only a comment.
  - Never split the card into subtasks.
- A card that blocks twice for real spec questions trips the same detector (limit 2) even though nothing is waiting. When you answer the first block, answer every question the worker will predictably hit next (tool/permission allowances, sibling hard-coded values, file-count expectations), not only the one it raised.
- If decomposition has already happened:
  1. Confirm the children have no `worker_pid`.
  2. `hermes kanban unlink <child> <root>` for each child: the decomposer makes the children parents of the root, so the root stays `todo` behind them.
  3. Archive all the children immediately. The root then returns to `ready` by itself, so `unblock` is not needed (it answers "not blocked").
  4. Put the decisions for the original block reasons in one comment on the root, so the next run continues as a single card.
  5. Check git status (or the file baseline) for anything a child already ran.

## Completion watchers (background poll loops)
- Stop an old watcher by its pid (`kill <pid>` from the start response). Never use `pkill -f '<card ids>'` from inside the new watcher command. The pattern also matches the new shell's own command line, so the new watcher kills itself and no completion notice ever arrives.
- After any block, unblock or relink, restart the watcher with the current card list. A watcher that exited on a block, or whose list lacks newly inserted cards, stays silent.

## Re-ordering a queue: link the new parent before unlinking the old
- To move a queued child behind a different card, run `hermes kanban link <new_parent> <child>` **first**, then `unlink <old_parent> <child>`.
- In the other order, the child has no open parent for a moment, flips to `ready`, and the dispatcher can claim it and start a GPU job on a host another card needs.
- After the move, check `hermes kanban runs <child>` (it should show no runs yet) and `show --json` (status `todo`, parents = the new card). Leave a comment that says why the order changed.

## Design cards spawn their own implementation cards
- A design card assigned to `reviewer-bot` is dispatched to a worker within seconds. That worker may refine the design and create its **own** coder card, which duplicates the one you created.
- `complete` on the design card fails while its worker is live ("a live worker is running it").
- Pick one path:
  - Let the design worker create the implementation card, or
  - Write the design only to an outbox file and create just the coder card.
- If duplicates exist:
  1. Compare `worker_pid`, start time, and files already present in the repo.
  2. Keep the further-along card.
  3. Archive the other with a comment that names the survivor.
  4. Fold any missing scope into a comment on the survivor.
