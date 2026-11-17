---
name: kanban-orchestration
description: "Use when delegating work via Hermes kanban board."
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, multi-agent, delegation, review, verification]
---

# Kanban Orchestration (reviewer → coder)

For running work as an analysis/design profile that delegates implementation to a
coder profile via `hermes kanban`.

Stuck cards/refused transitions: `references/stuck-cards.md`. Live queue edits (insert/reorder on a serial host, review BLOCK overlapping a follow-up, parking without auto-wake, sqlite reads of run summaries/comments, artifact-not-sentinel checks): `references/queue-and-dependency-edits.md`. Stalled handoffs: `references/stall-watchdog.md`. wake vs notify cost: `references/notify-token-budget.md`. fable: `references/fable-handoff.md`. Numeric gates: `references/acceptance-gates.md`. Workers cannot mutate Kanban via the CLI (measurement scripts you run, temp boards, cards blocked on a user step): `references/worker-limits-and-test-boards.md`. Card-body footer (scratch is pruned at 24 h; don't keep it there): `templates/card-footer-review-loop.md`.

## Role boundary

**Never edit files yourself.** Not even a one-line revert or a cleanup `rm`. If a
file must change, that is a card for the coder profile — put the exact desired end
state in the card and let the worker do it. Touching files directly breaks the
separation the user relies on and makes the board history lie about who did what.

What you *may* run: read-only inspection (`diff`, `ls`, `grep`), and re-running the
worker's own verification scripts to check their numbers.

## Approval gates (irreversible or paid steps)

- **Submits, the remote platform pushes, paid-API spend, deletions and protected-file edits wait for the user's explicit word.** Record a conditional pre-approval on the card with its exact gates; bodies keep "worker submits 0"; "proceed" is not a submit instruction (`references/fable-handoff.md`).
- **Split a card whose later step needs push/submit approval** into a build card and a push card created after approval (`references/review-cli-quirks.md`).
- **Never tell a worker to bypass a security scan;** the user edits protected files (AGENTS.md) himself.
- **When `request-review --reviewer <self>` arrives, let the spawned reviewer run own the verdict.**
  **This applies doubly to any irreversible step in the review (a the remote platform submit).** The wake reaches the
  chat session while the board also spawns a reviewer run of the same profile, and both act. Once,
  both reviewed a pre-approved submit card and each submitted the same kernel version 12 s apart,
  burning the day's last slot. Submit only through a locked wrapper: it takes an exclusive `flock`,
  checks a local ledger (slug@version and the phase prefix) and a fresh submissions listing, writes
  the ledger line, and only then calls `submit`. Here that wrapper is `scripts/rsna_submit_once.py`;
  put its exact command line in every submit card and approval comment, and never hand-type a
  `competitions submit` from the chat while a reviewer run is live on that card.
  Wrapper rollout, live-chain edits, transform specs, cron cleanup: references/live-chains-specs-and-crons.md.

## Workflow at a glance

1. Pre-verify the premise, then write the design card and the coder card.
2. Subscribe in the user's current thread with the right delivery mode.
3. Park external waits with `schedule` + a release cron, never repeated `block`.
4. On completion/block: check the card, recompute from raw artifacts, pick a disposition.
5. Relay your own figures; decisions go to the user with options and an advisory pick.

## Verify every self-report

Worker summaries are claims, not facts. Before relaying a result:

- **Recompute headline numbers from the raw artifact** (pkl/json the worker left
  behind), not from its prose. Sign flips and dropped rows show up here.
- **Check a correspondence claim in both directions.** "Every refresh had a triggering event"
  does not prove "every event produced a refresh"; count the inputs that got no output too
  (per tab/per item, and where its log simply stops). A one-way check passed while one tab had
  silently died after a single error and missed most later events.
- **Before saying "🔴 none" on a pre-review, test the card's own completion criteria literally.**
  If a criterion says "commands copy-paste runnable", dry-trace each command against the live
  system; if it says "no regressions", look for failure paths (an error, a retry, a read failure)
  rather than only the happy-path numbers. Your "🔴 none" comment steers the review run, so a
  premature one costs a retraction and a round.
- **`diff` the files** against a known-good baseline to confirm the change is
  exactly what was claimed and nothing else rode along.
- **Confirm claimed deletions with `ls`.** A worker once reported "deleted X" when
  it had actually overwritten X with the original content — the file was still there.
- Check that a claimed "no-op default" really reproduces the baseline numbers exactly.
- **Discord pre-checks report what you verified; they do not dictate the verdict.** Comment the
  numbers you recomputed and which FAILs are spec/measurement artifacts. Do not write "approve" or
  "do not send back" to the review worker. Its independent pass is the second look that catches
  defects you missed, and a pre-emptive "no 🔴" told to the user has to be retracted when it does.
  Tell the user "pending the review verdict" until the review run lands.
- **Read helper-bot text edits back before relaying them.** A Haiku helper transcribing Korean prose substituted look-alike words that reversed meaning ("contaminates" became "raises") and garbled others. For verbatim doc additions, `tail` the file and grep the load-bearing phrases; fix via a coder card with exact old→new string pairs.

Relay your own recomputed figures, and say explicitly when a worker's framing was
misleading even if its numbers were right (e.g. "no reaction" meaning "no win/loss
flips" while margins actually moved on 51/52 games).

**A background-process or late completion notice for work you already reported is not a new request:** reply in 1–3 lines (`references/status-and-resume-checks.md`).

## Writing cards

- **Design → implementation pair, in order.** Create the design card assigned to yourself with the
  spec body, `complete` it with a one-line result, then create the coder card with
  `--parent <design_id> --max-retries 4 --workspace "dir:<repo>"`, reusing the same body file. The
  body must end with the request-review loop and `--reviewer reviewer-bot` spelled out. Finish with
  `kanban show <coder_id>` and confirm it reads `ready`, `assignee: coder-bot`, `parents: <design_id>`.
- **Pre-verify the premise before assigning.** Confirm the data/files the card depends
  on actually exist and have the shape you assume, and that a worker is allowed to run every
  step (no kanban CLI writes, no `hermes update`; see `references/worker-limits-and-test-boards.md`).
  Cards built on a guess waste a run.
  Premise checks for borrowed components and for label mappings reused on a new data release: `references/spec-writing-checks.md`.
- **Subscribe intermediate coder/helper cards with `--delivery-mode notify`** (user rule 10/27):
  their review is done by the kanban review worker, and a wake on `review_requested` cost 36% of
  Discord spend. Use `wake` only for cards needing a user decision, a phase's final card, and fable.
  Wake kinds are fixed in code (upstream #136614).
- **Embed expected reproduction values** (exact means, per-seed deltas, counts) and say
  "if these don't reproduce, the implementation is wrong — stop and report". This turns
  a self-report into a checkable claim. Compute every embedded count with a real parser
  (`csv` module, `json`), never `wc -l` or `awk -F,`: quoted fields holding commas or newlines
  (e.g. a CLI `description` column) inflate line counts, and the worker then measures
  against your wrong number.
- **List already-rejected approaches by name**, and search the phase docs, data dirs and `src/` for your own design before writing it (`references/spec-writing-checks.md`).
- **Make "no improvement found" an explicitly valid outcome.** Without this, workers
  manufacture a recommendation. Add: do not loosen the acceptance bar to pass it.
- **Spell out every time, budget and timeout limit, and forbid the worker from adding its own.**
  A worker that adds a stricter "safety" cap can kill the very measurement the card exists
  for. The rework then costs a new push and a review round.
- **Separate hard gates (regressions) from soft signals, and tag every gate with the decision it controls** (`references/acceptance-gates.md`).
- Demand `ls`/`diff` output as evidence in the completion summary for any file operation.
- **When a gate result is hours away and the next stage is pre-registered, pre-arm the next stage behind the gate** (chain launcher, kill switch, parse fallback, smoke timing), **and while weights are still training rehearse everything except the weights ("stage 0").** Recipes: `references/long-job-chains.md`.
- Feasibility probes, paid-API cards, regression-gate inputs, duration estimates: `references/spec-writing-checks.md`.
- Detached-job cards, mid-wait hand-offs, release-cron assignees: `references/parking-external-waits.md`. Disarming a chain, mid-training input defects: `references/long-job-chains.md`.
- Reviewer-run follow-up cards; chat decisions vs a live reviewer run: `references/review-cli-quirks.md`.
- Cards sharing a box, quota, repo or RAM; WSL hangs, disk floors, box-down gates, live-box paths: `references/shared-boxes-and-resources.md`.
- Mid-run course corrections go in a card comment that overrides the body (`references/queue-and-dependency-edits.md`).

## CLI pitfalls (these cost real time)

- **Free text is positional on every subcommand that takes it** — `comment <id> "text"`,
  `block <id> [reason...]`, `request-changes <id> <reason...>`, and the title on
  `create <title>`. `--body`, `--reason`, `--title` are all rejected. `--body`, `--assignee`,
  `--parent`, `--max-retries`, `--workspace` *are* real flags on `create`. When unsure, run
  `kanban <subcommand> --help` — it prints the positional/optional split in one line.
- `kanban archive <id>` is the disposition for a card that should not be completed or blocked
  (see Review dispositions).
- **There is no `kanban stop`.** To retire a card whose run is still active, `kanban reclaim <id>`
  to release the worker claim, then `kanban archive <id>`.
- **Park external waits with `schedule`, not repeated `block`** (2nd block → triage → auto-decompose). See references/parking-external-waits.md.
- **Before writing a spec or a resume/restart instruction, read the code it depends on.** See references/spec-writing-checks.md (also: how to write latency/count/load-time/CPU gates so a correct implementation can pass).
- **When a faithful implementation misses gates, sort each FAIL before the review worker acts:** recompute from raw; label it measurement artifact, spec arithmetic, noise, or real. Comment on the card "do not request-changes; approve execution, criterion N unmet = design decision", and give the user the real misses with accept-as-override vs follow-up-design options. Sending it back makes the coder change constants it does not own.
- **A "crashed (worker exited); dispatcher will retry" notice is not proof the worker died.**
  On every such notice, run `ps -axo pid,etime,command | grep "work kanban task"` right away.
  Duplicate workers, retries exhausted, credential (`exit_code 78`) stops: `references/stuck-cards.md`.
- Any multi-line comment/reason: write a file, pass `"$(cat f)"`; backticks inline in a double-quoted arg run as commands and silently drop text. Body files, heredoc refusals, encoding failures: `references/card-bodies-and-comments.md`.
- `--board` is a top-level flag, so put it BEFORE the subcommand: `hermes kanban --board <slug> create ...`
  (also `comment`, `show`, `unblock`, `notify-subscribe`). Placed after `create` it is rejected. Alternatives:
  `--project <slug>` on `create`, or `kanban boards switch <slug>`. Always also pass
  `--workspace "dir:<abs path>"` to pin the working dir;
  otherwise switch with `kanban boards switch <slug>`.
- `create` prints no id in its default output — pass `--json` and parse the id out,
  or you cannot subscribe to the card you just made. The id sits at the top of the JSON, so
  piping through `tail` drops it; if it is lost, recover it with
  `kanban list | grep "<unique title keyword>" | awk '{print $2}'`.
- There is no `kanban subscribe`; it is `notify-subscribe`. `--chat` is **ambiguous**
  (`--chat-id` vs `--chat-type`) and `--platform` is required, so the working form is
  `notify-subscribe <id> --platform discord --chat-id N --thread-id N`.
- **Never `--parent` a new card to a card that is (or will stay) `blocked`** unless a cron or a person will complete that card (the box-down gate pattern above). A child waits in `todo` with `dependency_wait parent_not_done` until the parent completes, so hanging a follow-up (e.g. a diagnosis card) off a deliberately blocked card strands it forever. Use `--parent` only for real "start after X finishes" ordering; for context, name the related card in the body. If it already happened: `kanban unlink <parent> <child>` and confirm `show` reads `ready`.
  Box-down gate pattern: `references/shared-boxes-and-resources.md`.
- **Repeated blocks trip a circuit breaker** (`failure_limit`, default 2) and route the
  card to `triage`. Raise `--max-retries` on cards you expect to iterate on.
  Auto-decomposer children and `triage` handling: `references/block-loop-auto-decompose.md`.
- **Your own blocks count toward that limit.** Blocking a card to redirect the worker can
  strand it in triage even though the worker never failed. Prefer a comment + reclaim.
  Parking a card for an external wait (quota reset, a kernel still running) by block → handoff →
  block also trips it. Use `schedule` for long waits.
- An unblock→block cycle also trips "unblock loop detected".
- the remote platform multi-version outputs, crons: `references/live-chains-specs-and-crons.md`. Closing a live card with a verdict, cards blocked from `review`, anomaly alerts: `references/review-cli-quirks.md`. Retiring/rewriting cards: `references/queue-and-dependency-edits.md`. Capability blocks, protected files: `references/worker-limits-and-test-boards.md`.

## Notification routing

`kanban notify-subscribe <id> --platform ... --chat-id ... --delivery-mode <mode>`

- `notify` / `notify+wake` post the **worker's raw summary** into the chat.
- `wake` wakes you only — you read the board and report in your own voice. Use this when
  the user wants the reviewer, not the worker, speaking.
- Set `--notifier-profile` to your own profile so delivery is owned by you.
- **Subscribe the chat the user is in now**, not an earlier card's thread (`references/notify-token-budget.md`).

## Check the card itself before acting on it

A card can be defective independently of the worker. Run these checks when a card completes or
blocks, before you approve, relay, or act on its output:

- **Does the title match the body?** A card titled for one build can carry a body specifying an
  entirely unrelated one. The worker will faithfully build the body, so the deliverable is not
  what the title promised. Read both, and when they disagree treat the body as what was built
  and the title as the bug. Put "if the title and body contradict, do not reinterpret — block"
  in cards you write.
- **Is the deliverable already on disk from an earlier card?** Hash it. A re-issued card can
  reproduce a byte-identical artifact under a new name, leaving the same bytes carrying two
  version numbers — a lasting citation hazard. Compare `sha256` against the existing candidates
  before treating the output as new information, and recommend collapsing to one name.
- **Is the premise still current?** A card written days earlier can reference a baseline the line
  has since moved past. Evidence gathered against a superseded baseline has never passed the
  project's own acceptance gate, however clean the card's execution was.

## Review dispositions: approve execution, correct the premise separately

When a worker executed the spec faithfully but the *spec's* numbers or premise were wrong, do not
reject the card — rejection asks the worker to fix something it did not author, and a second
block can trip the circuit breaker. Instead:

- **Approve/leave completed**, and post a comment that states the correction with your own
  recomputed figures and labels itself as superseding the card's quoted numbers. The board then
  carries both the honest execution record and the corrected conclusion.
- **Archive** a card whose body was defective at birth (wrong subject, stale candidate). Say in
  the comment that it is not the worker's fault and name what was wrong with the body. Leave the
  artifacts on disk; they usually have record value even when unusable.
- Reserve `changes_requested` for things the worker can actually fix: factual errors in its own
  document, missed spec items, unverified claims.
- **State the scope boundary in the rejection: what passed, and what must NOT be re-run.** A
  worker facing a rejection defaults to redoing everything, so a request to fix a derived table can
  cost a full re-measurement. List the parts you independently verified ("fidelity gate, the
  N-game matrix, the runtime checks — all confirmed, do not re-run") alongside the numbered fixes,
  and say plainly whether re-measurement is needed. Scoped this way a rework lands in minutes
  instead of rerunning the expensive step.
- **Number the required changes and give each one the evidence that it is wrong.** Quoting your own
  recomputed figure next to the worker's makes the fix checkable rather than a matter of authority,
  and the worker can verify it landed without another round trip.
- **Record an override the moment the user picks an option below a pre-set criterion** (e.g.
  "proceed" when one gate missed by a hair): a `사용자 결정(override): <criterion, number, choice>`
  comment on the card the next step hangs from, plus the same line in the next card's doc step.
  Left for later, the final check flags it as a defect.
- **Do not @-tag inside the user's quiet hours** (see memory), even when a decision is pending.
  Check the clock before writing the tag; say "for the morning" instead and let the cron flush.
  One-night quiet-hours overrides and night watchers: `references/overnight-autonomy-and-quiet-hours.md`. Fencing a rework off a running job: `references/long-job-chains.md`.

After you have issued a terminal review action, your obligations to that card are discharged even
if the harness keeps asking for one. Do not `complete` a card you just rejected (that is
rubber-stamping the work you objected to) and do not `block` one that has no real blocker (that
kills the worker's in-flight fix and burns a retry). Say so in a comment and move on.

- A `changes_requested` notice can be your own action echoed back: `kanban show` first; if a new worker run is already claimed, do nothing (`references/review-cli-quirks.md`).


## Situational playbooks

- Final check / fable opinion / checker-model design (only when asked; the checker does not decide): `references/fable-handoff.md`.
- "Decide yourself until morning", overnight submits, "act now": `references/overnight-autonomy-and-quiet-hours.md`.
- "Is anything running?", resume, "did we miss anything?", ship before close: `references/status-and-resume-checks.md`.
- Benchmark statistics, experiment design: `references/statistical-hygiene.md`.

## References

Load: `skill_view(name, file_path="references/<file>.md")`.

- `references/acceptance-gates.md` — read when writing numeric gates or pre-checking a worker's numbers.
- `references/block-loop-auto-decompose.md` — read when a card hit `triage` or got auto-decomposed children.
- `references/card-bodies-and-comments.md` — read when posting a long spec or multi-line comment.
- `references/cli-review-gotchas.md` — read when a review-stage CLI call is refused or gating the remote platform re-runs.
- `references/fable-handoff.md` — read when the user asks for a final check, fable's opinion or a fable design.
- `references/live-chains-specs-and-crons.md` — read when touching the submit wrapper, a live box chain, a data-transform spec, or crons.
- `references/long-job-chains.md` — read when a deliverable depends on hours-long training/kernels.
- `references/notify-token-budget.md` — read when choosing wake vs notify or auditing token cost.
- `references/overnight-autonomy-and-quiet-hours.md` — read when decisions are delegated overnight or quiet hours are lifted.
- `references/parking-external-waits.md` — read when a card must wait on an external job.
- `references/queue-and-dependency-edits.md` — read when inserting, reordering, holding, retiring or rewriting live cards.
- `references/review-cli-quirks.md` — read when a reviewer run and the chat both act on a card.
- `references/shared-boxes-and-resources.md` — read when cards share a box/quota/repo/RAM or a box goes dark.
- `references/spec-writing-checks.md` — read before writing a spec or a resume/restart instruction.
- `references/stall-watchdog.md` — read when an approved mechanical handoff might stall between turns.
- `references/statistical-hygiene.md` — read when judging or designing benchmark/experiment work.
- `references/status-and-resume-checks.md` — read when asked what is running, to resume, to summarise or what is left.
- `references/stuck-cards.md` — read when a card is stuck, refused, crashed or has duplicate workers.
- `references/worker-limits-and-test-boards.md` — read when a card needs kanban activity, a human step or a user prerequisite.
- `templates/card-footer-review-loop.md` — append to every coder card body (request-review loop).
