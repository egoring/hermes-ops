# Watching cards and auditing role separation

## Background card watchers
- Write the watcher in Python (`python3 -u - <<'EOF'` with a list literal of ids). A shell loop `L="t_a t_b"; for t in $L` does not word-split under zsh, so every poll asks for one task named "t_a t_b" and the watcher prints `no such task` until its timeout — it never fires.
- Poll `hermes kanban show <id>` line 2 for status once a minute; exit on the first transition into done/blocked/triage/scheduled/archived and print the last `runs` line. Start it with `background=true, notify=true`.
- One watcher per active chain. When adding cards, kill the old watcher and start a new one with the full list; the SIGTERM notice of the killed one is expected — answer it in one line.
- After a watcher fires, re-arm it for the remaining cards before replying; otherwise the next completion arrives silently.
- Old broken shell watchers keep running for hours and later surface as walls of `no such task`. When one appears, sweep with `process_manage(action='list')` — not `ps | grep`, whose pattern misses watchers started from other shells — and `kill` every entry whose status is `running` except the current watcher, in the same turn. Then answer the notice in one line (its cards were already done).

## Overnight chains (user wants it "done by morning")
- Chain every remaining card by dependency before going quiet: create new prerequisites with `--parent`, and insert a prerequisite in front of an already-queued `todo` card with `hermes kanban link <new> <queued>` plus a spec-correction comment widening that card's allowed diff. Never edit or transition a card whose worker is running; queue the new work behind it with an extra `--parent`.
- The final-check card can be created up front with `--parent <last impl card>`; it stays `todo` until the chain finishes. Post the routing line when you create it.
- Use ONE watcher for the whole chain that prints intermediate `done`s and exits only on the last card or on blocked/triage/scheduled, so the overnight thread gets one wake-up instead of one per card.
- Quiet hours suppress tags, so schedule a one-shot `cronjob_manage create` at 09:00 (Asia/Seoul, deliver to origin, toolsets terminal+file, workdir = project) with a self-contained READ-ONLY prompt: card statuses and where a stopped card stopped, artifact sha/size, final-check 🔴/🟡/🟢, test-env readiness (ports free, launcher points at the newest zip), and the user's to-do list. The cron session has no chat context, so name every card id and path in the prompt.

