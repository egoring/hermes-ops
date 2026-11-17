# Overnight autonomy, conditional submits and quiet hours

Read when the user delegates decisions overnight, pre-approves submits on results that do not exist yet, says "act now" while an opinion card is open, or lifts quiet hours.

## Delegated decisions overnight

**"Decide yourself until morning"**
- Write the branch table to a plan file in scratch, with a running "decision log" section. Append one line per autonomous decision as it happens, so the morning report is a read of that file.
- Also list what stays out of scope: submits beyond pre-approved ones, deletions, threshold changes, starting a follow-up the user has not seen.

**"Decide yourself until morning; ask fable if something needs discussing"** delegates the pending go/no-go calls, not submits.
- Before the result exists, pre-register a branch table for each pending result, e.g. control ≥ baseline → start arm X and build probe Y; slightly below → start X only; far below the monitor value → suspect the eval path and investigate.
- Post the table on the gated card and on the plan card, then execute it without further asking.
- Anything the table does not cover goes to a fable-bot opinion card first (independent recomputation, no decision). Then you decide and proceed.
- Submits still wait for the explicit word. the remote platform pushes the user pre-approved in chat ("push right away") go into that card's body with the push count and the `-b` fallback.
- Report every autonomous decision in the morning with its pre-registered rule.
- **"If something gets submitted overnight, check what is next and go"** → make the follow-up mechanical before any score exists:
  - Write a decision-table file in scratch: events E1..En keyed on each pending submission's score band, each with exactly one action. An action is either a single-variable card (push 1 → submit 1) or "record only". Add a submit priority for when the UTC-day cap binds, and the rule "anything not in the table → report in the morning, no new experiment".
  - Prefix every overnight submit message with a phase tag (`p59 `, `p56s `, ...).
  - A time-gated one-shot submit cron ("submit after the UTC reset") on a 30-min cadence can fire up to 30 min late. When the user asks for status after the gate time and the flag is still unset, run the same script by hand under an outer `perl alarm` cap, confirm one submission with the phase prefix, then `hermes cron pause` the job and add the new ref to the score watcher.
  - Add a no-agent cron (every 10 min) that reads the submissions csv. When a ref with a known prefix first shows a score or an error, it creates one reviewer-bot card whose body is that score plus the table. A state file keeps that to one card per ref.
  - The card applies the table, checks the board for an existing card with the same purpose, and @-tags nobody in quiet hours.
  - Do not let a score that changes two variables at once trigger an action. Example: a relabelled member's standalone score must not justify a blend-weight change; record it only.
  - When an overnight result makes an off-table action attractive (e.g. that standalone score jumped), the table still says "record only"; pitch the action to the user in the morning as a new single-variable card with its own baseline (the newest blend submit), and once approved, drop its phase prefix from the trigger cron so a second card is not auto-created.
  - A false "crashed" notice on a card that already pushed is answered with the existing crash rule (comment "already pushed, do not re-push" first). Write every kernel wait in overnight cards as `sleep` <= 60 + heartbeat, with no single tool call over 5 min.
- **When you queue a new chain behind running work, re-check every release cron that waits on the same box in the same turn.** A cron created an hour earlier whose predicate was "trainer process count 0" stops working once the new chain starts that trainer seconds after the old one ends. The gated card then waits for the whole new chain. Re-key the predicate on the old run's own tag/`--out` string, and comment on the gated card that the box's GPU is now someone else's (CPU only, `nice 19`, `CUDA_VISIBLE_DEVICES=""`, RAM floor).
- **A card that launches its own detached chain may end its first run with one deliberate block** ("chain waiting, no input needed", pid + log path). Register the release cron in the same turn. The cron emits each verdict or marker line once, and when the launcher count is 0 and the last line is terminal, it runs `assign <id> coder-bot` + `unblock`. The `blocked` notice that follows is expected: confirm the chain pid and the pre-registration commit time, and reply in a few lines.
- **Pitch an option to the user only when its trade-off is really balanced.** If the downside clearly dominates, decide it yourself and mention it in one line: it departs from the pre-registered config, adds variance that blurs the readout, or spends a submit and GPU hours for an early peek. This user said to skip such options without asking. Ask only about choices whose value depends on his priorities.
- **When the user says "act now" while an opinion card is still open, do not wait for it.** Decide from the numbers you have recomputed, and post the decision on the gated card as an override comment. In that comment, put PUSH_OK behind that card's local gates (P1). Then comment on the opinion card that the decision is made, and ask it to report any 🔴 as a comment right away. Watch the opinion card until the push. If a 🔴 arrives first, post a stop comment on the gated card; if no stop comment exists, the worker proceeds. When the opinion lands after the push, reconcile it: adopt its 🟡 as a pre-result amendment (e.g. the verdict bands) before the score exists, and correct any of its "missing" findings that the timeline already resolved.

"Submit it if the verdict looks OK" on an experiment whose results do not exist yet (overnight) is handled the same way, but needs a design card first. Its body holds:
- A mechanical selection rule that the results cannot bend: which run is picked, with a pre-named default when nothing is adopted, and "no pick, no submit" when a required seed run is missing.
- Numbered submit gates: queue finished cleanly, bug floors, kernel COMPLETE with weights md5, parity, a time-limit check, a remote = local diff limited to the selection constant, and a free UTC-day slot.

Record the user's words on the card as a user decision. In the reply, say which the remote platform GPU pushes you take the instruction to include, so the user can withdraw it.

## Quiet-hours overrides and night watchers

- **Do not @-tag inside the user's quiet hours** (see memory), even when a decision is pending.
  Check the clock before writing the tag; say "for the morning" instead and let the cron flush.
  When the user lifts quiet hours for one night only ("OK to alert until 1 am tonight"), keep the window itself as it is. `is_quiet()` already honours an `OVERRIDE_UNTIL` file (epoch; ignored once past or unreadable) in the quiet-hold dir, so write the epoch of the stated end time there and confirm with `python3 -c "import quiet_hours as q; print(q.is_quiet())"` from the scripts dir. Note that held alert files from old jobs will flush on the next tick. The override is global — it un-silences every cron that routes through `emit()`. When the request is about ONE project's alerts ("심사 기간엔 밤에도 알려줘"), first read that relay's wrapper: a contest relay may already bypass quiet hours inside its own judging window (`in_window(now)` → print directly). Then check the window bounds and leave `OVERRIDE_UNTIL` alone, so unrelated projects' alerts stay quiet.
  To actually use such a window, add a one-night no-agent watcher cron (every 15 min, `--repeat` bounded) that keeps a small state JSON and emits once per event: long-job milestones (e.g. every 2 epochs with the monitor metric labelled as monitor-only), job finished (with the raw final log lines + tag), download done, and a stall alert after 2 unchanged ticks. Route it through `emit()` so anything after the override expires is held for the morning, and tell the user which expected events will likely land after the cutoff.
