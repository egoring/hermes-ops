# Parking a card that waits on an external job (PC chain, the remote platform run)

## Rule
Park with `schedule`, never with a repeated `block`.

## Why
The board counts same-kind blocks (`block_recurrences`). The 2nd park of the same kind
(e.g. `needs_input`, or `dependency` re-kinded to `needs_input` because the card has no
open parent) routes the card to `triage` (`block_loop_detected`). With
`auto_decompose: true` the decomposer then splits the root into child cards assigned to
the root assignee, which start running at once and can duplicate live work.

## How to park a card that is in `review`
`schedule` only accepts todo/ready/running/blocked, so run these in one command:

    K="hermes kanban --board <board>"
    $K assign <id> <coder-profile>
    $K reopen-review <id> --reason "[parking, not a rejection, round N/3 unchanged] ..."
    $K schedule <id> "<what it waits for; which cron releases it>"

The release cron's `unblock` re-opens `scheduled` cards too.

Common refusals and what they mean:
- `cannot schedule <id>` means the card is still in `review`. Run `reopen-review` first.
- `request-changes` answering "not in an active review run" means the review run has already exited. Use `reopen-review` + `schedule` instead.
- `unblock` takes its note only as `--reason "..."`. A positional note is parsed as extra task ids, and the error then echoes your note text followed by "(not blocked/scheduled?)". Read which string the error names before concluding anything. If it names the real card id, the card is already `ready`: the dispatcher will pick it up, so a `comment` alone carries the new instructions. Cron scripts that call `unblock` need `--reason` too, or the release silently does nothing.

A worker that blocks with a capability claim ("python execution is refused in this mode") is not a design problem when other runs of the same profile executed the same tools that day. Treat the block as transient. Write the remaining steps in a comment and re-dispatch the card with `unblock` or `assign`. Do not change config because of it.

A worker blocked by the approval guard on an irreversible step (for example `rm -rf` on a home path, "delete in root path") is different. Nobody can approve it headless, and re-dispatching only repeats the block. Hand the user the exact command. After he runs it, verify the result yourself, then close the card from chat: `comment` the measured numbers, `assign <id> reviewer-bot`, `unblock <id>`, then `complete <id> --result "..."`. `complete` does not accept a `blocked` card directly. Any remaining doc step goes to a small helper card.

If a review run parks the card with `block` itself, as an INTERIM pass, convert it at once:
kill that run's pid, then `assign <id> <coder-profile>` and `schedule <id> "..."`. `schedule`
accepts a `blocked` card directly. The next park would otherwise trip block-loop triage.
Before treating a "blocked; needs attention" notice as a problem, read the card's last comment
and block reason. A review worker that could not run `schedule` from its own context parks with
`block` and writes "PARKED, no human action needed". In that case, verify its claims against the
raw files and tell the user the card is just waiting on the box. If the release cron covers the
card, no conversion is needed.

## Acting on a card whose review run is still claimed
First check whether the claimed review run is doing the same verification you would do. If it is, let it finish and re-read its comment against the raw files afterwards. A kanban review worker can verify and park an INTERIM card correctly on its own.

Keep the worker kill in its own terminal call, apart from the read-only checks. A kill can trigger an approval prompt. If the prompt goes unanswered, the whole call is refused, the read-only verification never runs, and you may not retry it.

When you decide a review from chat while a review worker holds the card:
1. Kill the worker pid.
2. Run `$K reclaim <id>`. Without it, `assign` fails with "currently running (claimed)".
3. Run `$K request-changes <id> "[round N/3] 🔴 ..."`. The reason is positional; there is no
   `--reason` flag. Put the long details in a `comment` first, and keep the reason short.

To approve, run `complete <id> --result "..."` after killing the run.

If the approved artifact can only be submitted after the daily quota resets, do not keep the
card open. Instead, add a one-shot no-agent cron with these parts:
- a time gate (UTC reset + 5 min)
- one call through the locked submit wrapper
- WATCH registration
- a flag file that stops any re-run

After it fires, pause it.

## If triage already fired
1. Kill the child workers: `ps ... | grep "work kanban task <child>"`.
2. `unlink <child> <root>` for each child.
3. `archive <child ...>`.
4. Then park the root as above.

## False "crashed" notices
"crashed (worker exited)" can appear while the worker pid is still alive. The dispatcher
then spawns a second run on the same card, so two runs work it at once. On every such
notice:
1. `ps -axo pid,etime,command | grep "[w]ork kanban task <id>"`: two pids = duplicate.
2. Check what the old run already did (commits, `platform-cli kernels status`, output files).
3. Kill the redundant pid so one run remains.
4. Comment to the survivor what is done and what it must not repeat ("v1 already pushed
   and COMPLETE, do not push again; only re-check gates and request-review").
Never let two runs reach an irreversible step (push, submit) on the same card.
