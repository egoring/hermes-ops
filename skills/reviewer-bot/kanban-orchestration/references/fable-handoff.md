# Handing a question to fable-bot (independent opinion / check)

User-agreed principle (2026-10-21): give fable all the information, withhold the conclusion,
ask for its judgment. Fable is an independent checker, not a devil's advocate and not a rubber stamp.

## Contents

- Card body: as detailed as possible on information
- Withheld until fable writes its own conclusion
- Requested output
- "Finish everything, then 최종점검"
- Afterwards
- Final-check handoff (independent-model checker)

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

## Final-check handoff (independent-model checker)

Only when the user asks for a final check. In the card body:
- Pin the artifacts by hash (md5 of each kernel/script file) and the git HEAD. If another live
  card edits the same builder or source tree, name it, and say that a hash mismatch at check
  time is itself a defect.
- List the pass criteria numbered, taken from the project rules and the spec. List what you
  already verified and, separately, what you did not verify, so the checker re-derives the
  first and digs into the second.
- End with the report format: per criterion met/unmet/unverified with numbers, severity per
  defect, risks in resource units. Say the checker does not decide.
**While a final check runs, keep the independent work moving.** This user asks "what does not
need the check result?" right after dispatching one. Answer (or pre-empt it in the dispatch reply)
with two lists: items no pass criterion of the check can change — read-only analyses, assets every
branch needs (e.g. an offline wheel Dataset), facts only the user can read (quota screen) — and
items that wait on a named criterion. Offer one coder card for the first list (no GPU box, no
submit, no decisions inside it), and forward any fact the user supplies meanwhile to the running
check card as a comment.

**"Wouldn't a final check say the same?" about a plan or strategy:** when the checker model
authored the plan (a second-opinion or design card), re-checking it with the same model is not
independent. Say so, list which of its numbers you recomputed yourself and which parts nobody
can verify before results exist (subjective probabilities, approximations), and recommend
putting the final check at the first artifact that will be submitted, where there is code,
runtime and output to re-derive. Offer it now anyway if the user says the word.
When the user says "final check, then submit" in one message, the submit is pre-authorised
conditionally: write into the card body that the orchestrator submits if the report has 🔴 0
and asks again otherwise. When the report returns with 🔴 0, re-hash the kernel file against
the pinned md5, confirm the kernel status is COMPLETE, submit once, and report the check
summary and the submission id together.
The same holds for "submit if the review passes" on an implementation card: post a comment on
the card recording the user's conditional decision and the exact submit procedure (gates:
COMPLETE, gate lines in the log, remote md5 = local, UTC-day count; the exact `submit -k ... -v`
command and message; add the ref to the score watcher; "on request-changes, do not submit"),
because the dispatched reviewer run of your own profile, not the chat, will hold the verdict.
Keep "worker submits 0" in the body so the coder never submits.
**"Submit right away when fold 0 is good" on a member the submission kernel loads as K folds.** A fold-0 checkpoint swapped into a K-fold slot changes two variables (the data change and the fold count), so its LB result cannot be read. Explain that fold 0 is a gate, not a submittable artifact. Record the pre-approval on the card as conditional gates: fold-0 gate passed (reviewer-recomputed), all K folds trained, kernel diff = weights only, push COMPLETE, then one mix submit plus one standalone measurement submit. Give the ETA of the earliest real submit.


When the user says "final check, then proceed" without the word submit, chain it overnight but
keep submission for the morning ("proceed" is not a submit instruction):
1. Create the implementation card (judge → build → push, no submit), then `kanban schedule <id>
   "<what it waits for>"` so it cannot start before its input exists (e.g. a training queue still
   running).
2. Create the final-check card with `--parent <impl_id>`; it sits in `todo` and the dispatcher
   starts it when the parent completes. Its body must cover both parent outcomes: gates failed
   with push 0 → a short re-derivation report only; pushed → the full check against the hash
   table the parent was told to put in its doc.
3. A cron checks the precondition by reading the last status line of the remote log plus a
   process count, and only then runs `kanban unblock <impl_id>`; otherwise it does nothing. When
   the input-ready time is known, a one-shot at that time is enough. When it is uncertain (a
   multi-variant queue whose last stage has no measured speed), use a recurring cron (e.g. every
   30 min) whose first step is "if the card is no longer `scheduled`, print nothing and exit", so
   it stays silent and cannot double-release. Subscribe both cards with `wake`. If the user asks
   for status and the precondition is already met, unblock it yourself right away instead of
   waiting for the next tick, and say so.
