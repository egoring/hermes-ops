# Stuck or un-reviewable kanban cards

## Card sits `ready` for hours, no worker claims it
1. `hermes kanban --board <b> diagnostics` — look for `stranded_in_ready`.
2. `hermes kanban --board <b> show <id>` event log — look for `respawn_guarded {'reason': 'blocker_auth'}`.
3. Cause: the dispatcher's respawn guard regex-matches words like `quota`, `403`, `auth` in the card's stored `last_failure_error` (captured output of an earlier crashed run — e.g. a worker merely *mentioning* a the remote platform GPU quota) and refuses to spawn, silently, forever.
4. Fix: `block <id> "<reason>"` then `unblock <id> --reason "..."`. Unblock resets `consecutive_failures` and `last_failure_error`; a worker is claimed on the next dispatcher tick (~1 min). `reopen-review` does NOT clear the guard.
5. Verify with `show <id>`: a new `claimed` + `spawned` event and a live pid.
- After any crash whose output mentions quotas/auth, check the card is actually re-claimed instead of trusting the `ready` status.
- The block/unblock you did yourself fires a delayed "blocked; needs attention" notification — check `show` before treating it as a new problem.
- `unblock` takes the note only as `--reason "..."`. Text passed positionally is parsed as more task ids and the call fails, which matters inside release crons that run unattended.

## New card sits in `todo` because its `--parent` is blocked
A child created with `--parent <id>` stays `todo` until the parent completes. A parent that is parked `blocked` (for example a generation card waiting for a quota refill) therefore freezes the follow-up card, and no worker ever starts on it. Use `--parent` only for a real dependency. When the link is just for context, put it in the body instead. If you already linked it, run `unlink <parent> <child>`; the dispatcher then moves the child to `ready` and claims it on the next tick. Check the result with `show <child>`.

## `request-changes` refused: "task is not in an active review run"
Happens when the card is in `review` status but no review run is open (e.g. the review worker already exited, or a Discord session is reviewing out-of-band). Use `hermes kanban --board <b> reopen-review <id> --reason "[round N/3] 🔴 ..."` — it returns the card to the implementer with the reason, same effect as request-changes. Keep the round counter in the reason.

## Reviewing a card from the Discord session while its review run is also alive
A `request-review` spawns a reviewer worker for the card, and the Discord session often reviews the same card at the same time. After you act, the dispatcher may also respawn coder runs. The result is two or three workers on one card: one can crash mid-command ("crashed (worker exited)") and another can launch a second copy of a long job.
1. List them: `ps -axo pid,etime,command | grep "[w]ork kanban task <id>"`, then `ps -o command -p <pid>` shows the profile (`-p reviewer-bot` / `-p coder-bot`).
2. Kill the stale reviewer run and any older coder run; keep only the newest coder run. Add a card comment that names the killed pids.
3. Tell the worker to check the box launcher count (`pgrep -fc`) or the `flock` before launching, and to reuse an existing launcher instead of starting another.

