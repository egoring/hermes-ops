---
name: kanban-work-delegation
description: "Use when delegating, steering, or verifying work on a Hermes kanban board."
version: 1.3.0
license: MIT
metadata:
  hermes:
    tags: [kanban, delegation, multi-agent, orchestration, code-review, verification, benchmarking, attribution]
---

# Delegating work through a Hermes kanban board

For orchestrator/reviewer profiles that create cards, steer workers, and accept or
reject their output. Worker profiles execute; the orchestrator designs, instructs,
and verifies.

## Role boundary (always on)

**The orchestrator does not write or edit the files the worker was assigned.** Analysis,
design, card authoring, and verification only. Reading files, running read-only commands,
and recomputing numbers are all in scope; `cp`, edits, reverts, and writes to the
workspace are not.

Running the worker's benchmark or analysis script yourself to check its numbers is
verification, not authorship — do it.

The line is **not** simply "mutating the workspace". Recomputing a stated result is yours;
**mechanical exploratory search is the worker's even when it is entirely read-only.** Probing
API endpoint variants to find one that responds, trying credential shapes, and grinding
through candidate paths are cheap-model work by definition — reaching for them because you
have the shell open is the same violation as editing a file, and the user will read it that
way. Ask "is this discovering *what* to do, or executing a known procedure?"; only the first
is yours.

When you have already over-reached and produced useful findings, **hand them to the worker
rather than discarding them** — put the attempted variants and their exact failure codes on
the card as a do-not-retry list. Withholding them to stay inside the boundary just makes the
worker repeat the same dead ends.

When a mid-task correction arrives ("revert that", "do it as a new file instead"), the
correct move is to put the new instruction on the card and let the assigned worker carry
it out — doing it yourself because it is faster is the exact failure. A stale card left
running under the old instruction is not an excuse to grab the keyboard; block or comment
the card first, then wait.

The boundary breaks under **urgency**, not under ambiguity: a worker is mid-run against
superseded instructions, and undoing its output looks like damage control rather than
authorship. It is not. Reverting, `cp`-ing a baseline back, and deleting a stray artifact
are all worker actions; the orchestrator's move is to halt the run and re-instruct. If you
catch yourself reaching for a write because "the worker is about to make it worse", that is
precisely the moment the rule exists for.

The same applies to **cleanup**: deleting a leftover file, tidying a stray copy, or fixing a
misreported deletion. Detecting it is verification and is yours; performing it is the
worker's, and goes on the card as a task with the `ls`/`diff` evidence you used to find it.

This boundary is a standing user expectation, not a stylistic preference — restate it in
plain terms when corrected, own the specific violation rather than apologizing broadly, and
resume as instructed without re-litigating it. Expect the correction to be terse and to
assume you already know the rule ("you do analysis and design, the worker does the work");
treat a repeat correction as evidence the rule was not actually internalised the first time,
not as a new instruction.

## Procedure

### 1. Learn the board before creating anything

```bash
hermes kanban boards            # current board + counts
hermes kanban ls                # existing cards; NEVER recreate an existing graph
hermes kanban assignees         # which profiles exist and their on-disk status
hermes kanban show <task_id>    # body, comments, events, runs, latest summary
```

CLI shape traps (they fail loudly but waste a round-trip each):
- Target a board per command with the group-level flag placed **before** the subcommand:
  `hermes kanban --board <slug> create|ls|show|request-review ...`. `create` itself has no
  `--board` option, so `hermes kanban create --board x` fails. `boards switch <slug>` changes
  the default for every later call (including other sessions) — prefer the explicit flag.
- New project/competition → new board: `hermes kanban boards create <slug> --name ...`. Run
  `hermes kanban boards set-default-workdir <slug> <abs dir>` yourself from the interactive
  session once the folder exists. Worker contexts cannot run it; they are refused with
  "cannot mutate Kanban tasks via the CLI". When
  that first card creates the project folder itself, set its `--workspace dir:` to the
  existing parent directory (so the parent AGENTS.md still loads) and put the new folder path
  in the body; a `dir:` that does not exist yet is not a valid workspace.
