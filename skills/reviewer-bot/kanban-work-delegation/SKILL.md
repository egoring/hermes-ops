---
name: kanban-work-delegation
description: "Use when delegating, steering, auditing Hermes kanban work."
version: 1.3.0
license: MIT
metadata:
  hermes:
    tags: [kanban, delegation, multi-agent, orchestration, code-review, verification, benchmarking, attribution]
---

# Delegating work through a Hermes kanban board

For orchestrator/reviewer profiles: workers execute; the orchestrator designs, instructs, steers and verifies.

## Role boundary (always on)

Watchers and role-audit recipe: `references/monitoring-and-audit.md`.

**The orchestrator does not write or edit the files the worker was assigned.** Analysis, design, card authoring and verification only; reading, read-only commands and recomputing are in scope, while `cp`, edits, reverts and workspace writes are not.

Running the worker's benchmark or analysis script yourself is verification, not authorship — do it. **Protected files (AGENTS.md, SOUL.md) are written only with `patch`/`write_file`, never with `open(...).write` in `execute_code`.** The Python path skips the per-write approval, so the user loses the final check on the exact text even when they approved the change in chat. Routing: `references/card-inputs-and-routing.md`; protected/triage: `references/protected-files-and-triage.md`; waits/duplicates/queue re-ordering (SCHEDULED_UNTIL format, block→auto-decomposition, design-card duplicates, **link the new parent before unlinking the old** — the reverse order flips the child to `ready` and lets the dispatcher start it): `references/scheduling-and-duplicate-cards.md`.

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
Keep your verification commands strictly read-only. Do not tack an `rm -rf` of your own probe folder onto them. A recursive delete is approval-gated, so the whole command waits and then fails unrun, and the checks inside it are lost. Use fresh uniquely-named scratch folders instead of deleting old ones.
Before running a worker's tool in its "test mode" from the live repo, read where it writes its side files (backups, logs, state), not only its main target. A test-mode override that redirects only the target file still drops backups into the production folder, and a later production rollback restores the fake value. Copy the script into a scratch tree, or set every path override. If your probe already left files, report them and their contents on the card. A side effect your own probe created is the one cleanup you undo yourself, after checking the contents are your fake values.
For an undo/rollback feature (secret swap, config switch), probe the sequence, not one step: change key A three times, change key B once in between, then roll A back until it refuses. Expect each earlier A value in order, then an explicit "nothing left, file unchanged", with B untouched and the production backup folder listing identical before and after. A single change-then-rollback passes code that restores only the newest backup or crosses keys.

This boundary is a standing user expectation, not a stylistic preference — restate it in
plain terms when corrected, own the specific violation rather than apologizing broadly, and
resume as instructed without re-litigating it. Expect the correction to be terse and to
assume you already know the rule ("you do analysis and design, the worker does the work");
treat a repeat correction as evidence the rule was not actually internalised the first time,
not as a new instruction.

## Procedure

Each step keeps its always-on core here; the detail sits in the reference named on the step.
Load one with `skill_view(name="kanban-work-delegation", file_path="references/<file>.md")` when its condition applies — before acting, not after.

### 1. Learn the board before creating anything

```bash
hermes kanban boards            # current board + counts
hermes kanban ls                # existing cards; NEVER recreate an existing graph
hermes kanban assignees         # which profiles exist and their on-disk status
hermes kanban show <task_id>    # body, comments, events, runs, latest summary
```

Before any `create`, `link`/`unlink`, `edit`, `comment`, `block` or `schedule`, read
`references/board-cli-and-chaining.md`: CLI shape traps (group `--board` flag before the
subcommand, positional comment text, one uniquely-named body file per card, ids from `--json`),
chaining with `--parent`, inserting/re-ordering cards (link the new edge before unlinking the
old), cards gated on user approval, folding new requirements into queued bodies with `edit`, and
concurrent cards in one git repo.

### 2. Route model tier by task kind

Check `model.default` in each profile's `config.yaml` before overriding anything — tiers
are usually already split. Put judgment-heavy cards (design, attribution, redefining
acceptance criteria) on the stronger model and mechanical cards (implement-to-spec, run
the bench) on the cheaper one. Downgrading the design card is a false economy: a bad
parameter choice there forces a full re-run of the implement+benchmark cycle, which costs
more than the model difference. Per-card override: `hermes kanban set-model <id> --model <m>`.

Helper-bot vs coder-bot routing pitfalls: `references/worker-routing.md` and the Routing
section of `references/card-inputs-and-routing.md`.

### 3. Write the card so it cannot be satisfied by prose

