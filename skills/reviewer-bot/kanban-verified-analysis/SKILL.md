---
name: kanban-verified-analysis
description: "Use when running kanban analysis cards via worker bots."
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, multi-agent, verification, statistics, orchestration, analysis]
---

# Kanban Verified Analysis

Orchestrating analysis/optimization work across a `hermes kanban` board where an
orchestrator profile writes cards and a worker profile executes them. Covers role
discipline, verifying worker claims, statistical rigor, and board pitfalls.

## Role discipline

Orchestrator = analysis, design, verification, writing cards. Worker = ALL
implementation, file edits, and mechanical trial-and-error (including API endpoint
probing and scripted searches).

**Never edit files directly as the orchestrator** — not even a one-line revert or a
`cp` to restore a backup. Put it in a card. Probing endpoints with a script is also
worker work. If you already did exploratory work, don't discard it: hand the findings
to the worker in a card comment so failures aren't repeated.

## Verify every worker report against raw data

Worker summaries are self-reports, not facts. Before relaying any result, re-derive
the headline numbers yourself from the raw artifacts (pkl/JSON/bench output the worker
produced), and check file state with `ls`/`diff`/`md5`.

Real failures this caught:
- "deleted file X" — file was still present, overwritten with the original instead
- a hard pass/fail gate silently skipped on the second dataset
- a claimed "no effect" that was actually "effect present, outcomes unchanged"

Report results in your own voice with your own numbers. Never relay worker text verbatim.

### Grep every quoted literal in the raw source before accepting the narrative on top of it

Re-deriving aggregate numbers is not enough. A report will also quote *specific artifacts* —
an action dict, a log line, a config value — as the evidence for its causal story, and those
are quoted, not computed, so no statistical check touches them. One report attributed a loss
cluster to a particular order at a particular step; searching that step across every game in
the cluster returned **0 occurrences** of the quoted order and a completely different pair of
orders in all of them.

So: for any claim of the form "at step/line X the system did Y", pull X out of the raw data
yourself and confirm Y is literally there. Require reports to cite the source location for
every quoted artifact so this check is cheap. A fabricated literal invalidates the entire
causal section built on it while leaving the surrounding aggregates correct — which is exactly
why it survives a numbers-only review.

## Sample size and statistics

**Never judge on small n.** In one project the identical code gave: n=5 → -1565,
n=20 → +2943, n=50 → -259 — the sign flipped twice. Check effect size against spread:
if per-seed sd is ~15% of the mean and the effect is ~1%, small samples are pure noise.

- Use n≥50 for benchmark judgments; measure and record per-run cost to justify it.
- Compare **paired** (same seed both arms); unpaired comparisons drown in between-seed variance.
- Report bootstrap CI and P(Δ>0), not just the mean. **A CI containing 0 means "not significant"
  even when the mean is positive** — say so explicitly.
- Make completion criteria **hard on regression, soft on improvement**. Gating on "mean must
  improve" fails genuinely good changes when effect < noise.
- A hard gate is empirical and **dataset-dependent**: re-measure it on every new dataset.
  "Same logic, so the earlier result carries over" is invalid.

## Stop the review loop once the numeric core is reproduced and the conclusion is stable

Reviewing finds defects indefinitely — prose that contradicts its own table, a range quoted
with one endpoint wrong, a section that ignores a dimension the card asked for. Each round
costs a full worker cycle. An analysis card can run four rounds where every round after the
first finds only wording defects, every headline number is independently reproduced, and the
top-level conclusion never moves.

Apply a termination test at the end of each round:

1. Has the **numeric core** been independently reproduced (your own harness, not the worker's
   script, on a sample that does not overlap theirs)?
2. Would fixing the remaining defects **change the decision** this card feeds?

If (1) is yes and (2) is no, stop reviewing. Send the residual defects as a single
non-blocking correction comment, and move the track to an execution card. Findings that only
reinforce the existing conclusion — a second event also landing outside the window you were
testing — are the clearest signal that further rounds are buying nothing.

