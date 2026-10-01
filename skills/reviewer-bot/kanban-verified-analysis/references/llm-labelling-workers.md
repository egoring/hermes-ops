# LLM workers as bulk labellers (pseudo-labels from free text)

For cards where a worker model reads thousands of documents and writes a label per document.
The order below is the order you do the work in. Each rule comes with the mechanism behind
it.

## 1. Before the full run: pilot and compare with the incumbent

- Label about 100 items first. Compare prevalence per target, and binary agreement, against
  the incumbent label source.
  - If prevalence differs by a large factor (e.g. 20% vs 60%), or agreement is far below
    what incumbent sources reach with each other, **stop and diagnose before spending more**.
  - The exception: you have independent evidence that the incumbent is wrong.
  - Why: a disagreement this large shows up in unlabelled data long before a gold-set
    evaluation. In one case it predicted a −0.1 macro-AUC loss.
- For an AUC metric, keep graded evidence ordered: clean negative < not mentioned < mild or
  low-grade < definite.
  - Do not import a host definition's severity threshold ("mild = negative") into the score
    mapping unless the gold labels follow it.
  - Why: collapsing borderline findings into the clean-negative score erases exactly the
    rank information AUC measures.

## 2. Limit session length

- Run each labelling session over a short range, roughly ≤13–15 batches of 25 items. Split
  big jobs into parallel cards by **order position** (`--range A B --part K`), each in a fresh
  session.
  - Why: when one long session gets context-compacted, its criteria drift. The drift shows
    up as a stricter or looser segment in the output order.
- Have the labeller re-read the definition file every ~6 batches and right after any
  compaction. Record the definition-file md5 at the start and end of each part.
- Relabel runs **must not read the original labels** (a separate output file, and no reads
  of the original parquet/jsonl). Why: otherwise the model anchors to the labels you are
  trying to replace.
- Report cost per part against both a per-card cap and the cumulative cap. Block the card on
  either one.

## 3. Detect drift by output position

- Split the labelled output by position (A = early, B = suspect, C = late), not at random.
  Compare positive rates for the targets most prone to drift, using a two-proportion z-test.
- Confirm with a blind re-label of ~100 items per segment in a fresh session. Count
  stricter-vs-looser disagreements per segment with a sign test.
- Choose the reference segment carefully. "B vs A∪C" assumes A is clean. If A came from the
  first half of the same long session, A can be the drifted one.
  - Also compute **fresh-session vs fresh-session** (relabelled B vs C) as a secondary
    number.
  - When pre-registering a gate, state which comparison decides it.

## 4. Evaluate once, then freeze

- Evaluate on the gold set **once**, with a fixed variant list (incumbent, new source, mean
  of the two). Use paired bootstrap Δ against the incumbent with Bonferroni over the
  variants.
- Any post-hoc diagnosis of why a source lost (e.g. "gold positives scored as explicit
  negatives") is allowed. A **revised** labeller built from that diagnosis cannot be scored
  on the same gold set, because its G metric is contaminated. So a loss on the one-shot
  evaluation usually ends that label family. Say so, and state the sunk cost.
