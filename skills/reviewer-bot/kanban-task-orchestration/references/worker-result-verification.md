# Verifying a Worker's Result Before Relaying It

A completed card's summary is a claim, not evidence. Workers report their own success,
and a plausible-sounding summary is exactly what a fabricated or mistaken one looks like.
Verify first, then report.

## Procedure

1. **Confirm the artifact exists** at the path the card promised, and check its mtime is
   consistent with the run. A summary describing a document that was never written is the
   cheapest failure to catch.
2. **Find the raw data behind the headline numbers.** Working files often land outside the
   workspace (a scratch dir such as `/tmp/...`); the spec or summary usually names the
   location. Analysis whose inputs cannot be located is unverifiable — say that rather
   than passing the numbers along.
3. **Recompute the headline figures yourself** from the raw data, in your own code. Do not
   re-derive them from the worker's own tables.
4. **Anchor against a value you already knew** before the card ran — a baseline figure
   from an earlier run, a count stated in project docs. If the recomputation reproduces
   the known anchor exactly, the pipeline is real; if it cannot, stop and investigate
   before reporting anything else.
5. **Check the mechanism claims, not just the arithmetic.** If the card was told to expose
   toggles or modify specific code, grep for them. Numbers can be right while the method
   described to produce them is not what happened — a copy of the module patched in a
   scratch dir is legitimate for read-only analysis, but only if the report says so.
6. **Re-read the prohibitions section of the card** and confirm none were violated —
   production code left modified on an analysis card, rejected approaches re-proposed.
7. **Give judging and gate code negative controls, not only reproduction checks.** For a
   verdict/adopt function, feed a known failure (an optional criterion set to fail, the
   candidate and baseline swapped) and require FAIL. For a format checker, feed a bad label,
   a duplicate id and a null, and require FAIL on each. Matching the expected numbers only
   shows the gate passes good input, and a gate that never fails stays invisible until it
   waves a bad candidate through. Run whatever the worker said it could not run.
8. **Check that a stress test exercises the branch it claims to test.** After the
   perturbation, print the property the method keys on (group size, row count, threshold).
   One injection grew groups past the method's size limit, so those groups went to the
   fallback path. The "robust" verdict for that variant then measured the fallback, not the
   variant. A faithful implementation of a broken test is a spec defect: approve it, open a
   follow-up that replaces the test, and mark any choice made from it as provisional.
9. **Read the gate's return value, not only its printout.** A verdict function can print
   "not final" while returning `adopt=True` when optional criteria are left unset. Tell
   downstream cards to pass every applicable criterion explicitly.

## Reporting

- Lead with what you verified and how, before the worker's conclusions.
- Carry the uncertainty forward. If a recommendation's confidence interval includes zero,
  or the effect only appears in a small subset of runs, state that where the
  recommendation is stated — not in a footnote. "Probably not harmful, possibly slightly
  better" is the honest summary of a wide interval, and it is more useful than a clean
  number the next decision would be built on wrongly.
- Name what you could not verify, explicitly.
- When verification shows the worker did good work, say so plainly and move on. The point
  of the check is calibration, not suspicion.

## When the worker's finding invalidates the premise of the card

A good analysis card sometimes proves the question was wrong — for example, that the
measurement which triggered the whole chain was noise. When that happens, say it directly
and retract the earlier conclusion, including your own. Do not let the original framing
survive in the follow-up cards; re-examine every downstream card still on the board for
the same invalidated assumption before letting it dispatch.