The deeper reason: for an analysis card the deliverable is a **decision**, not a publishable
document. Defect-free prose earns nothing on its own. Where the finding is genuinely uncertain,
the settling evidence is a controlled A/B, not another pass over the write-up — so a round
that cannot change the A/B you would run next is a round that should not happen.

Corollary for your own reviews: when a later round exposes something an earlier round waved
through, record that in the feedback. "I passed this without checking" keeps the defect count
honest and stops the loop being read as the worker alone degrading.

## Correlation is not an intervention (the main failure mode)

Four consecutive targets failed because a strong *observed* difference was treated as a
cause. Before committing to a target, ask: **is this variable something we control, and does
changing it actually change the outcome?**

Examples of the trap:
- 37.5pp win-rate gap between "collides" and "doesn't collide" groups → sweeping the timing
  changed **zero** outcomes. The collision marked already-losing games; it didn't cause them.
- r=+0.67 between an environment feature and a top player's configuration → copying the
  configuration produced **negative** results, because the top bot was a live engine that
  also adapted everything downstream. Changing one constant gives you the cost without the benefit.
- A 45x behavioural difference vs top-ranked players that was **not intervenable** at all
  without rewriting the whole agent.

When the gap is large but you cannot intervene, say so and drop it. Don't build a card.

### Hold your own hypotheses to the worker-report standard

The verification discipline above is aimed at worker output, which creates a blind spot: the
orchestrator's own hypotheses get written straight into cards without the same raw-data check.
They fail at least as often. In one session four orchestrator hypotheses were falsified by the
cards sent to test them — a suspected wiring bug (every one of 11 state fields matched), a
selective-intervention scheme (predicted +6,369, delivered −2,092), a subsystem judged harmful
from a subgroup split (all 11 variants beat the baseline under control), and a narrow-loss
cluster judged fixable (the opponents were clones of our own build).

The shared mechanism is reading a pattern off **partial data** — one window, one subgroup, one
file — and generalising it to the whole system. Before spending a card on your own theory,
state what would falsify it and check that cheaply against the full data you already hold. A
card is the expensive way to discover you were looking at a slice.

A large disagreement with the incumbent on unlabeled data is itself the cheap falsification
check, and it must gate spend. A new pseudo-label source whose prevalence was a third of the
incumbent's on key targets (e.g. 20% vs 60%) and whose binary agreement was 0.83 (incumbent
sources agreed 0.95 with each other) went on to lose −0.107 macro AUC on the gold set after
$55 of labelling. The cause was a definition choice in the prompt (strict severity thresholds
mapped borderline findings to the same score as clean negatives, erasing rank information for
an AUC metric). Before a full run, pilot ~100 items and stop if prevalence or agreement is far
from the incumbent without an independent reason to believe the incumbent is wrong; for AUC
targets, never collapse graded evidence (mild/small/low-grade) into the clean-negative bucket.

Bulk LLM labelling (pilot gate, session-length limits against compaction drift, blind
relabels, drift detection by position, one-shot gold evaluation) is covered in
`references/llm-labelling-workers.md`.

This matters for reporting too: name your own overturned calls as explicitly as the worker's.
A verification log that only ever catches the worker is not measuring itself.

## Writing cards

- Front-load facts you already verified, with the exact numbers, so the worker doesn't redo them.
- List **already-rejected approaches with reasons** so they aren't re-proposed.
- Name exact file paths / line numbers / constants for the intervention point.
- Give expected reproduction values; state that a mismatch means the implementation is wrong.
- State explicitly that **a negative result is a valid conclusion** and that criteria must not
  be loosened to pass. Without this the worker invents an improvement.