4. In the reply, say plainly that nothing will be submitted and which word the morning needs.

When the user says "final check first, then proceed" about a **design** (before any code exists),
check the design itself, not an artifact:
1. Create the design card for yourself with the full spec body and `complete` it at once (result =
   one line: "draft fixed, waiting for final check").
2. Create the checker card with `--parent <design_id>`, `--max-retries 3`, subscribed with `wake`.
   Its body pins the spec file and the hashes of the files the spec promises not to touch, lists
   what you already measured (so the checker re-derives it), numbers the pass criteria
   (single-variable, gate thresholds vs the existing per-fold distribution, selection rule free of
   the hold-out, regression testability, train **and** submission-runtime budget, queue predicate
   safety), and adds opinion questions that state your stance as a claim to rebut.
3. Do not create the coder card yet. On 🔴 0, create it from the same spec with `--parent
   <design_id>`; on any 🔴, revise the spec first. Running jobs on the shared box continue; the
   checker body makes the box read-only.
   When a second design shares the training code or cache with a design whose check is still
   open, do not open a second checker card. Create the new design card, `complete` it, and post
   on the open checker card a comment naming the spec path, the review points as numbered
   items, and "report the two designs' 🔴/🟡/🟢 separately". A shared trainer then gets one
   check, and the two verdicts stay apart.
4. Adopt the checker's 🟡 that change a threshold, a test procedure or a branch rule before the
   coder card exists, not in review: write them as a numbered "amendments — this section overrides
   the sections above" block (each with the evidence you re-derived from the checker's output),
   append it plus the request-review loop to the spec file, and create the coder card from the
   concatenated file. Post the same list as a comment on the design card. Threshold changes made
   here are still pre-result, so they keep the pre-registration valid; keep the original wording
   in the doc next to the new value. Items needing a user decision (e.g. spending the remote platform GPU on a
   side measurement) stay out of the card and go to the user.