## Parking a card on a user hold ("I'm using the GPU, I'll tell you")
- A card whose last scheduled reason has `SCHEDULED_UNTIL=` gets auto-woken by the wake script; a scheduled card without it is left alone. To turn a timed retry into an indefinite hold, re-schedule it with a reason that has no `SCHEDULED_UNTIL=` (who holds it, why, "reviewer unblocks to resume", and that retry counters restart from 0 because the user's own session caused the rejections).
- `hermes kanban schedule` refuses a card that is already scheduled. Run `hermes kanban unblock <id> && hermes kanban schedule <id> "<reason>"` as one command so the dispatcher has no window to claim the briefly-ready card, then confirm the last run row is the schedule, no worker process exists for the card, and the external job was not started (e.g. kernel status 404 for a never-pushed kernel).
- Do this only when no worker is running on the card (last run not `running`); otherwise comment and let the worker transition it.
- Resume with a comment stating the user's go-ahead and the reset counters, then `unblock`.

## Reading a finished card's full result
`hermes kanban show <id>` prints only the truncated "Latest summary"; a final-check worker may write no report file. The structured result (per-criterion verdicts, defects by severity, not-verified list, side effects) is in the run row: `sqlite3 'file:~/.hermes/kanban/boards/<board>/kanban.db?mode=ro' "select metadata from task_runs where task_id='<id>'"` (per-board DB, not `~/.hermes/kanban.db`). Re-derive the user report from that JSON, not from the summary line.

## Auditing whether roles held
Evidence comes from the profiles' own session stores, not from worker self-reports.
1. Tool calls: open `~/.hermes/profiles/<profile>/state.db` read-only (`file:…?mode=ro`), table `messages`, `role='assistant'`, `tool_calls` JSON since the window start. Flag `write_file`/`patch` whose path is inside the project, and terminal/execute_code commands that mention the project path and contain `cp|mv|rm|rsync|sed -i|tee|>` or Python `open(…,'w')`/`write_text`, excluding commands that go through the recording wrapper (`cc_run.sh`). Then read each flagged command: copies *from* the project into scratch are verification, not authorship — judge by the destination.
2. Which model wrote code ("another session had Haiku coding — check it"): per profile, `select model,count(*) from sessions where started_at > <window> group by model` in `state.db`, then for every session on the suspect model list its file writes (`write_file`/`patch` paths plus shell redirects, `sed -i`, `tee`, `cat >`, platform-cli push/submit). For each written file report whether it is still in use (referenced by a live cron, script import, or repo path) and, if live, test it directly instead of trusting the session; files of finished projects or since-deleted helpers are "no impact". Leftover `_`-prefixed one-off scripts are cleanup items.
   Recorder logs: for each recorder log (`_cc_logs/*.out.json`) in the window, collect `modelUsage` keys; report counts and the files that fail to parse (a run still in progress, or a broken log).
3. Review pairing: for each card, `show --json` events of kind `review_requested` → (implementer, reviewer) must be (coder-bot, reviewer-bot); count changes_requested rounds against the 3-round cap; count `<@…>` mentions in approval summaries when the user asked for untagged completions.
4. Discord-session transitions: confirm each complete/unblock you made was on a card with no running worker (`runs` last line not running).
5. Report: kept / violated (time, card, what, already corrected?) / your own deviations (e.g. running a read-only script in the live tree instead of a copy). Fix forward: put a missing rule into the per-card comment of the remaining cards, not only into a skill the worker may not load.

## Live status, ETAs and machine load (step 5)

**Before quoting an ETA, read the live process, not the output folder.** Take `ps` for the
running command (flags such as `--fresh` mean the worker restarted from zero), and take the
progress line of the log it writes (`[k/N]`). Then compute the rate from two timestamps.
A records folder left by an earlier pass can be nearly full while a fresh rerun is at 7%.
"Done in 10 minutes" read off that folder turned into a 5-hour run, and the estimate had
to be withdrawn. If you can't tell why the worker restarted, say so; don't guess a reason.

**"Is this overloading the machine?" — answer with four readings and the end time.** Give
load average against the core count, `memory_pressure` free %, `docker stats` per
container (CPU, memory against its cap), and `pmset -g therm` and power state. Add the
time the job ends, since the load stops then. List stale containers you see (days old,
0% CPU) as cleanup for a card, not something to delete yourself. Give the one knob the
user can turn (concurrency) and what it costs in time.

For your own "is it still running?" checks, keep one read-only status script in the
profile's `scripts/`. It covers board `ls`, progress files, remote job status, and live
worker pids per card. Run it with `bash <path>`. Long inline one-liners that chain many
commands are rejected by the command parser, and a script is re-runnable anyway.
Write verification probes the same way, as `review_<card>.py` in scratch, with a step argument (`tab`, `dup`, `sym`, ...). The terminal lifecycle guard refuses inline heredocs that name large data files, because it cannot scan them. The next review round of the same card then re-runs the same file unchanged.

## Reading a report card's full result (step 6)

**Read a report card's full result, not the truncated summary.** `hermes kanban show`
cuts a long `kanban_complete` summary mid-sentence and drops its metadata. The quickest
full copy is the board DB itself: open `~/.hermes/kanban/boards/<slug>/kanban.db`
read-only (`?mode=ro`) and `select summary, metadata from task_runs where task_id=?` —
`metadata` holds the per-criterion verdicts, the checker's own numbers, defects by
severity and any rubric disagreements; `tasks.result` holds the one-line advisory. The
worker's `~/.hermes/profiles/<worker>/state.db` (`messages`, last assistant row whose
`tool_calls` holds `kanban_complete`) is the fallback when the run row is empty.
Relay from that, and say which of your earlier claims it overturned.
A fable opinion card's raw numbers also sit in its own scratch (`~/.hermes/profiles/fable-bot/cache/scratch/<topic>/probe*.log`). Read those logs before you relay, because the summary drops the per-arm tables (bands, ratio-shift grids) you need to judge its advice.
