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
- There is no global `--board` flag; switch with `hermes kanban boards switch <slug>`.
- `comment` and `block` take the text as a **positional** argument, not `--body`/`--reason`.
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
- `create` has no `--board`; attach the card with `--project <slug>`. An unknown flag makes the
  command print usage and exit **without creating anything**, so a pipeline that greps the
  output for an id silently yields an empty variable and every follow-up call then targets
  nothing. Create with `--json`, parse the id from that, and assert it is non-empty before
  chaining `notify-subscribe` or any other command onto it.
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

### 6. Verify before relaying — worker summaries are claims, not results

Never forward a worker's summary as fact. Reproduce the load-bearing numbers yourself from
the artifacts, then report in your own words. See `references/verifying-worker-results.md`
for the verification gates and the statistics trap that invalidates most benchmark verdicts.

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

If a conclusion recorded earlier in the same session was later refuted by your own analysis,
correct it in the handoff and say it was corrected. Carrying a superseded framing into the
handoff is how a wrong cause outlives the session that disproved it.

## Recovery

- Stop a running card: `hermes kanban reclaim <id>` releases the claim.
- **A worker block for a resource limit is usually a design defect in the card, not a
  permissions question.** When a card stops on disk, quota, or rate limits, the worker asks
  which resource it may consume; answering that question directly ("delete these directories")
  authorises destruction of the user's data to keep a bad plan running. Re-scope the work
  instead so the limit stops binding — stream and discard rather than accumulate, sample
  rather than exhaust — then `comment` the new design and `unblock`. Ask what the card
  actually needs to keep; it is often a tiny fraction of what it was collecting.
  Deleting the user's accumulated artifacts is never the orchestrator's call to make on its
  own, and never the orchestrator's hands either.
- **Your own blocks count toward the card's failure limit.** Blocking to change instructions
  is indistinguishable, to the dispatcher, from a worker failing repeatedly; enough of them
  route a card whose work was fine into `triage` and make the board record it against the
  assignee. To redirect a card that is *not* mid-run, edit it with `comment` and let the
  dispatcher re-claim it — reserve `block` for genuinely halting work.
- `reclaim` followed immediately by `block`, or a short `unblock`/`block` cycle, trips the
  loop detector and dumps the card into `triage`.
- **`triage` is a terminal-ish parking state with no path back.** `promote` rejects it
  ("promote only applies to 'todo' or 'blocked'"), `unblock` rejects it ("not
  blocked/scheduled"), and `complete` rejects it ("unknown id or terminal state"). The only
  exit is `hermes kanban archive <id>`. When the deliverable is already produced and
  verified, archive with a comment recording the verification and why the card ended up
  there; do not fight the state machine to force a `done`.
- A parent card blocked or in review keeps children in `todo`; completing or unlinking the
  parent is what promotes them to `ready`.
- Close a card that met its stated goal even if the outcome was disappointing. A spec that
  was implemented faithfully but underperformed is a spec failure, not a worker failure, and
  leaving it open records it against the wrong party. Put the performance question on a new card.

## References

- `references/verifying-worker-results.md` — verification gates before relaying any worker
  summary, the sample-size trap, and designing acceptance criteria under noise.
- `references/measuring-what-matters.md` — checking the benchmark maps to the real
  objective, detecting drift in a recorded evaluation pool, discrimination-testing a
  proposed cause **and then falsification-testing it before believing it**, guarding
  segments you already win, building sub-group classifiers, pivoting to leader-profiling
  when every candidate in the current layer is rejected, and why borrowed parameters need
  their supporting subsystems.
