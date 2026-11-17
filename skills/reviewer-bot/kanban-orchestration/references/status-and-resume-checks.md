# "Is anything running?" / "can we continue where we left off?" / "can we ship before it finishes?"


Answer from the machine and the board, not from memory. Run one batch:

1. `ps aux | grep -iE "python|bench|eval"`: the worker's actual script, its CPU% and start time.
2. `hermes kanban list | grep -viE "done|archived"`, then `kanban show <id>` on each live card for
   the round number and the latest review summary.
3. `ls -lat <card output dir> | head` and the tail of its run log: what was rewritten and when.
   An empty log next to a busy process means the process is still running, not that it hung.

Report per card: what finished, what is running and for how long, and the headline counts
(e.g. how many games passed the fidelity check). Flag counts that look like a spec defect
rather than a worker defect.

**"How can I see what is running from Discord?"** Offer a no-agent status-board cron at fixed hours (e.g. 9/12/15/18/21 local, through quiet-hours `emit()`). It prints one screen:
- box up/down, host-disk free, running job names, and the progress line of the live run
- RUNNING/QUEUED kernels
- best score and PENDING submission refs
- live cards with a status icon and assignee
Long-dead blocked cards are skipped. Pair it with the box-down gate cron, so an outage is reported within minutes instead of through a worker's report. `/kanban --board <b> ls` in the thread is the instant, card-only alternative.

**"Summarise everything so far into an md and upload it"** means a file attached in the chat
(`MEDIA:<abs path>`), not a the remote platform or git upload. Refresh the live facts in one batch first
(submissions list with status and score, every live card's status and last events, `git log`,
remote job progress), because a result often lands while you write. If one did, put it at
the top of both the file and the reply. File sections, in order: header (time, competition,
deadlines, current best, [measured]/[estimated] legend) → submissions table → completed work
by phase with key numbers → in progress with ETAs → decisions needed, each with options and an
advisory pick → ops state (quota, box, active crons, cards) → risks and unverified items →
file locations. Write it in scratch, not in the repo. In chat, give only the new result and the
decisions list, plus the `MEDIA:` line.

**A card can close without you noticing.** Small cards (a figure script, a doc edit) finish within
minutes. When the user cancels or changes their mind right after you dispatch, `kanban show` before
replying: if the card is already done, say so, list the artifacts it left (and that nothing was
published), and offer removal as a separate cleanup instead of claiming it was stopped.
A `request-review --reviewer <self>` spawns a separate
reviewer run of your own profile that may approve and complete the card on its own
(a chat-side `complete` then fails with "unknown id or terminal state": post your check as a
comment instead). Before
telling the user a card is "still running" or summarising a build, `kanban show <id>` and read
the run list and last events; if a reviewer run already completed it, re-read the result files it
cited (hash the artifact, open the summary JSONs) and report that verdict as confirmed-by-you.

**"Is there anything left to do?"** First sweep for loose ends: runs whose result files exist but whose card was never judged. A wake cron keyed on a process pattern can miss them. Judge each one from its raw files against its pre-registered gate, then `complete` it. Remove the watch crons of finished phases in the same pass (`hermes cron remove <id>`). Only then list the remaining options as a table: expected Δ, cost, verdict. Say plainly when no experiment is worth starting, and name the cheap standing work instead: daily public-notebook watch, and the final-slot selection.

**"Did we miss anything?" / "review everything"** — run this checklist in one batch and report each line as fixed / OK / needs a decision:
- Work-log doc: `grep -n "^## Phase"` against every card closed since the last sweep. A phase judged in chat or by a reviewer run often has no section (project rule C4). Hand the missing sections to helper-bot with "copy the numbers from the card's last reviewer comment, no recomputation", path-only commit.
- Board: `kanban ls` minus done/archived. Archive long-blocked cards that later phases superseded, with a one-line comment saying which.
- Crons: every job's target terminal? Remove finished-phase one-shots and jobs paused for a week or more. Keep any watcher with a PENDING target, including another competition's submission.
- Our uploads: confirm each private Dataset is really private with an anonymous request (`curl -s -o /dev/null -w "%{http_code}" https://www.platform-cli.com/api/v1/datasets/view/<owner>/<slug>`: 403 = private). Run a known public Dataset alongside it as the 200 control.
- External-data ruling: re-read the host post in the browser and quote the condition we meet, plus any unanswered objection.
- Final slots: whether the user has selected them, and what auto-selection would do on a displayed-score tie.
- In a code competition, a scored submission is fixed: its hidden-test run is already done. Public weights changing later cannot affect it, so do not list a "final-day sha check" for scored submissions. That check applies only to a new submit.
End with the numbered decisions for the user, and @-tag outside quiet hours.

For a resume check, add two things to that batch: `kanban show` on every **blocked** card (its
last comment records why it stopped and what the re-issue plan was), and the output directory of
the most recently closed card. Collected-but-unjudged data is the usual loose end — a collection
card closes "done" while the comparison it fed was never made — so say explicitly which numbers are
raw and not yet a verdict. End with one recommended next step and why (prefer the one that feeds a
pending decision and has no external blocker), then ask.

If the user proposes shipping before the card closes, do not answer "wait for review"
reflexively. Look up which pre-declared gates control *that* artifact. Recompute each one from the
raw results file yourself: completion status, max step time, win counts under the declared
seat-dedupe rule, and per-opponent regression. Hash the file you are handing over against the
copy that was measured. If those gates pass, recommend shipping now, with the post-ship criteria
and the control slot that must stay. The still-running gates keep deciding only the artifacts
they were declared for.
The same applies to "is there anything to submit?" while a push card is still writing docs: the
remote job often finishes long before the card closes. Run `kernels status <slug>` and read the
downloaded log's gate lines (ERRORS, WEIGHTS md5, PARITY, G, EST_SEC) yourself. Then give the user
two labelled options, "final check, then submit" (recommended if the agreed condition said so) or
"submit now", and say which exact words trigger each.

## Completion notices for work already reported

**A background-process completion notice is not a new request.** When a job you already harvested
finishes, reply in 1–3 lines: which job it was, that its numbers are already in the last report
(or what changed if the final count differs), and what is still running. Do not re-report. The
same holds for a late "handed off for review" or "completed" notice about a card whose approval
you already relayed.