- `comment`, `block` and `request-changes` take the text as a **positional** argument, not
  `--body`/`--reason` (`request-changes <id> "<reason>"`).
  Quote the whole body: `hermes kanban comment <id> "$(cat file.md)" --author <profile>`.
  **Give every card body its own uniquely-named file and re-read it after writing, before
  creating the card.** A generic scratch path (`/tmp/card.md`, `/tmp/body.md`) reused across
  sessions can still hold a previous card's spec, and `$(cat ...)` will ship that stale content
  as the new card's body -- the title looks right, the worker correctly implements the wrong
  task, and the run is wasted. Name the file after the card, then `grep` it for two or three
  terms that must appear and one that must not before calling `create`.
  **Never pass a multi-line body inside double quotes directly** — backticks and `$(...)` in
  the text are evaluated by the shell, so code-fenced paths and commands get executed and are
  silently replaced by their output or by nothing. The comment posts and looks fine on the
  board while lines are missing. Write the body to a file and pass `"$(cat file)"`, or drop
  backticks entirely. After posting a long instruction, re-read it with
  `hermes kanban show <id>` and confirm the paths survived.
- `create --workspace` wants `dir:/abs/path` (or `scratch` / `worktree:<path>`).
- `--project <slug>` links a card to a Hermes project (worktree anchoring); it is not a board
  selector. An unknown flag makes the
  command print usage and exit **without creating anything**, so a pipeline that greps the
  output for an id silently yields an empty variable and every follow-up call then targets
  nothing. Create with `--json`, parse the id from that, and assert it is non-empty before
  chaining `notify-subscribe` or any other command onto it.
- **Chain cards that touch the same file with `--parent`** (doc-record card → card A →
  card B) so they run in order instead of racing on one work log. Create in dependency order,
  parse each id from `--json`, and substitute it into later bodies (e.g. `sed` a placeholder
  in the next body file, then `grep` that the id landed) before creating them.
- **A card that must wait for the user's approval is created blocked, not chained and
  blocked later**: `create ... --parent <prev> --initial-status blocked --json`, then
  comment the user's gate condition ("start only after the user reviews A/B results").
  `block` on a `todo` card is refused ("cannot block"), and a plain `--parent` chain
  auto-promotes the card the moment the parent completes. If one was already created
  unblocked, archive it before it starts, recreate it blocked, and move the subscription.
- The subcommand is `notify-subscribe`, not `subscribe`, and it wants `--platform` plus
  `--chat-id` / `--thread-id` as separate flags — a bare `--chat` is rejected as ambiguous.

### 2. Route model tier by task kind

Check `model.default` in each profile's `config.yaml` before overriding anything — tiers
are usually already split. Put judgment-heavy cards (design, attribution, redefining
acceptance criteria) on the stronger model and mechanical cards (implement-to-spec, run
the bench) on the cheaper one. Downgrading the design card is a false economy: a bad
parameter choice there forces a full re-run of the implement+benchmark cycle, which costs
more than the model difference. Per-card override: `hermes kanban set-model <id> --model <m>`.

### 3. Write the card so it cannot be satisfied by prose

Every card body needs:
- **Background with the real numbers**, so the worker does not re-derive them.
- **Numbered deliverables**, each with the artifact path it must produce.
- **Exact expected values** where they are already known, plus "if this does not reproduce,
  the implementation is wrong — stop and report". A self-check the worker cannot fudge is
  worth more than any amount of instruction.
- **A ban list**: approaches already measured and rejected, with where the rejection is
  recorded. Without it workers re-propose dead ends.
- **Explicit permission to conclude "no improvement found"**. Without this line a worker
  manufactures a recommendation to look productive — the same failure mode that produced
  the bad input in the first place.
- **A ban on modifying the file under study.** Analysis cards should name the artifact as
  read-only and require new files for anything the worker produces, so the measurement
  baseline survives the card. State where a pristine baseline copy lives so scope can be
  checked with one `diff`.
- **Forbid moving the goalposts**: report shortfalls as numbers, never relax the criterion.
  The same applies to you: when a fix card re-implements a decision rule the user already
  approved (a verdict function, a gate), copy that rule verbatim. Adding a condition while
  "tidying" it changes the verdict the run prints, and you then have to explain why the
  printed verdict disagrees with the approved rule.