- Add a **pre-flight gate** when the measurement setup might be invalid (e.g. "if the sample's
  feature distribution doesn't match production, stop and report before sweeping"). This gate
  correctly halted a run that would otherwise have produced meaningless numbers.
- Forbid editing originals; require new files. Require `ls`/`diff` output as evidence in reports.

## Kanban operational pitfalls

- **Blocking a card twice trips `failure_limit` → the card routes to `triage`, where
  `unblock`/`complete`/`promote` are all refused.** Only `archive` gets it out. Inject course
  corrections as **`hermes kanban comment`**, never as a block.
  - A worker blocking at a pre-registered gate the user must decide on is correct
    behaviour, but it still counts toward the limit. Write gates that need a user decision
    as "comment the result and stop" rather than "block", or expect triage.
  - Once a card is in triage, the auto-decomposer can rewrite its title/body and promote it
    again. The worker, seeing no new decision, blocks again, and the loop repeats with
    another notification. Archive the triaged card promptly: comment what it produced,
    then archive. Carry the user's decision into a **new** card whose body records it as
    `사용자 결정(override): ...`, so the worker executes instead of re-asking.
- `hermes kanban comment <id> "text"` takes the body positionally — there is no `--body` flag
  (unlike `create`). For any body containing backticks, `$`, parentheses or quotes, **always**
  write it to a file first and pass `"$(cat file)"`. Inline double-quoted text gets
  command-substituted by the shell, which posts a half-garbled instruction the worker may
  act on. If that happens, post a full corrected comment at once and mark it as superseding.
- When a decision lands on a card that is in `blocked` (the user picks an option),
  comment the decision first and then `unblock`. Unblocking first lets the dispatcher spawn
  a worker that reads the old comments and blocks again.
- `--board` is not a global flag; switch with `hermes kanban boards switch <slug>`.
- Subscribe notifications with `notify-subscribe --delivery-mode wake` so the orchestrator is
  woken to verify and summarize, instead of worker text being pushed to the user raw.
- A completed card's notification summary is **truncated** — always open the card and the
  artifacts rather than acting on the notification text.
- **`kanban_request_changes` is refused ("task is not in an active review run") once the card
  has left `review`.** A stray `kanban_complete` from another session — one that defaults to the
  env task id — can close the card you are reviewing mid-verdict, leaving it `done` with a
  summary describing a *different* card's work. When this happens, do NOT restate the approval:
  file the defects as a new child card (`parents=[reviewed_card]`) assigned to the implementer,
  and add a comment on the closed card recording that the board summary is not the real verdict.
- Check whose work a `done` summary actually describes before trusting it. Cross-check the
  summary's numbers against the card's own fix list; a mismatch means the wrong card was closed.
- Give doc-editing cards `workspace_kind="dir"` + `workspace_path=<repo root>`. The `scratch`
  default hands the worker an empty tmp dir, forcing a "work in the repo instead" correction
  comment on every card.

## Verifying a table-heavy document

Don't eyeball a table that claims a trend — parse it and diff every cell against a
recomputation. Regex the `label | value` pairs out of the markdown section, rebuild the same
buckets from the raw data, then report three sets: cells missing from the doc, extra cells, and
value mismatches. This is what proves "47/47 intervals present, 0 mismatched" instead of
"looks complete".

Audit a count's **predicate**, not just its total. A listed breakdown whose items sum to a
different number than the stated total is the tell: one enumerated item usually fails the
stated condition (e.g. a row listed under "check X is not PASS" whose check X *is* PASS, inflating
101 to 102). Sum the breakdown yourself and confirm each item satisfies the predicate.

When a doc is revised, grep for the OLD claim across the whole file, not only the section you
asked to be rewritten. Parallel sections repeat the same conclusion, and workers fix the one
you quoted while leaving the twin intact — which leaves the document self-contradicting.

A worker reporting "my recomputation disagrees with your spec" is doing the right thing, but
verify *which* side was wrong before accepting the deviation; the spec is sometimes correct and
the worker's predicate subtly broader. Also credit the reverse case: when the worker's value
corrects your spec (e.g. a sign convention), say so and keep their version.

## Deliverables

Keep a running handoff document in the repo (findings with verified numbers, methodology
lessons, a rejected-approaches table with reasons, reusable artifacts, and prioritized next
steps). Update it as conclusions are overturned — including **correcting your own earlier
recommendations** when data contradicts them.
