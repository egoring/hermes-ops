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

## Role boundary

**Never edit files yourself.** Not even a one-line revert or a cleanup `rm`. If a
file must change, that is a card for the coder profile — put the exact desired end
state in the card and let the worker do it. Touching files directly breaks the
separation the user relies on and makes the board history lie about who did what.

What you *may* run: read-only inspection (`diff`, `ls`, `grep`), and re-running the
worker's own verification scripts to check their numbers.

## Verify every self-report

Worker summaries are claims, not facts. Before relaying a result:

- **Recompute headline numbers from the raw artifact** (pkl/json the worker left
  behind), not from its prose. Sign flips and dropped rows show up here.
- **`diff` the files** against a known-good baseline to confirm the change is
  exactly what was claimed and nothing else rode along.
- **Confirm claimed deletions with `ls`.** A worker once reported "deleted X" when
  it had actually overwritten X with the original content — the file was still there.
- Check that a claimed "no-op default" really reproduces the baseline numbers exactly.

Relay your own recomputed figures, and say explicitly when a worker's framing was
misleading even if its numbers were right (e.g. "no reaction" meaning "no win/loss
flips" while margins actually moved on 51/52 games).

**A background-process completion notice is not a new request.** When a job you already harvested
finishes, reply in 1–3 lines: which job it was, that its numbers are already in the last report
(or what changed if the final count differs), and what is still running. Do not re-report.

## Writing cards

- **Design → implementation pair, in order.** Create the design card assigned to yourself with the
  spec body, `complete` it with a one-line result, then create the coder card with
  `--parent <design_id> --max-retries 4 --workspace "dir:<repo>"`, reusing the same body file. The
  body must end with the request-review loop and `--reviewer reviewer-bot` spelled out. Finish with
  `kanban show <coder_id>` and confirm it reads `ready`, `assignee: coder-bot`, `parents: <design_id>`.
- **Pre-verify the premise before assigning.** Confirm the data/files the card depends
  on actually exist and have the shape you assume. Cards built on a guess waste a run.
- **For a small, well-defined rule, run a throwaway feasibility probe in your own scratch first**
  (a wrapper around the live artifact, never a repo edit) and set the card's thresholds below the
  probe's result on a DIFFERENT seeded seed list, reporting zero intersection. The probe also
  catches constants taken from memory (domain constants were wrong until checked against the
  source module). Name the probe file in the card as the reference implementation, and forbid
  importing it from the deliverable.
- **Subscribe to the coder card with `--delivery-mode wake --notifier-profile <self>`** right after
  creating it, so its completion comes back to you for re-verification instead of being relayed raw.
- **Embed expected reproduction values** (exact means, per-seed deltas, counts) and say
  "if these don't reproduce, the implementation is wrong — stop and report". This turns
  a self-report into a checkable claim.
- **List already-rejected approaches by name** with a pointer to where they were rejected,
  so the worker doesn't re-propose them.
- **Make "no improvement found" an explicitly valid outcome.** Without this, workers
  manufacture a recommendation. Add: do not loosen the acceptance bar to pass it.
- **Separate hard gates from soft signals.** Hard = regression guards (nothing gets worse);
  soft = the improvement you hope for. When effect size is near the noise floor, gating on
  the improvement makes pass/fail a coin flip.
- **Tag every gate with the decision it controls** ("G0,G1,G3,G5 → upload A; G6–G8 → candidate B
  only"). A multi-gate card then cannot hold one artifact hostage to another artifact's slow or
  buggy gate, and a mid-run "can we ship now?" is answered by recomputing only that decision's
  gates.
- Demand `ls`/`diff` output as evidence in the completion summary for any file operation.
- **Quote pipeline durations from the previous run's artifacts, not from impression.** Before
  telling the user how long a design→build→gates→review cycle takes, list the prior card's output
  dir by mtime (`ls -lT -tr`) and split wall time into first build, rejection rounds, and the final
  gate run. A guessed "10-12h" was really ~1h of gates plus ~2.5h of rework — and the rework,
  not the verification, is what a reusable/generalised tool removes. For a generalisation card,
  make byte-identical reproduction of the old artifact (md5) plus the old gate numbers the
  completion criteria, and keep the original scripts untouched as the reference.
- When changing direction mid-run, put the correction in a card comment that says it
  overrides the body. It may not reach a running worker, but it is authoritative on requeue.

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
- **To close a live card *with* a verdict** (the user ends a verification early and its partial
  results still count): post the verdict comment first, then `kanban reclaim <id>` and
  `kanban complete <id> --force --result "..."`. Plain `complete` is refused while a run holds
  the claim. Afterwards confirm the worker pid from the card's `spawned` event is gone
  (`ps -p <pid>`) and that `show` reads `done` — a reclaimed worker can keep writing files.

### Getting a long spec into a card

A multi-paragraph card body inlined as `--body "$(cat <<'EOF' ... EOF)"` can be refused by the
shell guard, which cannot prove the executable body of a large heredoc and blocks the whole
command. Do not fight it by shortening the spec. Two working paths, in order:

1. Write the body to a file with the `write_file` tool (not a shell heredoc), then
   `kanban create "<title>" --assignee X --body-file <path> --json`. `--body-file` is a real flag and
   avoids shell substitution entirely; `--body "$(cat <path>)"` is the fallback.
2. If that is still refused, create with a one-line stub body (`"스펙은 첫 코멘트 참조"` /
   "spec in first comment") and post the full spec as the first `kanban comment`. The worker
   reads comments, so nothing is lost.

**Give every body file a unique, descriptive name** (`/tmp/kb_<ver>_<purpose>.md`), never a short
generic one (`/tmp/kb_sub.md`). Generic paths get reused across sessions, and a stale file a later
step never overwrote has shipped a completely unrelated spec into three separate cards here — once
silently, because the card was archived before the worker ran. Before `create`, `grep -c` the
defining keyword of the intended topic against the file, and grep the keyword of the *wrong* topic
expecting 0; run that grep through the terminal, not through the same helper that just wrote it.

Always `kanban show <id>` afterwards to confirm the body or comment actually landed — a failed
`cat` inside the substitution yields an empty body and the CLI rejects it with a bare
"comment body is required". `show` echoes the opening body lines, which is the cheapest way to
catch a contaminated body before the worker starts.
- `--board` is not a flag on `create` either. Target a board inline with
  `--project <slug>` (plus `--workspace "dir:<abs path>"` to pin the working dir);
  otherwise switch with `kanban boards switch <slug>`.
- `create` prints no id in its default output — pass `--json` and parse the id out,
  or you cannot subscribe to the card you just made. The id sits at the top of the JSON, so
  piping through `tail` drops it; if it is lost, recover it with
  `kanban list | grep "<unique title keyword>" | awk '{print $2}'`.
- There is no `kanban subscribe`; it is `notify-subscribe`. `--chat` is **ambiguous**
  (`--chat-id` vs `--chat-type`) and `--platform` is required, so the working form is
  `notify-subscribe <id> --platform discord --chat-id N --thread-id N`.
- **Repeated blocks trip a circuit breaker** (`failure_limit`, default 2) and route the
  card to `triage`. From `triage`, `unblock`/`promote`/`complete` are all refused — the
  only clean exit is `archive`. Raise `--max-retries` on cards you expect to iterate on.
- **Your own blocks count toward that limit.** Blocking a card to redirect the worker can
  strand it in triage even though the worker never failed. Prefer a comment + reclaim.
- An unblock→block cycle also trips "unblock loop detected".

## "Is anything running?" / "can we continue where we left off?" / "can we ship before it finishes?"

Answer from the machine and the board, not from memory. Run one batch:

1. `ps aux | grep -iE "python|bench|eval"`: the worker's actual script, its CPU% and start time.
2. `hermes kanban list | grep -viE "done|archived"`, then `kanban show <id>` on each live card for
   the round number and the latest review summary.
3. `ls -lat <card output dir> | head` and the tail of its run log: what was rewritten and when.
   An empty log next to a busy process means the process is still running, not that it hung.

Report per card: what finished, what is running and for how long, and the headline counts
(e.g. how many games passed the fidelity check). Flag counts that look like a spec defect
rather than a worker defect.

**A card can close without you noticing.** A `request-review --reviewer <self>` spawns a separate
reviewer run of your own profile that may approve and complete the card on its own. Before
telling the user a card is "still running" or summarising a build, `kanban show <id>` and read
the run list and last events; if a reviewer run already completed it, re-read the result files it
cited (hash the artifact, open the summary JSONs) and report that verdict as confirmed-by-you.

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

## Notification routing

`kanban notify-subscribe <id> --platform ... --chat-id ... --delivery-mode <mode>`

- `notify` / `notify+wake` post the **worker's raw summary** into the chat.
- `wake` wakes you only — you read the board and report in your own voice. Use this when
  the user wants the reviewer, not the worker, speaking.
- Set `--notifier-profile` to your own profile so delivery is owned by you.

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

After you have issued a terminal review action, your obligations to that card are discharged even
if the harness keeps asking for one. Do not `complete` a card you just rejected (that is
rubber-stamping the work you objected to) and do not `block` one that has no real blocker (that
kills the worker's in-flight fix and burns a retry). Say so in a comment and move on.

**A status notification can be your own action echoed back.** A `changes_requested` you just issued
arrives worded as "review requested changes (BLOCK); implementation is not approved — decide the
next step", which reads like fresh work. Before acting, `kanban show <id>` and check the event log
and run list: if the latest `changes_requested` carries your own reviewer name and a new worker run
is already claimed against the card, the loop is healthy and the correct action is **none** —
confirm status/assignee routed back to the implementer and stop. Creating a follow-up card here
duplicates work the worker is mid-way through fixing.

## Statistical hygiene for benchmark work

- **Re-run the headline measurement yourself on inputs the card never touched.** Recomputing from
  the worker's raw artifact only proves its arithmetic; it cannot catch a biased input set. The
  strongest findings of several sessions came from drawing fresh inputs and getting a materially
  different number — approve the execution, then correct the conclusion.
- **Never accept an evenly-spaced parameter sweep as the evidence base.** Strided seeds/IDs
  select a correlated slice of the space and inflated a win rate three separate times here
  (90% -> 67%, 96% -> 73%). Require inputs drawn with a seeded RNG, pin the list in the card, and
  make the worker report a zero intersection with previously used values.
- **Check whether the sample can even detect the effect** before acting on a verdict.
  A result can flip sign across sample sizes (n=5 negative, n=20 positive, n=50 negative)
  when the between-sample sd is ~15% of the mean and the effect is ~0.5%.
- Report paired bootstrap CIs; if the CI includes 0, say the result is not established
  no matter how good the point estimate looks.
- **Pool every distinct measurement before judging, deduping repeats.** Per-card win rates from
  different input blocks can disagree wildly while the pooled estimate is stable and modest; the
  pooled number with its CI is the one to report and to set the next card's bar from.
- **Set an implementation card's completion threshold from the lower bound of the pooled CI**,
  not from the best point estimate, and write "do not lower this bar to pass it" into the card.
- In chaos-sensitive simulations, a "win" by a margin far below the known perturbation
  scale is noise, not an improvement — name it as such.
- Measure the metric the user is actually scored on. Optimising mean score when ranking
  is win/loss based means large margins on already-won games are worth nothing. Corollary: when
  the win-rate CI excludes the break-even point but the mean-margin CI includes 0, the result
  still counts — say which criterion decides so the worker does not reject on the wrong one.
- Before proposing to merge two workstreams, confirm they share a code path. Two
  "improvements" can live in entirely separate agents, in which case one contributes zero
  to the scored artifact.
