# Statistical hygiene for benchmark work


- **Re-run the headline measurement yourself on inputs the card never touched.** Recomputing from
  the worker's raw artifact only proves its arithmetic; it cannot catch a biased input set. The
  strongest findings of several sessions came from drawing fresh inputs and getting a materially
  different number — approve the execution, then correct the conclusion.
- **Never accept an evenly-spaced parameter sweep as the evidence base.** Strided seeds/IDs
  select a correlated slice of the space and inflated a win rate three separate times here
  (90% -> 67%, 96% -> 73%). Require inputs drawn with a seeded RNG, pin the list in the card, and
  make the worker report a zero intersection with previously used values.
- **Calibrate every CI gate against a null pair before putting it in a card.** Recompute the gate on two runs that differ only by seed (same config): if that pair already fails it, the gate cannot pass for any real comparison. A "ΔG CI lower bound > −0.010" gate on a 58-study gold set failed for a seed-only pair (CI [−0.018, +0.011]), so it was a coin-flip gate; judge single-fold A/Bs on the low-variance metric and keep the small set as a report-only guard.
- **The same applies to "behaves identically" gates on GPU code** (e.g. "feature ON vs OFF, loss |Δ| ≤ 1e-3"). fp16/cuDNN runs are not bit-reproducible: two identical-config smoke runs differed by 0.002–0.028 in epoch-1 loss, so the worker burned runs chasing a gate it could never meet. To prove a side-effect-free addition (checkpoint save, logging), gate on a deterministic check instead: assert the RNG states (python/numpy/torch/cuda) are byte-identical immediately before and after the new code, plus identical loss up to the point the new code first runs. Report the ON/OFF loss gap only as a reference number. If such a gate is already in a running card and the worker is looping, correct it in a comment at once and own it as a spec error.
  The same holds for "output sha equal to the previous run" gates on a multi-GPU inference kernel after any change to scheduling (chunking, worker count): write the gate as rank equivalence plus a metric Δ bound, and keep byte equality only for stages the change does not touch. A worker that follows a byte gate literally stops a push that was fine.
- **Set a new model's adoption gate from the strongest existing comparable member on the same metric and label source, not from the baseline the plan names.** A gate of "baseline + τ" that sits below a member we already have (0.8781 vs an existing 0.8792) passes a model that adds nothing. List every member's value before writing the threshold. In the same spec, fix the checkpoint-averaging epochs in advance (e.g. the last three) instead of "top-k epochs by OOF", because choosing epochs on the evaluation fold biases the gate it is judged by and the all-data run has no fold to choose on.
- **Calibrate per-fold auto-stop gates against the same fold's baseline, never a single absolute value.** CV folds differ in difficulty: a "stop the queue if A_fold < 0.85" gate, set from fold0 (0.870) minus a margin, halted an overnight 4-fold queue on the hardest fold (ViT baseline there 0.812 vs 0.836–0.839 elsewhere) although the new model's gain on it (+0.034) matched the other folds (+0.031, +0.033). Gate on Δ vs the baseline's same fold (e.g. Δ ≥ 0, or ≥ half the fold0 gain), and when an absolute gate does fire, check that Δ before treating it as a failure.
- **Several experiments that each need trainer changes → one experimental trainer copy with default-off flags, not one edit per experiment.**
  - Leave the frozen trainer (the one shipped in the kernel) untouched. Copy it once and add flags for every planned experiment.
  - The default path must be bit-identical to the original: no new RNG calls on it, and the original loss line kept as it is.
  - Prove it once on CPU before queueing: step-loss and EMA max|Δ| = 0.0, same thread count for both runs, `nice 19` on a box whose GPU queue is busy. Add a grep showing that every added RNG call sits inside a flag branch, because a CPU test cannot see CUDA RNG.
  - One checker round then covers all experiments, and every later run is argument-only.
  - Things to spell out in the spec, since checkers caught each of them:
    - **Masked or weighted losses:** write `(w*bce).sum() / w.sum().clamp_min(eps)`, plus a unit test on an all-masked batch. A graph-detached 0 crashes `backward()`, and an all-masked batch is likely over a few epochs, which kills the queue.
    - **Judge scripts:** copy helper functions instead of importing them from another record script. Scripts with module-level argparse and no `__main__` guard run their whole report, and exit, on import.
    - **New queue's kill and wait patterns:** they must match the new trainer's path. Patterns copied from the old queue miss it, which silently disables stall and EP0 guards.
    - **Flag plumbing:** trace every new flag to the function that consumes it through every call path, e.g. an aug flag stored as a model attribute so `forward()` passes it on and the EMA deepcopy inherits it. A flag parsed but never reaching the transform makes the arm a silent copy of the baseline.
    - **Fine-tune continuation arms** (init from a baseline ckpt): give both arms the same new seed. Re-using the baseline's seed replays the baseline's first-epoch shuffle and windows.
    - **Augmentation ranges:** state them in image-side units. `affine_grid` translation lives in [−1, 1] coordinates, so t = 0.20 shifts by ±5% of the side, not ±10%.
    - **Weighted samplers with replacement:** compute the expected unique-study fraction and the per-label positive exposure per epoch before fixing the weight (w 3 left 41% of draws as duplicates; w 2 was gentler). Re-derive the rare-label set from the actual train-fold prevalences, because a round threshold can exclude the very label the arm was meant for.
    - **Auxiliary metric for a loss-mask arm** (e.g. AUC on explicit cells only): print each label's cell count next to it. A label with ~100 cells adds its own bootstrap SD to the mean and inflates τ, so pre-register the full mean as the gate and the mean without that label as report-only.
