# Review-stage CLI quirks (hermes kanban)

These came up while handling review cards from a Discord chat session, alongside a live kanban review worker.

## Rejecting a card
- Syntax: `hermes kanban --board <b> request-changes <task_id> "<reason>"`. The reason is **positional**. A `--reason` flag returns "unrecognized arguments".
- The command works **only while a review run is active** (the card shows `running`/`review` with a live reviewer run). Kill or reclaim the review worker first and it fails with "task is not in an active review run".
  - Correct order: put the full instructions in `comment`, run `request-changes` while the worker is still alive (it reports "routed to coder-bot"), and only then kill any duplicate review worker.
- Every rejection reason starts with `[round N/3]`.

## Reassigning
- `assign` refuses while a worker holds the claim ("currently running (claimed)"). Kill the duplicate worker first (`ps -axo pid,command | grep "[w]ork kanban task <id>"`) or wait, then assign.
- `unblock` works only on `blocked` or `scheduled` cards.

## Parking a card while an external job runs
- A review worker that confirms an INTERIM report often parks the card with `block`. A second `block` sends the card to triage and auto-decomposition.
- Convert the park to: `assign <id> coder-bot`, then `schedule <id> "<reason>"`. A release cron runs `assign` + `unblock` when the external chain exits. See `parking-external-waits.md`.

## Approving and submitting from chat
- When the chat session verifies and submits, kill the live review worker first, so the worker and the chat cannot both submit. Then submit through the single-submit wrapper, then `complete <id> --result ...`.