When the report returns, read the full run summary from the board DB (the `result` field can
be a one-line stub). The checker's structured report (criteria, defects, opinion, unverified)
is usually the `metadata` argument of its own `kanban_complete` tool call: read it read-only
from the checker profile's `state.db` (`select tool_calls from messages where tool_calls like
'%<task_id>%' and tool_calls like '%kanban_complete%' order by id desc limit 1`, then parse
the JSON arguments). If neither that, `task_runs.summary` nor `task_comments` carries the defect list
(the summary may only count "🔴 0, 🟡 1, 🟢 2"), read the checker's own last assistant message
from its profile's `state.db` (`select content from messages where role='assistant' and content
like '%🟡%' and content like '%<artifact keyword>%' order by id desc limit 1`). Do not report a
🟡 you have not read as "to be checked later". Re-verify each 🟡 yourself against the code, and
say which ones you will handle operationally. Give an advisory recommendation that names its trade-off, and @-tag the
user for the decision.

**"Final check, and ask fable's opinion too" is one card with two halves.** Keep the numbered
pass criteria, then add numbered opinion questions, each stating your current recommendation
as a claim to confirm or rebut with numbers, the candidate options to rank, and "end with one
line: checker's advisory pick = X, reason = Y". When the checker disagrees and backs it with
external evidence (a public bundle, a scored notebook), open that evidence yourself before
relaying; if it holds, say in the reply which of your earlier recommendations was wrong and
adopt the corrected one as yours, rather than presenting two competing opinions.


### Second-opinion card ("ask the other model what it thinks")
When the user asks for the checker model's opinion on direction (not a final check), give it
the same assignee but an opinion-shaped body. Put no time cap and no "keep it short" in it:
this user wants depth over speed for strategy cards. Instead, name the raw artifacts it must
recompute from: our OOF and hold-out prediction files (inter-member Spearman, per-label
weak spots), the scored notebooks' blend cells, the borrowed bundle manifests. Allow long
reports split over several comments. The body holds the situation with every number and its file,
**your current stance as numbered claims it must confirm or rebut**, the concrete questions
(next-step design with numeric criteria, why a past approach failed, ranked paths with cost,
defects you missed), and "no code, no cards, no submit, does not decide". If a long job is
running on a shared box, make the box read-only for it (read files only; start/stop nothing).
**"Is there anything more we can do with X?" (a resource the user has decided to keep, e.g. an
external dataset).** Shape the body so the answer is a ranked, priced list rather than a debate:
- Open with the user's fixed premise ("we keep using X; host ruling Y") so the checker does not
  re-litigate it.
- State the current use of X with measured numbers, including any null LB result and the label
  or member weak spots, plus the hard constraints: freeze date, which box is busy until when,
  quota, the submission kernel's remaining runtime headroom, and the data-handling rules.
- Give candidate directions as examples "not limited to" (other releases or visits, unused
  label fields, self-supervised pretraining, a different backbone for decorrelation,
  pseudo-labelling, auxiliary targets). Require for each: expected ΔA and ΔLB with the
  reasoning, expected correlation with the current base, box GPU hours, quota hours, download
  size and time, added inference seconds in the submission kernel, feasibility before the
  freeze, failure risk, and rule conflicts.
- Ask why the measured effect of X vanished in the blend and what would have to change for it to
  survive (answered from principles, never by tuning on the LB or the small hold-out).
- Ask which in-progress runs on X should be stopped, then for a ranked top 1–3.

When it returns:
- Read the full report from the comment it names (`task_comments` in the board DB), not the
  one-line result. Recompute its headline numbers from the raw files.
- If it computed results before a criterion was fixed, any criterion set afterwards is post
  hoc; keep the pre-existing project threshold.
- Agreement between two models is not evidence. Test its load-bearing claims ("X is not worth
  it", "break-even needs score Y") against external data such as public notebooks before
  adopting them, and say which ones failed.
  **When the user forwards the checker's proposal and asks "shall we do this?", answer it piece by piece.**
  - Adopt the parts your own measurements already support: target resets, cancelling a retrain, GPU order.
  - Test the load-bearing premise against a with/without pair you already hold before you agree to a new card. Example: a per-label gain the proposal assumes.
  - If the premise fails, do not reject the proposal outright. Convert it into a pre-registered condition on the card already in flight ("proceed only if ≥ 2 of these labels gain ≥ +0.02 at fold 0"). Post that condition as a comment on that card.
  - Ask the user only about the leftover optional items, each with its cost.
  - Implement "go ahead only if it does not touch running resources" as ownership lines in the new card: no box GPU or RAM, quota only, push cap.
  A causal explanation for a failure ("the stage cost
  was underestimated 3×") counts as a load-bearing claim: relay it to the user as a hypothesis
  plus the measurement that would test it, never as the cause. Acting on an untested cause
  pointed the next design at trimming compute when the measurement later showed compute fit.
- While the card is still open, forward new evidence to it as a comment rather than waiting
  for its report. Examples: a score that just landed, or a memo the user shared. Give the
  file path, list the claims, and mark which ones you have already refuted with numbers.
  Ask the checker to confirm or rebut each one in its report. A report written without that
  evidence must be redone; a comment costs nothing.
- **Run `kanban show <id>` before forwarding.** If the card already reads `done`, nobody will
  read the comment. Reconcile the report yourself instead: read it, mark which of its
  conclusions the new evidence confirms or changes, and post a correction comment for the
  record. Any statement of yours that the report proved wrong (e.g. a fact about our own
  code) gets an explicit "[reviewer correction]". Then tell the user which points of the
  report still hold.

### Design delegated to the checker model ("let fable design the next step")
The checker still writes no code and creates no cards; its deliverable is a design document.
- Body: the situation with every number and file, the open question (e.g. a collapsed run to
  diagnose), the design template it must fill (one-line summary, evidence, single-variable
  variant table with tag/out path/time, run order within the overnight budget, pre-fixed numeric
  gates with a multi-comparison margin, "no passer is valid", contamination note, honest pass
  probability), and "post the design as card comments, then complete; the box is read-only".
- Create it with `--parent <judging card>` so it starts only after the results it must react to
  exist, and write both result branches into the body (something passed / nothing passed).
- When the judging card returns, add a comment to the design card with any pattern you saw in
  the results, framed as "confirm or rebut", not as a conclusion.
- On return, review the design like any spec, then turn it into the coder card yourself;
  execution still waits for the user.
- When the user approves ("do both"), write a design-final card for yourself with
  `--parent <design card>`: cite the design's comment ids, list the claims you accept, the
  claims you correct with your evidence (e.g. a public score it called unverified that you
  read on the page), and any scope cut (e.g. "judge only, no blend kernel this phase").
  `complete` it, hang every coder card off it, and chain any final check with
  `--parent <impl card>`. Write the machine/quota ownership into each parallel body, and
  delete the previous phase's one-shot release cron once its card has started.

