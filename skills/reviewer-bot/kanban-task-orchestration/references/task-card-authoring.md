# Writing a Task Card Another Bot Can Execute

## Body structure that works

1. **배경 / Background** — the numbers, file paths, and prior results verbatim. Fenced
   blocks for measurement tables so they survive rendering.
2. **할 일 / Work** — numbered, each item naming the concrete artifact or decision it
   must produce. Vague verbs ("analyze", "improve") produce vague cards; bind each to a
   check ("name the constant and its file location", "give the measurement command").
3. **산출물 / Deliverable** — the exact output path, and the sentence "a downstream task
   must be able to implement from this document alone."
4. **금지 / Prohibitions** — what the worker must NOT do. This is the highest-leverage
   section; without it workers expand scope. Typical entries: don't modify production
   code on an analysis card, don't propose numbers without justification, don't defend
   the prior design, don't relax the acceptance criteria to make results pass.
5. **Completion protocol** — `kanban_complete` vs `kanban_block`-for-approval, plus what
   the summary must contain (keep it to three or four named lines).

## Analysis and tuning cards

When a card asks another agent to tune parameters or explain a regression, these
requirements belong in the body or the resulting work is unreliable:

- **Demand ablation whenever more than one change shipped together.** A batch of N
  simultaneous changes with one aggregate result attributes nothing; a tuning proposal
  built on that is guesswork dressed as analysis. Require each change to be individually
  toggleable and measured on/off before any number is adjusted.
- **Check whether the codebase already has a parameter convention before demanding
  toggles.** Mature tuning-heavy projects often expose every knob one way (a bank of
  `PREFIX_*` environment variables read with a default, driven by an existing sweep
  script). Changes that hardcode constants instead have broken that convention, which is
  both the reason ablation is impossible and a defect worth reporting. Require new
  toggles to follow the existing pattern, and grep for the convention before writing the
  card so you can name it.
- **Pair any extract-the-knobs step with a baseline-equivalence gate.** Require that with
  every toggle at its default the harness reproduces the pre-refactor numbers *exactly*,
  and that a mismatch stops the work and reports instead of continuing. Without this the
  refactor can silently change behavior and every ablation number above it is measuring
  the wrong thing. A refactor's correctness is only demonstrated by unchanged behavior.
- **An analysis card that must not touch production code still needs somewhere to work.**
  Permit a copy of the module under test in a scratch directory, and require the report
  to state that the measurements came from the copy. This resolves the common deadlock
  between "add toggles so we can ablate" and "do not modify the engine."
- **Force the sample-size question when the system is stochastic.** If the spread across
  runs is an order of magnitude larger than the mean delta, the measurement does not
  support *any* conclusion — including the negative one that the change was harmful.
  Require the card to widen the sample and to measure the per-run cost of doing so.
  Expect sign flips: the same code can read negative at n=5, positive at n=20, and
  negative again at n=50. Until the sample is large enough, "this change made things
  worse" is not a finding, and neither is its opposite.
- **Require an effect-size-vs-spread comparison, stated as a ratio.** Cheap to compute,
  and it decides whether the rest of the analysis means anything. Ask for the run-to-run
  standard deviation as a percentage of the mean alongside the size of the effect being
  chased; when the effect is a fraction of the noise, the honest deliverable is the
  sample size that would be needed, not a tuned parameter.
- **Require confidence intervals, not point estimates, for every recommendation**, plus
  the count of runs where behavior actually differed from baseline. A change that is a
  no-op in most runs and large in a few is a different object from a uniform small
  improvement, and only the per-run counts distinguish them.
- **Reject per-sample acceptance criteria on high-variance systems.** "Every seed must be
  >= baseline" fails genuine improvements almost always, because one bad draw sinks the
  whole gate. Replace with mean-or-median improvement plus a regression guard ("no single
  run degrades more than X%").
- **Every acceptance criterion ships with the command that measures it.** A criterion
  nobody can run is a criterion the next worker will interpret in its own favor.
- **Check that the benchmark's metric is the metric that actually matters** before
  writing any acceptance criterion. Harnesses tend to report whatever is easiest to
  extract — a raw score against a trivial opponent — while the objective the user cares
  about is something else entirely, such as win rate against the real field. Optimizing
  the convenient proxy can be worthless or negative: where the payoff is a win/loss
  outcome, widening the margin of matches already won is worth nothing, and added
  variance strictly lowers the win rate of a position that already has an edge. Confirm
  the objective from project docs, name it in the card, and say so plainly when existing
  work has been graded on the wrong axis — including work you specified yourself.
- **Split acceptance into hard regression gates and soft improvement targets** on
  high-variance systems. Hard: no run degrades beyond X%, no more than N runs change at
  all. Soft: mean and median improve. Making improvement a hard gate means a genuine
  change passes or fails on luck; making regression soft means damage ships.
- **Require the worker to report bad numbers unchanged.** State it explicitly; otherwise
  a worker that misses the bar tends to soften the bar instead of the claim.
- **List the approaches already tried and rejected, with their measured results.**
  Long-running projects accumulate these in their notes; a card that omits them gets a
  proposal to redo something already disproven. Search the project's own docs for the
  rejection record and paste the short version into the card.
- **Authorize "no viable improvement found" as a valid deliverable.** Without that
  sentence a worker asked for recommendations will invent one, which is the exact failure
  mode that produces unvalidated parameter changes.

## Instructing an implementation card downstream of a spec

- Point at the spec document by path and say "implement it as written; do not
  reinterpret." Add: if the spec is contradictory or unimplementable, write no code and
  `kanban_block` with the specific contradiction.
- Tell it to inspect the working tree first (`git status` / `git diff`) when a previous
  card already left changes there, and to block if the new spec is ambiguous about
  whether it builds on those changes or replaces them.
- Require before/after numbers per run, produced by the same harness the baseline used —
  a different harness makes the comparison meaningless.
