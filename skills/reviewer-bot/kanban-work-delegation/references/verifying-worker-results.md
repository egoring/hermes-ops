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
   single most common inaccurate claim, and the cheapest to check. When the change is
   embedded (a script inlined as a string literal inside a notebook cell), extract it with
   `ast.literal_eval` and diff that against the original — a diff of the notebook JSON
   cannot show a one-line patch inside an escaped blob.
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
   **Check which interpreter and library versions the worker's dry-run used.** A dry-run
   under the dev venv can pass on an import that the target's (newer or older) library no
   longer has. Require the run to print its key package versions, and compare them with
   the versions the target will install before you accept "dry-run exit 0".
8. **Measured vs derived** — for every load-bearing quantity, ask whether the script
   *observed* it or *computed* it from a formula. Only observed values are evidence; see
   below.
9. **Did the change change the output at all?** — compare the new output against the
   baseline output, not only against a recomputation of itself. See "Plumbing gates on a
   tiny smoke input" below.

## Check what a branch gate compares against

A gate that chooses between variants ("adopt weight 0.6 if its CI lower bound > 0") only means
something when the comparator is the **incumbent setting**. Read the script's paired-difference
line and confirm which arm is being subtracted. A sweep scored against a weak reference, such as
the component-removed baseline instead of the current weight, passes "CI > 0" at every grid
point, so it ranks nothing. The tell is that every variant clears the gate by a wide margin.
When you spot it, bounce with the exact pair to compute (C(w) − C(incumbent), same resample
indices). Leave the branch rule itself unchanged and keep the wrong-reference table only as a
record. Do not let a push the worker already made under the bad verdict count as approval: the
rule is re-applied to the corrected numbers, and that decides whether the push is used at all.

## A baseline that returns nothing is not a comparison

Before relaying "ours beats the baseline by X", count how often the baseline produced
any output at all. A baseline empty on most units turns the margin into a measure of its
emptiness. Recompute the comparison on the units where the baseline is non-empty and
report both. When you wrote the spec, own the weak baseline as a design error. Also
check any absolute floor you set against n: if the observed value sits inside the
binomial CI of the floor, a "miss" is undecidable. Say so, and route it to the user as an
override decision rather than a redesign.

## A reported zero is a claim about a classifier — recount it mechanically

When a worker reports "0 leaks", "0 failures" or "0 violations", recount from the raw
answers with a dumb matcher against the source list. For leaks, strip answers to digits
and match them against every personal number, then substring-match the addresses. Any hit
the worker did not count rests on a judgement ("a farm address is not personal"). Report
that judgement as a policy question for the user, not as a pass. The same matcher
confirms a real zero in seconds, so run it even when you expect agreement.

## Check the headroom of any adopted limit

When a card adopts a cap (output tokens, timeout, memory, batch size), report the
maximum observed value as a fraction of the cap, not just the failure count at the cap.
Above ~80% the margin is thin. Re-probe with inputs heavier than the worker's set before
approving; a cap with 0/30 failures on the worker's set failed on a reviewer-written
question that needed slightly more. A time margin ("max 59 s vs 240 s deadline") says
nothing about the token margin, so check each limit the run can hit.

## Plumbing gates on a tiny smoke input

When the only runnable input is a handful of rows (a competition's visible test, a smoke
fixture), a gate like "recompute == kernel output, max|d| 0.0" proves the wiring and
nothing about the effect. Check whether the new output is identical to the baseline output:
a small-weight rank blend over 3 rows cannot reorder anything, so a blend at any W ≤ ~0.3
returns the baseline exactly. Report that explicitly as "plumbing verified, effect
unobservable here", so a perfect gate sheet is not read as evidence the change does
something.

The same applies to **fail-safe fallbacks**. A design that silently restores the baseline
when the new branch fails (skip on timeout, error, format mismatch) makes an unchanged
downstream score ambiguous: "no effect" and "branch skipped" look the same, and in a
scoring environment whose logs you cannot see, the ambiguity is permanent. Name it before
the user spends a scarce slot on it. When designing such a card, prefer a path whose
success is observable (a variant that cannot be byte-equal to the baseline when it ran,
or a second arm whose expected direction differs), and state the residual ambiguity in the
decision packet when that is not possible.

## Read rewritten text artifacts as bytes, not through the read tool