- **State git expectations as two explicit yes/no lines** ("local commit: YES, message
  `<msg>`; push: NO") and put `git status` empty + the commit hash in the completion
  criteria. "Commit locally, push forbidden" written as one phrase gets read as "no git",
  and the round trip costs a full review cycle.
- **Size every absolute threshold to the sample before writing it.** A floor like "Hit@5 ≥
  0.70" on n≈50 is inside the binomial noise of a result a few items short; prefer a paired
  criterion against the previous version or baseline, or write the floor with its CI. A
  floor missed only by noise is a spec defect: approve the faithful implementation, record
  the miss, and raise the threshold question to the user instead of bouncing the worker.
- **Compute a metric's no-op and oracle values before writing a delta threshold on it,
  and check that criteria can all hold at once.** A similarity score where "do nothing"
  already reaches 0.96 cannot rise by 0.05; a success floor plus a per-item step cap can be
  jointly unreachable on the real size distribution. Ask the card to print both reference
  values first. When the worker flags such a conflict at review, decide each flagged item in
  the approval comment (replacement metric or criterion, with its numbers) so the next card
  inherits the corrected rule, rather than bouncing a faithful implementation.
- **For public-facing text edits, ship the exact replacement sentences and an explicit
  do-not-touch list.** Workers "improve" wording and replace every occurrence of a value;
  name the lines to change, the look-alike occurrences to leave (e.g. measurement tables),
  and make the diff hunk count a completion criterion.
- **For remote-history rewrites (force push), require a backup and remote verification**:
  `git bundle create <path> --all` before touching anything, `--force-with-lease`, then
  `git ls-remote` sha == local HEAD and an API read-back of what the user will see. Tell the
  user about the force push and the backup path when you hand the card off.
- **For any push card, anchor to the remote as fetched at run time, not a SHA from the chat.**
  The user edits public repos on the web between cards. A card that hard-codes the base SHA,
  the original line text, or an absolute commit count gets a non-fast-forward rejection.
  Make the card `git fetch` and rebase onto `origin/<branch>`. Treat the user's web commit as
  intentional: keep it and resolve conflicts in its favour. Write the criteria relative to
  that head ("diff since origin/master = these files only", "origin/master is an ancestor of
  HEAD"), not as total commit counts.

### 4. Resolve contradictions you introduce

If a card forbids touching code but its analysis requires toggling behavior, the worker is
stuck between two orders and will either block or guess. Post a comment that names the
contradiction and carves the narrow exception ("refactor to extract toggles only; defaults
must reproduce current numbers exactly"). State that the comment outranks the body.

A comment on a **running** card may not reach that run's context — it is durable on the
board but not guaranteed to be injected mid-flight. Post it anyway (it governs any re-run),
and treat the current run's output as possibly written against the old instructions.

### 5. Route notifications through yourself

```bash
hermes kanban notify-subscribe <id> --platform <p> --chat-id <id> --thread-id <id> \
  --chat-type thread --notifier-profile <orchestrator> --delivery-mode wake
```

`--delivery-mode` choices: `notify` pastes the worker's own summary into the chat;
`wake` wakes the orchestrator to read the board and speak in its own voice; `notify+wake`
does both. **Use `wake` when the user should hear one voice** — `notify+wake` leaks the
worker's raw summary and looks like the worker is answering directly. Re-running
`notify-subscribe` on an existing subscription updates it in place.

To watch another board's card from this thread, subscribe to it here. Remove it with
`notify-unsubscribe <id> --platform <p> --chat-id <id> --thread-id <id>` once the
dependency is gone. Otherwise its events keep landing in the wrong conversation.

**Live progress in the chat for a long worker job.** "Can I watch it here" means periodic
aggregates, not a stream. Stream the raw work only if it contains no restricted content
and would not flood the thread; neither is usually true. Recipe:
- The card makes the worker keep a `progress.json` with fixed field names: done/total,
  batches, failures, ISO start and last-update times, running cost, per-category rates.
  Post the field list as a card comment too.
- Create a `cronjob_manage` job with `no_agent=true`, a script in the profile's `scripts/`,
  `deliver=<platform>:<chat>:<thread>`, `failure_deliver=local`, every 30 min. The script
  prints one summary line with an ETA. It prints nothing when unchanged or not started, and
  warns **once** when progress stalls. Test it on a fake progress file first: fresh,
  unchanged and stalled cases.
- It costs no tokens and never sends restricted text (e.g. competition data).
- **Respect the user's quiet hours (23:00–09:00 local).** No-agent alert scripts must not
  print during that window. Route their output through a shared helper
  (`scripts/quiet_hours.py` `emit(msgs, name)` in the profile). Overnight it appends to a
  hold file and prints nothing. The first run after 09:00 prints "held overnight: N" and
  then the held lines. Test it on 22/23/00/08/09 o'clock timestamps. Your own @-mentions
  follow the same window: overnight wake-ups get a short reply with no tag. Tell the user
  two things. Card-event wake-ups still post to the thread overnight; muting the thread to
  mentions-only silences them. A held duplicate-GPU alert costs up to one session of
  quota, so offer to exempt that single alert class.
- `hermes cron create --script` takes a script name only, with no arguments. To reuse a
  parameterised watcher (slug, state file, label, warn hours), have the card add a small
  wrapper script in the profile's `scripts/`. The wrapper imports the watcher's `check()`,
  calls it with fixed arguments, and prints through `emit()`. Before you register it, test
  it with a fake `status_fn` and a temporary state file. Then run it once for real: while
  the job is still running it must print nothing.
- Pause a progress cron once its job is finished (`hermes cron pause <id>`), and do not leave
  it posting "no change".

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

### 5b. Pause and resume on the user's word

"Pause this until X is done" → `block <id> "<reason + what exists + resume instructions>"
--kind needs_input`, then confirm with `ps` that the worker process exited. If the user
later says "wait for my approval", that **replaces** the automatic condition. Comment the
change on the card, drop any cross-board subscription you added for the old trigger, and
do not unblock when X finishes. On resume, first post a comment listing the artifacts that
already exist and must not be regenerated (frozen folds, uploaded datasets). Then unblock.

**"Fix it, then final-check, then proceed" means the fix card stops before the side effect.**
When a fix card also performs the irreversible step (push a GPU run, submit, publish), the
user's "check first" request arrives after it already happened. Split it: fix + CPU proof
in one card, the push/launch in a separate step gated on the check. When the user has
already approved the run ("fix, check, then run"), create the launch card after the check
returns go. Chain it with `--parent <last fix card>`, so your approval of that fix starts
the launch with no extra round trip. Give the launch card its own pre-push re-checks and a
one-push cap. If you already bundled
them, say so plainly and give the user the stop path (e.g. Cancel in the platform web UI,
since the CLI has no cancel) together with the rule you will apply if the run starts
before the check returns.

"Stop this" (for good) is not a pause.
- `block` with the user's decision, the list of kept artifacts, and "do not resume".
- `block` does not stop a live run. Kill the worker pid **and** any child process it
  spawned, then confirm with `ps`.
- Check the cards that depend on it. `hermes kanban unlink <parent> <child>` so they do not
  wait forever, and comment what they must now mark "n/a".

### 6. Verify before relaying — worker summaries are claims, not results

Never forward a worker's summary as fact. Reproduce the load-bearing numbers yourself from
the artifacts, then report in your own words. See `references/verifying-worker-results.md`
for the verification gates and the statistics trap that invalidates most benchmark verdicts.

**Two reviewers, one decision.** A `request-review` also dispatches a separate reviewer run
on the card while you may be reviewing it from the chat. If both of you make a design
decision (a resolution, a threshold), they can disagree, and the child card starts on
whichever one landed first. After the dispatched review completes, read its summary before
you report. On a conflict, pick one by the scarce resource (GPU quota, deadline). Then
comment the correction on any child card that already started, and check that nothing was
pushed under the losing value. Tell the user plainly that the two reviews disagreed and
which one you kept.

Before re-running a long check yourself (an offline dry-run takes minutes), run `ps` for
the dispatched review's process. If it is already running the same check, do not start a
second copy. Two copies compete for the CPU, and a foreground shell call can hit its
timeout. Wait for the dispatched verdict instead, and reproduce its claim afterwards with
a cheap targeted probe (e.g. a tiny fixture for the one function in question).

While that dispatched review run is live, `hermes kanban complete` from the chat is refused
("a live worker is running it"). Post your verdict as a `comment` (severity-tagged, with the
numbers you reproduced) and let the dispatched run close the card. Do not `--force` or
`reclaim` to get your own approval in: that kills the run mid-review and leaves the card
with a crashed run and two half-verdicts.
`request-changes` from the chat is refused the other way round: it works only inside an
active review run ("task is not in an active review run"), so a card sitting in `review`
before the reviewer run starts cannot be bounced from the chat. Post the 🔴 as a comment
that says "bounce this in the review run", with the exact fix and any "do not re-run the
side effect (no second push)" line. If the missing item is separable from an
irreversible step the card already did, have it moved to its own small card rather than
re-running the original body.

State residual weakness even when every gate passes — a criterion cleared by a hair, or a
confidence interval still spanning zero, belongs in the report next to the PASS.

Verifying that a result is *real* is only half the job; also check that the quantity being
optimized is the one that moves the user's actual objective, that the evaluation pool still
describes the current environment, and that any stated cause survives a discrimination test.
See `references/measuring-what-matters.md` — a technically flawless benchmark aimed at the
wrong metric, or averaged over a population that has since shifted, produces confident,
worthless work.

When a production metric moves sharply while the offline benchmark still looks fine, trust
the production signal and check the benchmark pool for drift before proposing any fix.

**Also verify file-operation claims by listing, not by reading the summary.** "Deleted X"
is routinely reported when the file was overwritten, moved, or left in place; one `ls` or
`diff -q` settles it, and an unverified file claim is the kind that turns into a real
accident on the next card.

**Read a report card's full result, not the truncated summary.** `hermes kanban show`
cuts a long `kanban_complete` summary mid-sentence and drops its metadata. For a
final-check or analysis card, read the worker's own record: open
`~/.hermes/profiles/<worker>/state.db` read-only (`sqlite3` URI `?mode=ro`), table
`messages`, the last assistant row of that session whose `tool_calls` holds
`kanban_complete`. Its `metadata` carries the per-criterion verdicts, defects and scripts.
Relay from that, and say which of your earlier claims it overturned.

**Attribute every recommendation to its source.** When a second-opinion or final-check
report comes back, keep three things apart in the reply: the checker's own one-line advice
(quote its "advisory" field), your own recommendation, and anything you derived from the
checker's findings but the checker did not say. This user asks "is that the checker's
recommendation too?" when they blur. If they differ, say so and offer to put your variant
in front of the checker on the next check. Because he weighs the checker's view, ask for it
explicitly in the check card: "for each question give your own judgment and
recommendation (advisory), say where you disagree with the reviewer and why with numbers,
and end with one line `checker advisory: <choice>, reason = <one line>`".

### 7. Let the human approve side effects

When a card blocks for approval on a change with real consequences, present the verified
findings and recommendation but do not `unblock` unilaterally. After `unblock` the card
returns to `ready` and the dispatcher **re-claims it within seconds** — so finish the
conversation about whether it should run before unblocking, not after.

In a group chat, hand a decision back by **@-mentioning the user** rather than leaving the
question in prose; an unaddressed question in a busy thread reads as narration and stalls.
Say up front which classes of thing you will decide alone (re-instructing a worker, rejecting
an unverified result, technical course corrections) and which will always come back to them
(irreversible side effects, deployments, anything consuming a limited resource), then hold to
that split.

Slots, quotas, and publish targets are limited resources: recommend, quantify the expected
gain on the current regime, and let the user spend them.

**Write a user decision into the project work log in the turn it is made.** When he relaxes
a criterion or a standing rule (accepting a missed floor, dropping a one-shot held-out),
open a small helper card that appends a `user decision (override): <what>, basis: <numbers,
card>` section verbatim and commits it. A decision recorded only in a card comment is
invisible to the next audit and gets flagged as a rule violation.

**Re-read the gate you just approved before declaring the work done.** A contamination or
safety guard can pass its own tests and still fail open on a missing input (e.g. a
reference file absent → a check silently degrades to a weaker mode and exits 0). After
approving, run the guard once with each of its inputs removed or truncated; a fail-open
path is a 🔴 and goes to a follow-up card at once. When writing the bounce reason, make the
required behaviours consistent with each other ("union, never replace" and "must exit 1"
cannot both apply to the same input).

**Announce every card you create in the same chat reply that reports the review.** A
follow-up fix card opened while reviewing (e.g. a defect found in the worker's tooling)
is a decision the user did not see. Its later "handed off for review" notification then
arrives as a surprise and needs an apology. State its id, why it exists, and whether it
changes any already-reported result.

### Hold licence and attribution requirements even when told to drop them

"Don't bother with the attribution" is a cost-saving instruction, not an informed waiver, and
it is one of the few places to keep a requirement the user waved off. Keep the notices, put
the obligation in the card so the worker preserves them too, and give the reason in one line:
the licence requires it, the output is publicly inspectable and similarity-checked, and the
cost is a few comment lines. Note when the ecosystem itself normalises it — borrowed code
that already carries a long credit chain is evidence retention is expected, not optional.

The general shape: when a shortcut trades a compliance or safety property for minor
convenience, say plainly which property is at stake and that you are keeping it, then carry
on with the rest of the request rather than re-opening the debate.

## Closing out a session

When the user signals wrap-up ("세션정리", "summarize for next time", "hand this off"),
write a handoff document into the project's own docs directory rather than only answering in
chat. Structure that survives the context gap:

1. **Headline diagnosis** in one or two lines.
2. **Numbers you personally reproduced**, marked as such — distinguish them from worker
   claims you relayed.
3. **Artifacts produced**, with paths, hashes, and current state (merged / awaiting upload /
   experimental).
4. **Methodology lessons** — sample sizes that proved inadequate, classifiers that worked,
   replay fidelity you measured.
5. **Ranked next steps**, each with the identifier a future session needs to find the data
   again (group hash, file path, id list).
6. **A rejected list** with reasons and sources, so the next session does not re-propose
   what was already measured and killed.
7. **Board state and operational gotchas** hit during the session.

Attach the file to the chat as well as writing it — on platforms that render attachments the
user wants the downloadable artifact, not only the prose.

When the user asks for "everything so far as an md file" mid-project, build it from fresh
primary sources in the same turn (submission CSV, LB CSV, `git log`, zip sha256/size,
CHANGES files, result summaries, cron list, board `ls`), not from memory or the compacted
summary. Put the timestamp of the snapshot in the header, mark estimates as such, and
include a table of your own corrected claims and one of the final checks run. Write it
under the profile's cache (not the repo) and attach it with `MEDIA:`; committing it into
the project is a separate decision for after the fact-check. For a competition, use these
sections:
- submission table: ref, UTC date, config, LB, pre-registered verdict
- completed phases, with measured numbers only
- in progress, with live counts
- decisions pending, each with your recommendation
- ops state: quota, slots left today, active crons, live cards
- risks and unverified items
- file locations

Re-poll the scored list right before writing: a score that lands while you write changes
the pending decisions. Lead the reply with it, and say which recommendation it weakens.
If he asks for it to be
checked, the check card is a pure fact-audit: every number traced to its source file,
mismatches returned as line number + doc value + source value + replacement text, and the
checker edits nothing.

Writing and revising that summary doc:
- **State each threshold once and derive every restatement from it.** A summary that says
  "±3 tasks are distinguishable" in one section and computes power 0.55 for +3 in another
  contradicts itself; write the computed section first and copy its conclusion verbatim.
  Give every quoted outside number its source (notebook slug, thread id, "participant
  claim" vs staff reply) and give every comparison its baseline ("−3 vs v6", not a bare "−8").
- **When state changes after the snapshot time** (a cron registered, a card approved),
  comment on the running check card that it happened after the snapshot, so the checker
  reports it as "changed since" instead of as an error.
- **Treat a checker's "unsupported" as a prompt to re-check, not to delete.** Open the
  primary source yourself; if it confirms the claim, keep it with the citation (a staff
  reply quoted verbatim), and delete only what nothing supports.
- **Revise as a versioned file**: copy the checked version to `<name>_v1.md`, mark the
  header "corrected v2 (check <card id>, N items)", add the doc itself to the corrections
  table, re-attach with `MEDIA:`, and list the fixes item by item in the reply, plus what
  the checker could not verify. A fix that belongs in the repo (a missing record) goes to
  a worker card in the same turn.

**"Didn't we decide X earlier?" — check the record before you answer.** Search the session
history: the profile's `state.db`, table `messages`, filtered by session_id and a keyword,
opened read-only. Also grep the user's shared documents and the project docs. Then quote
what was actually said. If nothing was decided, say so plainly. Give the reason the
premise doesn't hold (e.g. the data step uses no GPU at all), and ask whether the decision
was made in another chat. Agreeing from a vague memory plants a false decision in the plan.

If a conclusion recorded earlier in the same session was later refuted by your own analysis,
correct it in the handoff and say it was corrected. Carrying a superseded framing into the
handoff is how a wrong cause outlives the session that disproved it.

## Recovery

Rules that apply every time a card misbehaves. Recipes and state-machine details are in
`references/recovery.md`.

- **A `crashed` run is not proof that the worker is dead.** Before you report a crash or
  write retry instructions, run `ps -axo pid,ppid,etime,command | grep <task_id>` and
  `kill -TERM` any stale run. Then read what each run already did (push, upload) from the
  worker's `state.db` before you tell the user how many of anything exist.
- **Headless workers cannot pass approvals.** Force pushes, protected files such as
  `AGENTS.md`, and `pip install` all block. Design the card around that (draft + user `cp`,
  local result + interactive push, numpy reimplementation). Never route around the security
  scan.
  - Ask for the `cp` only after the last card that edits the draft is approved; otherwise the
    user installs a stale file. Leave the parent blocked meanwhile, and `unlink` it from the
    editing child so the child is not stuck waiting on it.
  - If the user tells you to do the copy yourself, first check `diff` shows only the
    intended lines, back up the current file (`AGENTS.md.bak_<date>_<reason>`), then copy,
    verify with `cmp` and the ignore check, comment it on the card, and complete the blocked
    parent.
- **Scarce remote quota (GPU hours): guard on two layers.** Put a pre-push checklist comment
  on every card and run a `no_agent` push watchdog cron. Cards that wait on a remote job use
  short status calls, never long foreground wait loops.
- **A resource-limit block is a card-design defect.** Re-scope so the limit stops binding;
  never authorise deleting the user's data to keep a bad plan running.
- **Your own blocks count toward the failure limit.** Redirect idle cards with `comment`,
  not `block`. Avoid `reclaim`→`block` and quick `unblock`/`block` cycles; `triage` can only
  be left through `archive`. A card in `triage` can also be picked up by the auto-decomposer
  and re-promoted with a rewritten title and body. The worker then blocks again for the
  same missing decision, and you get a second triage notification. Once a card lands in
  `triage`, archive it with a comment that records its results and why it stopped. Carry
  the work on in a new card that is created only after the user decides.
  The decomposer can also split a blocked card into several new child cards, and one of
  them starts running at once. That repeats side effects the parent was capped at, such as
  a second push. Right after any block or triage event, run `ls`. Archive every
  `auto-decomposer` card, using `show` → `created ... by auto-decomposer` to identify
  them. Kill the live worker pid of each, then confirm with `ps` and the remote status that
  nothing ran. To prevent it, write "do not decompose this card into sub-cards" in the
  body of every card that has an irreversible step.
- **Run `ls` right before `create`.** A parallel session of your own profile can create a
  card for the same purpose at the same moment. Two workers then edit the same files and
  overwrite each other's work. Keep the card that started first, archive the other with a
  comment pointing to the survivor, and kill its worker.
- **Check the side effect before killing a run you think is in the wrong mode.** Unblocking a
  card that was blocked from `review` returns it to `review`; after reassigning it to the
  worker, the dispatcher starts the worker with the review skill, and that run can still
  execute the PUSH_OK step. Before `kill`, read the remote state (`<platform-cli> jobs list
  --mine`, `kernels status`, submissions list). If the side effect already happened, do not
  kill. If you already did, comment "already pushed at <time>, do NOT push again; only wait,
  collect and verify" before the next run claims it.
- Close a card that met its stated goal even if the result disappointed; put the performance
  question on a new card.

## References

- `references/recovery.md` — headless approval workarounds, crashed-but-alive forensics and
  the scarce-quota guard, resource-limit re-scoping, and dispatcher state-machine traps
  (`triage`, failure limit, parent/child promotion).
- `references/verifying-worker-results.md` — verification gates before relaying any worker
  summary, the sample-size trap, and designing acceptance criteria under noise.
- `references/measuring-what-matters.md` — checking the benchmark maps to the real
  objective, detecting drift in a recorded evaluation pool, discrimination-testing a
  proposed cause **and then falsification-testing it before believing it**, guarding
  segments you already win, building sub-group classifiers, pivoting to leader-profiling
  when every candidate in the current layer is rejected, and why borrowed parameters need
  their supporting subsystems.