- **Pair an uninterpretable single-variable arm with its control in the same queue.** A bigger batch at a fixed lr cannot tell "batch does not help" apart from "lr was not rescaled", so run it next to the lr-scaled twin. A fine-tune continuation that adds a loss mask needs a same-steps, no-mask continuation, so that "trained longer" is separated from the mask itself. Do not chain a new queue by editing the running queue script, because bash reads scripts incrementally. Copy it and add `^bash analysis/run_<prev>.sh` = 0 to its wait predicate.
- **Design a multi-arm fold-0 screening queue so every arm differs from the baseline in exactly one variable.**
  - Fix the micro-batch for all arms up front (the smallest that fits the heaviest arm, e.g. bs2×accum4) and forbid per-run OOM fallback. A fallback that fires only on the high-resolution arm silently changes batch size too, which voids that arm's verdict.
  - Use the mean of 3 seed reps of the baseline as the reference, not one run. With 4 arms judged against a single baseline run, the family false-adoption rate is ~15–35% at τ = 0.003. Set τ = max(floor, 2.6σ_seed) against the 3-rep mean (≈3.2σ against a single run).
  - Put the seed reps first in the queue, so σ exists before any arm finishes, and put the longest, lowest-prior arm (e.g. 2× epochs) last, behind an elapsed-time skip.
  - Before claiming a pipeline lacks a feature (augmentation, flips), grep that pipeline's own code. A wrong "X has no augmentation" premise reshapes the whole screen.
- **Do not let an unvalidated proxy gate a go/no-go.** An OOF metric computed against one label source is not comparable across models trained on different label sources, so "OOF does not track LB" from such a table is confounded, not shown. Until a same-label-source OOF→LB link is measured, use the proxy only as a bug floor and decide on the LB readout.
- **Anchor pass probabilities on our own base rate before external testimony.** Count how many of our own comparable submissions cleared the bar (k/n, Laplace (k+1)/(n+2)). External "we got 0.95 with X" claims may move it, but they cannot replace it. In one case 0/5 own singles ≥ the bar gave ~14%, while testimony alone had suggested 35–45%.
- **A watcher that parses an append-only log must judge by the last status line.** After a manual restart the old `QUEUE_STOPPED` line is still in the log; a substring search keeps reporting "stopped" and blocks the release forever.
- **A chained queue's start predicate must not match the predecessor's own wait lines.** A waiting queue logs lines like "WAIT for run_16a ALL_DONE ...", so a downstream `grep -qE "ALL_DONE|QUEUE_STOPPED" <upstream log>` is true from the first minute. Only the "no training process" condition then holds the downstream queue back, and it races the upstream queue at its end or in the few-second gap between folds. Exclude the wait lines (`grep -vF " WAIT for " log | grep -qE ...`) or anchor the marker. In the card, require the predicate to be tested on four copies of the log: the current one (false), with `ALL_DONE` appended (true), with `QUEUE_STOPPED ...` appended (true), and 100 wait lines only (false). When reviewing, run the script's own function on those copies (`eval "$(grep '^fn ()' script.sh)"`) and do not trust "it is waiting, so it works".
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