## A live worker gets a twin ("crashed" / "pid N not alive" while it still runs)
On macOS the dispatcher can declare a live worker dead: older Hermes builds compared the
worker's psutil start-time fingerprint exactly, and that value shifts 1–3 s after a clock
adjustment, so `_worker_alive()` turns False. Upstream fixed it by reading the kernel birth time
(kanban fix "read process start fingerprints from the kernel birth on macOS"); the remedy is a
Hermes update, not a local patch or longer timeouts. Until updated, treat every "pid not alive"
crash as suspect. Do not judge it by reading `psutil.create_time()` from another interpreter:
that reading can differ from what the dispatcher sees. The dispatcher then spawns a second run, and you get a "crashed (worker exited)" alert while
the old run is still alive. Run the same `ps` listing as above, kill the older pid, and add a
comment telling the surviving run not to push again (check `kernels status` first).
To decide whether the twins actually double-pushed, read the push log (a second attempt refused by
the GPU-session cap creates no version) and `kernels pull -m` the slug, then compare its cells
and `dataset_sources` set against the local build. Report "one push, server copy equals the
build" with that evidence. Also list workers on the other open cards in the same check, because a
long in-turn poll on one card is usually not the only one.
Still keep long waits out of the worker's turn: any card that waits on an external queue (remote job, batch API, box run) parks with `schedule` and a no-agent release cron. In-turn sleep loops are not what triggers the false crash, but they are most of the worker's token cost (each wake past 5 min re-writes the whole cached context) and they keep a worker alive long enough to be misjudged.
When the `ps` command line does not show the card id, read each worker's environment:
`ps -E -o command= -p <pid> | tr ' ' '\n' | grep HERMES_KANBAN_TASK`. A worker whose card id is
unknown on this board usually belongs to another competition's board; leave it alone.
A card that a worker blocked only because of a resource cap ("Maximum batch GPU session count
reached") is not a decision for the user. Unblock it with instructions: retry every 5 min up
to N h, rejected pushes do not count as pushes, never touch other competitions' kernels, and
send an INTERIM review on timeout.

## Parking a card while a remote job is QUEUED/RUNNING
Use the parking sequence below, with a generic no-agent cron in place of the box-launcher
release. The cron holds a `WATCH = {slug: (task, reason)}` table and runs `kernels status`
every 10 min. When a slug leaves QUEUED/RUNNING, it runs `assign <task> coder-bot` +
`unblock --reason "<status>: pull output, run gates, request-review"` once per slug (flag
file). Pause the cron when the table is done; do not create a new cron for each kernel.
Remove a slug from the table as soon as its result is decided another way (a CPU twin finished first, or you verified and submitted it yourself). A stale entry fires later and unblocks the card with an obsolete instruction, which wakes a worker for nothing and adds a block cycle toward triage.

## `scheduled` cards do not release themselves
`schedule <id> "reason"` only parks the card; nothing unblocks it at the stated time. Newer Hermes builds document `schedule <id> --at <ISO8601>`; check `hermes kanban schedule --help` first. Otherwise register one no-agent cron per workstream holding a `CARDS = [(id, release_time, condition)]` table that unblocks a still-`scheduled` card once its time and condition hold. To gate on "Hermes was updated", read the commit from `~/.hermes/hermes-agent/.git/HEAD` (+ `refs/heads/<branch>` or `packed-refs`) instead of calling git: the install is a partial clone where `git show`/`log` can take minutes. Leave verification cards that need a human-confirmed precondition out of the table and release them by hand.
Writing or editing that cron script is still a file edit: hand it to coder-bot as a small card (exact script content + `hermes cron create` line + a dry-run showing "nothing to release") rather than writing it yourself — the role split covers helper scripts under the profile's `scripts/` too, and the user notices when it is skipped.

## Parking an INTERIM card while a long box chain runs
Use `schedule`, not `block`; repeated blocks trigger triage auto-decomposition. A card that is in `review` with your own run claimed refuses both `schedule` and `assign` ("currently running (claimed)"). Sequence:
1. Kill the card's reviewer worker (above), then `reassign <id> coder-bot --reclaim --reason "..."` to drop the stale claim.
2. `reopen-review <id>`, or `request-changes <id> "[parking, not a rejection, round N/3] ..."` if a review run is still open.
3. `schedule <id> "<what was verified; which cron releases it>"`.
4. `assign <id> coder-bot` if the assignee is not already coder.
5. `show <id>` must read `scheduled` / `coder-bot` with no worker pid.
The release cron later runs `assign <id> coder-bot` + `unblock <id> --reason ...` once (flag file) when the launcher count drops to 0. For an external wait with no cron (e.g. paid API batches), a tracked background loop that polls the status script and runs `unblock --reason` when every item has ended does the same job. Write the full `hermes kanban --board <b> ...` command inside such a loop, not a `K="hermes kanban ..."; $K` shorthand: background commands run under zsh, which does not word-split `$K`, so the release step fails with "command not found" after hours of waiting. Check the loop's last line when it ends and unblock by hand if it failed.

## Urgent fix while the main card is busy
When the box needs a small, time-boxed change (a guard value, a conf swap) before a run boundary and the main card's worker is on another stage, open a separate coder card with the deadline in the title, the exact file/line change, "do not touch running processes", and a pointer to the files the other card owns. Do not push it into the busy card's queue: a comment wakes nobody and the worker may not see it before the boundary.

## Card landed in `triage` and the auto-decomposer spawned child cards
Repeated block/park cycles route a card to `triage`. Within a minute the auto-decomposer may split it into child cards that redo finished stages, link them as parents of the root, and start workers on them. `triage` refuses `schedule`, `block`, `unblock` and `promote`. Recovery:
1. List the children: `show <root>` (the "Decomposed into ..." comment) and `ps ... grep "[w]ork kanban task <child>"`. Kill the child workers.
2. `unlink <child> <root>` for each child, and also child → child links, then `reclaim` the running ones and `archive` all children.
3. Move the root out of `triage`. `reassign <root> coder-bot` worked once but was also seen to leave the card in `triage` (both to the same and to another profile). The reliable exit is `kanban_db.specify_triage_task(conn, "<root>", author=...)` (triage → ready, title/body kept), run from a throwaway module with `hermes --run-module` (recipe in references/block-loop-auto-decompose.md). After that, `schedule <root> "..."` works.
4. `show <root>` must read `scheduled` with no parents left. Mine the archived children for any useful measurement (it may be more exact than your estimate), and keep their uncommitted doc edits for the next worker's commit.
To avoid it, park long waits with `schedule` from the start and let one release cron do the single hand-off. Do not block the same card again for each wait.
- **Children that redo a spend-gated stage are a budget risk.** If a child re-runs paid API calls or bypasses a gate that stopped the root (for example, a pilot gate), block or reclaim it at once. A `todo` child refuses `block`, so archive it.
- **If the root's design has to change anyway** (a gate failed and a new spec is needed), skip the unlink/reassign dance. Archive the root and all its children, open one fresh card with the new spec, and add a comment saying "do not auto-decompose; finish in this card".

## Worker blocked with `needs_input` on a contradiction in your own spec
A worker may block before push because two spec items cannot both hold (for example "cells
byte-identical" and "include member X" against a bundle assert). Check its evidence against the
artifact. If the evidence holds, the error is yours. Decide in the same turn which item serves the
card's stated purpose. Write the decision as a card comment: what was wrong in the spec, the
chosen option, the exact allowed diff, and the gates. Then `unblock --reason` it. Do not ask the
user to pick between options of your own spec. Tell the user in one line that the card text was
wrong.

## A spec comment posted after the worker already handed off
A card comment wakes nobody. If the worker sent request-review before your new instructions
landed (for example, an independent opinion arrived and changed the gates), the next run never
sees them. Check the handoff text against your latest comment. If anything is missing, kill
your own reviewer run (`ps` listing above), then `request-changes <id> "[GO, not a rejection,
round N/3] apply comment <time> ..."` and list the items in the reason itself.

## Worker blocks because it "cannot read the spec"
After dozens of comments, `kanban show` (and especially `--json`) grows past 100 KB. An unattended worker whose read tool truncates, and whose inline `python -c` is refused, blocks with a capability reason instead of implementing. Write the current instructions to a file in the repo (e.g. `analysis/<phase>/spec/<time>_<topic>.md`, a few KB). Then comment and unblock with: read that file only, do not read the full `show` output, and run checks as saved scripts (`analysis/_tmp_*.py`) instead of inline code. For long cards, put each new spec in such a file from the start and keep the comment to a pointer.

## Worker re-asks a decision you already posted
A fresh worker run may read only the card body and its own last summary, so it hands off again with "decision needed" on a question your comment already answered. Do not answer in another comment. Put the decision at the top of the body with `kanban edit <id> --body "$(cat $F)"`. The header holds the chosen option, the spec file path, any allowed exceptions to byte-identity, and "decided, do not ask again"; keep the old body below it. Then `reopen-review` (or `request-changes` if a review run is open) with the decision restated in the reason.

## Comment bodies lose backtick-quoted names
A comment passed as `"..."` on the command line runs backticks as command substitution, so
code names like `` `fly_data.FlyStudies` `` vanish silently. Write the body to a file with a
quoted heredoc (`cat > $F <<'EOF'`) and pass `"$(cat $F)"`. If one slipped through, post a
correction comment that restates the affected lines.

## One release cron per box chain
After the chain's single hand-off (flag file present), switch the same cron to reporting stage
changes only (read the chain's stage file, emit when it differs from the last seen value),
instead of creating another cron per stage. Route its output through the quiet-hours emitter.

## Auditing crons ("쓸모없는 cron 정리해줘")
Decide each job by the state of the thing it watches, not by its name or how old it is.
1. Run `hermes cron list` and open every script's docstring.
2. For each job, check what it watches:
   - its state file (are any watch-list items still pending or ERROR?);
   - the box process or chain stage it watches (`ssh <box> ps`, stage file);
   - the card it releases;
   - the deadline of the competition it belongs to.
3. Remove a job only when its target is finished: the score is recorded, the chain is done, or the card is closed. Keep any job that guards a live run, including a duplicate-push or GPU guard. For each kept guard, read its kill/stop pattern: a disk or box guard written for older jobs (`pkill -f '<old trainer names>'`) silently skips the trainer that is running now. Add the current trainer to the pattern.
4. Keep a paused watcher whose list still holds an ERROR item that may be rescored. the remote platform re-scores queue-timeout errors later.
5. For a competition's crons, do not delete them one by one before its deadline. Name the deadline and remove the whole set right after it.
6. Report each job in one line: what it watches, its current state, and keep or remove. Also report leftover output dirs of deleted jobs by count and size, and remove them only if the user asks.

## A live worker on a `gave_up`/`blocked` card finishes anyway
After repeated false crashes the dispatcher can mark a card `blocked` (`gave_up`) while its
last worker keeps working. That worker cannot call `request-review` ("not running"), so it
posts its completion report as a comment. Verify the report from the artifacts as for any
review (recompute the gate numbers, check remote state yourself). Then post the verdict as a
comment and close the card with `complete <id> --result "approved by reviewer: ..."`. Put the
follow-up work in a new card. Do not unblock the card just to obtain a review run: that
spawns a fresh worker that re-reads the body and may redo pushes.

## Passing a stage gate: do not use `request-changes` as a GO
`request-changes` is the rejection verb; using it to say "go on" corrupts the 3-round rejection count and fires a "changes requested (BLOCK)" alert. One card that is passed back and forth this way for many stages becomes a multi-day session (dozens of runs, dozens of unblocks). Make each card one verifiable stage: approve it, and put the next stage in a new child card. If a review run is open and you only need to add instructions, comment and `unblock --reason`. Only when there is no other way to return an open review run (for example a comment that landed after handoff, see above), start the reason with `[GO, not a rejection, round N/3]`, say so to the user in one line, and do not count it as a round.
