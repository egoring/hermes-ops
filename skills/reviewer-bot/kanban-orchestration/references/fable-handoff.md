# Handing a question to fable-bot (independent opinion / check)

User-agreed principle (2026-10-21): give fable all the information, withhold the conclusion,
ask for its judgment. Fable is an independent checker, not a devil's advocate and not a rubber stamp.

## Card body: as detailed as possible on information
- The decision being supported and the numeric criteria it will be judged by.
- Every raw-data location: DB paths + tables, logs, scripts, configs.
- Each number reviewer-bot reported WITH the query/script that produced it (re-run, not re-derive).
- What reviewer-bot already looked at and what it did not (fable should explore the unseen sources
  first; on 10/21 all of fable's new findings came from sources reviewer had not opened:
  per-profile state.db, coder errors.log, incidents logs, worker logs).
- Already-rejected ideas with where they were rejected.
- Constraints/pitfalls: read-only (`sqlite3 'file:<db>?mode=ro'`), processes not to touch, slow
  commands (hermes-agent git is a partial clone: minutes per command).
- Long material goes in files referenced by path; the 170KB incident was `kanban show --json`
  output, not body length.

## Withheld until fable writes its own conclusion
- reviewer-bot's conclusions, interpretation, recommendation: put them in a separate file and tell
  fable to open it only after its own conclusion is written to a file, in the same card (one run).
- Conclusion-first cards anchor fable inside reviewer's frame.

## Requested output
- Its own independent conclusion first.
- Then per reviewer claim: `confirmed / refuted / unverifiable + evidence (query, number)`.
  "No refutation" is a normal, valid outcome; do not ask it to find something wrong.
- "Unverifiable" must say what was missing and how to get it.
- For 2-3 load-bearing claims: state what the data would show if the claim were false, then look.
- Ends with a decision report; fable does not decide.

## "Finish everything, then 최종점검"
When the user asks for a final check of work that is still in flight, create the fable card now
with `--parent <last card of each chain>` (it stays `todo` and starts when they complete), subscribe
the thread with `wake`, and post the 🔀 line with its id immediately. The body lists every card in
scope with artifact paths, the spec cards holding the numeric criteria, any `사용자 결정(override)`
(record it as unmet, not as a rollback argument), items reviewer missed earlier as priority checks,
and what is out of scope (deferred cards). Steps that need kanban CLI writes go in the report as
"needs re-measurement by the Discord reviewer", since the fable worker hits the same guard.

## Afterwards
- A final check covers only the commits that existed when it ran. Fixes made for its 🟡 findings
  (and anything landed after) are review-only until a new final check. When reporting "all done",
  split the list into "final-checked" and "reviewed only", and say whose eyes saw each item
  (review worker, your own measurement, nobody, as for a no-review helper doc card). Offer the next
  final check, and fix any known 🟡 first so one check covers it. The user must say "최종점검".
- Put an unverified deploy↔commit gap in the body as a priority check, e.g. an image tag built from
  the previous HEAD (`<sha>-dirty`).
- Fable's verdicts are evidence, not the conclusion (10/21 its 'high confidence' crash cause had a
  counter-example). Where reviewer and fable disagree, reviewer re-judges that item from raw data
  once; no back-and-forth rounds.
- Log per card: cost, new findings, findings from sources reviewer had not opened, refutations
  that held. 3 cards in a row with nothing new -> keep fable for irreversible decisions only.
- Suggested `--max-runtime 40m`. Scope: design/diagnosis decisions and the user's "최종점검";
  fixed-answer checks (file identity, format) are scripts, not fable.
