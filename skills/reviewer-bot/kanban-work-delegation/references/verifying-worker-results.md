# Verifying worker-reported results

A worker's final summary is a self-report. Treat every number in it as a claim until you
have reproduced it from an artifact. Workers are not usually dishonest — they are
optimistic, they accept their own framing, and they report the criterion they remember
rather than the one written down.

## Verification gates

Run these before relaying anything. Any failure is grounds for rejection regardless of how
plausible the write-up reads.

1. **Scope** — did the change stay inside what was asked? Diff the workspace against the
   known-good baseline copy and read the diff yourself. "Only file X was modified" is the
   single most common inaccurate claim, and the cheapest to check.
2. **Recomputation** — load the raw result artifact (JSON/pickle/CSV the worker produced)
   and recompute the headline statistics independently. Do not re-read the worker's summary
   table; compute from the values.
3. **Cross-run agreement** — when an earlier card produced overlapping measurements, check
   the two runs agree per-unit (per seed, per case), not just on the mean. Independent runs
   matching item-by-item is strong evidence; matching averages is weak evidence.
4. **Criterion identity** — re-read the acceptance criterion from the spec and confirm the
   worker evaluated *that* criterion. Check the margin: a gate cleared by a fraction of a
   percent is a reportable weakness, not a clean pass.
5. **Baseline sanity** — confirm the baseline numbers still match the previously recorded
   ones. A shifted baseline silently invalidates every delta above it.
6. **Deployment-context defaults** — when the change is gated behind an environment
   variable, flag, or config key, load the artifact **with that variable unset** and assert
   the gate resolves to the intended production value. An experiment toggle written for
   local A/B naturally defaults to *off*, so the shipped artifact is byte-for-byte new and
   behaviorally identical to the old one. Every benchmark still passes, because benchmarks
   set the variable. State the required production default in the card and verify it
   yourself before approving.
7. **Deployability** — confirm the artifact runs in the target environment, not just the
   dev tree. A wrapper that imports its base by path works locally and fails wherever a
   single self-contained file is required; check packaging form, entry point, and runtime
   limits (per-call time budget, memory) against the target's constraints.
8. **Measured vs derived** — for every load-bearing quantity, ask whether the script
   *observed* it or *computed* it from a formula. Only observed values are evidence; see
   below.

## Derived quantities are not measurements

A number a worker's script calculated from a pricing rule, a cost table, or a known formula
is a model output wearing the costume of an observation. Two consecutive "fully attributed
root cause" reports can be built on the same fabricated quantity and both be false.

Three checks, cheap and decisive:

- **Close the account.** Sum the claimed components and confirm they reach the observed
  total. If a residual remains, the attribution is incomplete no matter how confidently it
  is worded — and a residual of roughly the same magnitude as the headline finding means the
  finding *is* the residual, mislabelled. Renaming a residual ("the gap was offset by
  revenue loss") is not closing it.
- **Sanity-check against a hard aggregate.** A claimed expenditure larger than what the
  observed balance change permits is arithmetically impossible, and one subtraction catches
  it.
- **Distrust suspicious invariance.** A quantity identical to the last digit across every
  seed, user, or shard looks like a strong deterministic mechanism but is equally the
  signature of **a formula that never reads state**. Invariance raises the question; it does
  not answer it.

Prefer a primitive the environment itself reports (a balance, a raw event log) and trace it
per-step. When start values are identical across arms, the in-window delta equals the final
delta exactly, which turns a per-step dump into a closed and complete account.

**Carry the same rule into cards you write**: name the raw field to use and ban derived
cost/revenue estimates outright, or the next worker reinvents them.

## A null sweep can mean the knob was never in the path

Before accepting "we swept it and nothing changed", read the full code path **downstream** of
the parameter. An unconditional block later in the same function can discard everything the
knob influenced and substitute its own behaviour, so the sweep measures nothing while
producing a clean, plausible null.

The tell is a value that returns **byte-identical results for every setting**. Genuine
no-effect parameters still perturb something; exact equality across an entire sweep means the
output is being overwritten, not that the knob is neutral. Find the real trigger — often a
hardcoded threshold — and report that the parameter was never the lever rather than that the
idea failed.

## The sample-size trap

Before accepting any "X improves/regresses Y" verdict, compare the **effect size against
the spread across units**. If the per-unit standard deviation is an order of magnitude
larger than the effect being measured, the verdict is noise and the sign will flip when the
sample changes. This is the failure that quietly invalidates small benchmark suites:
identical code can measure negative, positive, and negative again as n grows.

Rules that follow:

- **Measure the cost of a bigger sample before defending a small one.** Runs are often
  seconds each; a suite ten times larger is frequently minutes of wall time. Cheap
  measurement means there is no excuse for an underpowered verdict.
- **Report a confidence interval, not just a mean.** A paired bootstrap over the per-unit
  deltas is enough. An interval spanning zero means "not shown", and must be stated that
  way even when the point estimate is favorable.
- **Count how many units actually changed.** An effect concentrated in a handful of units
  and diluted across the rest is a different, weaker claim than a broad shift — say so
  explicitly, with both numbers.
- **A prior verdict built on too few units is void, not merely uncertain.** When the
  original failure finding evaporates under a larger sample, the correct report is that the
  premise was wrong — including the part where you accepted it.

## Designing acceptance criteria under noise

When effect size sits below the noise floor, "every unit must not regress" is unsatisfiable
by any real change, and "the mean must improve" is a coin flip. Split the criteria:

- **Hard gates guard against regression**: no unit drops more than a set percentage; the
  worst unit stays above a floor; the number of units whose behavior changes at all stays
  bounded.
- **Soft gates track improvement**: mean and median at least match the baseline.

Publish the expected reproduction values (mean, median, the exact list of changed units and
their deltas) inside the criteria. That turns acceptance into an equality check a worker
cannot argue with, and catches an incorrect implementation that happens to score well.

## Reporting

Lead with whether the claims verified and how you checked. Give the reproduced numbers, not
the worker's. Name the residual weaknesses — narrow margins, intervals containing zero,
small numbers of affected units — next to the pass, because the worker's own summary will
not.