When a worker rewrites a small text file (counts, id lists, configs), check it with `od -c | head`
or `cat`, not a line-numbered viewer. Workers that read a file with a `N|content` viewer and write
it back can leave `1|`, `2|` prefixes in the file; a line-numbered display hides them because it
adds the same prefix. Add `grep -c '^[0-9]*|' <file>` = 0 to the completion criteria of any card
that rewrites such a file.

## Fail-closed guards: attack every way they can quietly weaken

For a guard the spec says "cannot be turned off" (contamination filter, sha gate, quota
guard), passing its own tests proves little. Before approving, run the bypasses yourself:

- **Override arguments that replace instead of add.** Feed a partial list (e.g. the first 3
  lines of the held-out list) through the override flag; if a held-out item reaches the
  output, the flag replaces the default. Required fix: the default is always loaded, the
  flag only unions, and the default's size and sha are asserted and recorded.
- **Missing or unreadable auxiliary inputs.** Point every secondary input (a file the guard
  uses to derive extra keys) at a nonexistent path and at a copy missing one required row.
  A silent fallback ("id only") that shrinks the key count is the same bug as an off switch;
  require exit 1 with no output written.
- Compare the guard's key count against the full run (e.g. 81 vs 47) — a drop is the tell.
- **Baseline-relative exemptions.** "Skip what the baseline already contains" is fail-open when the baseline itself was never checked. A contaminated ancestor then passes every descendant. Plant the same bad value in both the baseline and the candidate. Require an explicit allowlist with a reason per entry, printed in the output.
- **Inputs the guard cannot parse.** A decode or parse error caught by `except: continue` silently drops the whole input. Inject one invalid byte into each accepted file type. The guard must FAIL that file and print it, not shrink its scan.
- **Spelling variants of a known-bad value.** A matcher that compares whole tokens only catches the fixture's exact spelling. Re-run it with the bad identifier behind a different prefix (`self.X`, `obj.X()`) or before a generic suffix (`X.add`).
- **Test-mode switches.** An env flag that skips part of the checks must not end in the same PASS line or exit code as a full run.

When writing the request-changes text, check the required outcomes are consistent with each
other ("flag only unions" and "partial list must exit 1" cannot both hold); state the
observable result of the intended behaviour instead of two incompatible ones.

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

For latency (or any per-item cost) criteria, compare **paired per-item differences**, not
the set-level p50 before vs after. Different items dominate each set's median, so a
set-p50 of +1.5 s can hide a paired median of +0.2 s when the per-item sd is 2.8 s. Write
the criterion as "paired median Δ ≤ X" from the start. When an old card used set p50,
record the miss under its rule and add the paired numbers as decision info.

Publish the expected reproduction values (mean, median, the exact list of changed units and
their deltas) inside the criteria. That turns acceptance into an equality check a worker
cannot argue with, and catches an incorrect implementation that happens to score well.

## A combination found on the evaluation data is a hypothesis

When your own post-hoc analysis of a failed card finds a variant that clears the bar on the
same rows (two failed graders chained, a threshold picked after seeing the misses), do not
adopt it and do not report it as the result. Open a validation card with the rule
pre-registered, written before any data is generated, and committed. Run it on fresh rows
with **different perturbation families** than the discovery set (e.g. swap names, shift
dates, not only change numbers). Report recall per family. A stage that sees only one
feature type passes the discovery set and fails every family it cannot see. A failed
validation is a valid result: the card ships no tool, and the user decides whether to
override.

## Re-pointing your own probe at a new artifact

To re-run an earlier probe (leak check, edge probe) against a fixed version, edit its input-path constant and **print that constant line before reading the output**. A `sed` pattern that does not match the exact path text leaves the old path in place. The probe then re-reads the old artifact and "finds the bug still there", or worse, passes on stale input. Also confirm that the input's sha or size equals the new artifact.

Keep cleanup (`rm -rf` of probe folders) out of the probe command. Build probes under the auto-pruned scratch dir and leave them. A destructive step chained into the same shell call waits for approval, and on timeout the whole check, including the read-only probes, never runs.

## Reporting

Lead with whether the claims verified and how you checked. Give the reproduced numbers, not
the worker's. Name the residual weaknesses — narrow margins, intervals containing zero,
small numbers of affected units, outputs identical to baseline — next to the pass, because
the worker's own summary will not.

When the next step spends a slot whose score is max-of-selected (leaderboard submissions),
say so in the recommendation: a worse arm cannot lower the kept score, so submitting both
arms of a fixed pair costs only the slots and buys the direction of the effect.
