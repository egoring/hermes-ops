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

## Follow-up cards and decisions around a live reviewer run

- **After a reviewer run completes a card, check the follow-up cards it created.** A review run can split off the unfinished part into a new card created `blocked` with an initial-status reason such as "waiting for the box to come back". Nothing will release it, even when the condition already holds. Run `kanban list` for new ids, `show` each one, and check its blocking condition yourself (e.g. ssh reachable, GPU free). If the condition already holds, `unblock` it with the measured facts, subscribe it with `wake`, and confirm that a worker spawned. The user's pre-approval (e.g. "train if PASS") carries over to that card, so say so in the reason.
- **A decision you make in chat about a card under review does not bind the reviewer run that already holds it.** That run can decide the opposite on its own and spawn a follow-up card for it, e.g. "copy the dataset" when the chat said "hold". Before you announce a hold or a close, `kanban show` the card for an active run. If one is active, post the decision as a comment that says "complete only; create no follow-up card". If a contradicting card already exists and has run, tell the user plainly that the two decisions conflict. Then re-weigh the original decision on its merits, because the artefact now exists. Ask the user to choose; do not silently delete or adopt it.
- **Do not let a review run's "this decision belongs to the user" re-open something the user already decided.** If the chat holds a conditional instruction that covers the outcome ("train if it passes, stop if not"), proceed under it, and say in the reply that it was pre-decided.

## Reviewer run vs chat session on the same card

- **When `request-review --reviewer <self>` arrives, let the spawned reviewer run own the verdict.**
  **This applies doubly to any irreversible step in the review (a the remote platform submit).** The wake reaches the
  The same split applies to verdicts: while a reviewer run is live on a card, the chat session
  reads the diff and reports what it sees, but issues no approve/request-changes/block itself.
  A `blocked` notification on a card your own reviewer run just handled is usually a deliberate
  park (dependency wait on a long box chain, with a release cron that re-assigns the coder when
  the chain exits). Read the card's last comment and the chain process before acting; do not
  unblock or re-review it.
  Do not reclaim or close the card from the chat. Once that run holds the claim, closing
  it from the chat needs `reclaim` + `complete --force`. That reclaim triggers the board's anomaly
  monitor, which @-tags the user with a "lock expired, reclaimed" alert. It also leaves two
  approval comments on the card. In the chat, reply that the reviewer run has the card, check that
  only one worker holds it (`ps ... | grep "work kanban task <id>"`), and wait. When its
  completion wake arrives, re-derive its numbers from the raw artifacts and report them.
  When the user is waiting on the result (e.g. a cron must be registered from the verdict), you
  may verify in the chat right away and post the verdict as a comment headed
  "[chat review — round N: approve, no 🔴. The dispatched review run completes per this verdict]"
  with every recomputed number. Do not touch the claim; the reviewer run reads the comment and
  completes consistently, and its later completion notice needs only a one-line reply.

## Closing a live card with a verdict

- **To close a live card *with* a verdict** (the user ends a verification early and its partial
  results still count): post the verdict comment first, then `kanban reclaim <id>` and
  `kanban complete <id> --force --result "..."`. Plain `complete` is refused while a run holds
  the claim. Afterwards confirm the worker pid from the card's `spawned` event is gone
  (`ps -p <pid>`) and that `show` reads `done` — a reclaimed worker can keep writing files.

## Cards blocked from `review` for a push approval

- **A card blocked from `review` (e.g. the reviewer run blocked to get the user's push approval) returns to `review` on `unblock`, not to the implementer's queue.** Reassigning it to the coder first does not change that: the next run is spawned in review mode (`--skills sdlc-review`) under the coder profile. Such a run may still act on your approval comment (it executed the push here). So after unblocking, read the external side before touching the run: `kernels list --mine --sort-by dateRun` / `datasets list --mine` / the submissions list. **Never kill a worker you think is in the wrong mode until you have checked whether it already performed the irreversible step**; a kill after the push only triggers a `protocol_violation` respawn. Instead, comment "step X is already done at <time>, do not repeat it; continue from step Y". `reopen-review` is refused unless the card is in `review` at that moment.
  If the approval arrives while the card sits in `review` (not blocked), let the reviewer run route it back with `request-changes` headed `[stage handoff, not counted as a rejection, 0/3]`. Put the approved scope (PUSH_OK, push count, slug fallback, wait and verify steps, submit 0) into that reason. The next run is then a normal implementation run, and this worked cleanly. Do not `block` and `unblock` for the approval.
  If the reviewer run already blocked the card for the approval and exited, `request-changes` is refused ("not in an active review run"). This sequence worked, run with no worker alive in between (check `ps` first): post the PUSH_OK scope as a comment (via a file, see the backtick rule below) → `assign <id> coder-bot` → `unblock <id>` (lands in `review`) → `reopen-review <id>` (lands in `ready`, coder). Then confirm with `show` and the next `spawned` event that a normal implementation run started.
  To avoid this whole path, split any card whose later step needs the user's approval (a remote push or a submit) into two cards. The first card builds, does the local checks and ends with request-review; you approve it. Create the second card (`--parent <build card>`) only after the user approves the push. It does the push, waits for the run and verifies the output. Its run is then a normal implementation run, so the approval never travels through a blocked review card.

## Answering a "lock expired / reclaimed" anomaly alert

- **Answering a "lock expired / reclaimed" anomaly alert:** read the evidence log it names
  (`~/.hermes/kanban/incidents/<board>_<task>_<event>.log`). `"manual": true` with a `prev_pid`
  means a reclaim you ran yourself. Then confirm it had no side effects: the reclaimed run's last
  comments, that no external action happened (e.g. the competition submissions list holds no
  stray entry), the card status, and that the pid is gone. Tell the user what triggered it.

## Your own `changes_requested` echoed back

**A status notification can be your own action echoed back.** A `changes_requested` you just issued
arrives worded as "review requested changes (BLOCK); implementation is not approved — decide the
next step", which reads like fresh work. Before acting, `kanban show <id>` and check the event log
and run list: if the latest `changes_requested` carries your own reviewer name and a new worker run
is already claimed against the card, the loop is healthy and the correct action is **none** —
confirm status/assignee routed back to the implementer and stop. Creating a follow-up card here
duplicates work the worker is mid-way through fixing.