Every card body needs real background numbers, numbered deliverables with artifact paths, exact
expected values with a stop-and-report self-check, a ban list, explicit permission to conclude
"no improvement found", and git expectations as two yes/no lines. The full checklist (detector
and allowlist specs, byte-identical baselines, thresholds sized to the sample, push/force-push
cards, verbatim insertions) is in `references/card-inputs-and-routing.md`; read it whenever you
write or re-scope a card body or a spec correction.

### 4. Resolve contradictions you introduce

If a card forbids touching code but its analysis requires toggling behavior, the worker is
stuck between two orders and will either block or guess. Post a comment that names the
contradiction and carves the narrow exception ("refactor to extract toggles only; defaults
must reproduce current numbers exactly"). State that the comment outranks the body.

A comment on a **running** card is normally injected into the live run as operator steering
(that is how a scope extension such as "also recommend alternatives" reaches a running
opinion card). It is still durable on the board for any re-run. When the result comes back,
check that it actually addressed the comment before relaying it.

### 5. Route notifications through yourself

Intermediate coder/helper cards: `--delivery-mode notify` (user cost rule 10/27). `wake` only for a
phase's final card, a card needing a user decision, and fable cards.

Subscription commands, `notify` vs `wake`, moving a project's alerts to a new thread, live-progress
crons and the user's quiet hours (23:00–09:00 local): `references/result-delivery.md`. ETAs,
"is this overloading the machine?" and your own status scripts: `references/monitoring-and-audit.md`.

### 5b. Pause and resume on the user's word

"Finish then stop", "do the next one", "pause until X", "stop this" (for good), taking over a
card another session stopped, and "fix, then final-check, then proceed" (the fix card stops
before the side effect): `references/pausing-and-sequencing.md`. Holding scheduled cards against
auto-wake: `references/park-scheduled-card.md` and `references/scheduling-and-duplicate-cards.md`.

### 6. Verify before relaying — worker summaries are claims, not results

Status-report sweep, helper-vs-coder routing for scripted collection, scraped-number bounds: `references/worker-output-checks.md`.

Never forward a worker's summary as fact. Reproduce the load-bearing numbers yourself from
the artifacts, then report in your own words. See `references/verifying-worker-results.md`
for the verification gates and the statistics trap that invalidates most benchmark verdicts.

**`request-changes` is only for a 🔴 rejection, never for "GO, next step".** Using it to
steer ("not a rejection, round 0/3") inflates the round counter, which makes the 3-round
cap meaningless and hides real rejections in the audit. Steer with `comment` + `unblock`,
or approve and open the next step as its own card.

Verifying that a result is *real* is only half the job; also check that the quantity being
optimized is the one that moves the user's actual objective, that the evaluation pool still
describes the current environment, and that any stated cause survives a discrimination test.
See `references/measuring-what-matters.md` — a technically flawless benchmark aimed at the
wrong metric, or averaged over a population that has since shifted, produces confident,
worthless work.

When a production metric moves sharply while the offline benchmark still looks fine, trust
the production signal and check the benchmark pool for drift before proposing any fix.

Read before relaying any worker or review result:
- `references/chat-comment-vs-running-review.md` — a dispatched review run is live or just
  finished: two reviewers on one decision, labelling a chat-side opinion as unofficial in the
  reply's first line, `complete`/`request-changes` from the chat, the 3-round cap.
- `references/verifying-worker-results.md` — judging by the pre-registered rule, file-operation
  claims, doc-correction grep counts, plus the verification gates and statistics.
- `references/worker-output-checks.md` — attributing recommendations to their source and
  scoping checker/opinion cards.

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
Before pitching a spend, grep the project AGENTS for a clause that classifies the case, such as a list of "things we do not use GPU for". If your pitch conflicts with it, say so in the pitch with the reason the situation changed. Then, if he approves, write `사용자 결정(override)` into the card body and the work-log step. A pitch that skips the clause gets approved unaware, and the next audit flags the spend as a rule breach.
When a spend needs a number only the user can see (remaining weekly quota on a page you cannot log into), create the spend card `--initial-status blocked`, comment the floor, and ask for the number with an @-tag. Once his number clears it, `unblock` at once if the rest is a parent gate: the card waits in `todo` and the parent's approval releases it. Holding it for your own re-check leaves a manual release nobody is woken for; post those checks as a pre-push comment.
**An approval holds only for the evidence it was given.** Suppose the user approves a spend ("추천대로 진행") and then asks a question before the cards exist. If your answer turns up evidence that weakens the plan, do not create the cards. Examples: forum measurements against the lever, or a peer consensus that matches your own negative smoke. Say the cards are on hold, and present the new evidence next to the approved plan. Ask again with an @-tag. Cards created on stale approval run before he has seen the counter-evidence.

Batching the user's hands-on checks, automated spending, conflicting official sources and
writing user decisions into the work log: `references/approvals-and-user-decisions.md`.
Probing guards, graders, detectors and privacy features before an approval opinion, blind-eval
leaks and spec corrections: `references/probing-guards-and-graders.md`.

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

On a wrap-up signal ("세션정리", "summarize for next time", "hand this off"), a mid-project
"everything so far as an md file", or "didn't we decide X earlier?", read
`references/closing-out-a-session.md` first: the handoff structure, `outbox/` + `MEDIA:` delivery,
fact-audit check cards and versioned revisions.

## Recovery

Rules that apply every time a card misbehaves. Recipes and state-machine details are in
`references/recovery.md`.

Read `references/recovery.md` whenever a card blocks, crashes, lands in `triage`, hits a quota,
or a notification looks stale. Always on:
- **Run `ls` right before `create`.** A parallel session of your own profile can create a
  card for the same purpose at the same moment. Two workers then edit the same files and
  overwrite each other's work. Keep the card that started first, archive the other with a
  comment pointing to the survivor, and kill its worker.
- Close a card that met its stated goal even if the result disappointed; put the performance
  question on a new card.

## References

- `references/recovery.md` — headless approval workarounds, crashed-but-alive forensics and
  the scarce-quota guard, resource-limit re-scoping, dispatcher state-machine traps
  (`triage`, failure limit, parent/child promotion), taking over a card another session
  stopped, and moving delivery to a new chat thread.
- `references/verifying-worker-results.md` — verification gates before relaying any worker
  summary, recounting a reported zero with a mechanical matcher, headroom of adopted caps,
  the sample-size trap, designing acceptance criteria under noise, and validating
  a post-hoc "this combination would have passed" idea on fresh, pre-registered data.
- `references/pipeline-health-audit.md` — answering "how can the bot/agent structure
  improve" or "how do we save tokens": SQL queries over `kanban.db` and `state.db`,
  crashed-but-alive forensics before quoting lost hours, a symptom → fix table, a
  token/cost audit with quality-neutral levers (cache TTL, compression threshold,
  notify vs wake), and an independent-opinion step before ranking fixes.
- `references/measuring-what-matters.md` — checking the benchmark maps to the real
  objective, detecting drift in a recorded evaluation pool, discrimination-testing a
  proposed cause **and then falsification-testing it before believing it**, guarding
  segments you already win, building sub-group classifiers, pivoting to leader-profiling
  when every candidate in the current layer is rejected, and why borrowed parameters need
  their supporting subsystems.
- `references/board-cli-and-chaining.md` — read before any board-mutating CLI call: flag
  placement, body files, `--json` ids, chaining, inserting/re-ordering, approval-gated cards,
  editing queued cards, concurrent cards in one repo.
- `references/card-inputs-and-routing.md` — read when writing or re-scoping a card body, a spec
  correction, or choosing a worker/model tier.
- `references/worker-routing.md` — read when choosing helper-bot vs coder-bot for a card.
- `references/result-delivery.md` — read when a result is pending for the user, or when setting
  up subscriptions, progress crons, quiet hours or moving alerts to a new thread.
- `references/monitoring-and-audit.md` — read when starting a watcher, quoting an ETA or machine
  load, reading a finished card's full result, or auditing whether roles held.
- `references/pausing-and-sequencing.md` — read when the user pauses, resumes or stops work, or
  a fix must be checked before its side effect.
- `references/pausing-and-review-timing.md` — read when pausing a `todo` card or posting a
  chat-side finding while a review run is in flight.
- `references/park-scheduled-card.md` — read when the user says "hold it until I tell you" about
  a card already parked with `SCHEDULED_UNTIL`.
- `references/scheduling-and-duplicate-cards.md` — read when a card waits on time or a remote
  job, when re-ordering a queue, or when a design card may spawn duplicates.
- `references/chat-comment-vs-running-review.md` — read whenever you review from the chat while a
  dispatched review run exists for the same card.
- `references/worker-output-checks.md` — read before a status report, relaying helper numbers,
  or relaying a checker/second-opinion report.
- `references/approvals-and-user-decisions.md` — read when a user decision, spend, quota or
  hands-on check is involved.
- `references/probing-guards-and-graders.md` — read before giving an approval opinion on a guard,
  grader, detector, privacy/access feature or blind evaluation.
- `references/protected-files-and-triage.md` — read before any AGENTS.md/SOUL.md/.hermes edit or
  when a card loops between block and triage.
- `references/closing-out-a-session.md` — read on a wrap-up or handoff request.
