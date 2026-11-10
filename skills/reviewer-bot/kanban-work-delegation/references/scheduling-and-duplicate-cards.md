# Scheduling waits and avoiding duplicate cards

## SCHEDULED_UNTIL must use hour 00-23
- `kanban_wake.py` parses the value with `datetime.fromisoformat`. `T24:00:00` raises an error, and the card is reported as a format error and **never wakes**.
- After a worker schedules a card, run `python ~/.hermes/scripts/kanban_wake.py --dry-run` to confirm the value parses.
- You cannot re-schedule a card that is already `scheduled` (`hermes kanban schedule` returns "cannot schedule"). To fix it:
  1. Comment with the correct format, e.g. `2026-11-09T00:30:00+09:00`.
  2. `unblock` the card (only when no worker is running).
  3. The next worker queries the status once and re-schedules with the corrected time.

## Never block a card that is only waiting
- A `block` on a long external wait (TPU queue, the remote platform scoring) can loop into `block_loop_detected` and **auto-decomposition**.
- One such decomposition produced six child cards, one of them "push kernel exactly once". That child would have made a second, unapproved external push.
- In the card body, tell the worker:
  - Keep scheduling until a hard deadline, e.g. push+48h.
  - At the deadline, leave only a comment.
  - Never split the card into subtasks.
- If decomposition has already happened:
  1. Confirm the children have no `worker_pid`.
  2. Archive all the children immediately.
  3. Check git status for anything a child already ran.

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
