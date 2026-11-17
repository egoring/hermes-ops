# Checks before relaying or reporting worker output

Load when writing a status report, when a helper-bot card blocks, or when a collection card returns numbers.

## Status reports
- **List every card that changed state since the last report** (`kanban list`, then `runs <id> | tail -1` for each card you mention). Review workers approve and complete cards between your turns, so a card last seen `running` may already be `done` with a result the user has not heard. Report that result first, recomputed from its artifacts, instead of describing the card as in progress.

## Routing collection work
- **Mechanical collection that needs a script (batch CLI calls, metadata sweeps over dozens of refs) goes to coder-bot ending in `kanban_complete` with no review, not to helper-bot.** helper-bot handles single queries and blocks with `needs_input` when a loop or script is required.
- If a helper card blocks that way: confirm no run is live, comment "no review, complete when done; scripts only under $TMPDIR, do not commit", `assign <id> coder-bot`, then `unblock <id>`.

## Scraped numbers
- **Sanity-check every scraped number against a known bound before using it**: a score above the current leaderboard top, or a licence field "missing" on most rows, means the collector read the wrong field (a version number in a title, the wrong JSON key), not that the data is unusual.
- Spot-check one or two refs yourself (verification, not authorship), then send a fix card that names the exact field to read and the bound to check, plus a completion item that tests it ("no score above 0.70").

## Attributing recommendations and scoping checker cards (step 6)

**Attribute every recommendation to its source.** When a second-opinion or final-check
report comes back, keep three things apart in the reply: the checker's own one-line advice
(quote its "advisory" field), your own recommendation, and anything you derived from the
checker's findings but the checker did not say. This user asks "is that the checker's
recommendation too?" when they blur. If they differ, say so and offer to put your variant
in front of the checker on the next check. Because he weighs the checker's view, ask for it
explicitly in the check card: "for each question give your own judgment and
recommendation (advisory), say where you disagree with the reviewer and why with numbers,
and end with one line `checker advisory: <choice>, reason = <one line>`".
**"Has the checker seen all of this?" — answer from the board, then scope the delta.** List every final-check card that completed (id, finish time, verdict count such as 5/6) and every card deployed after the last one. Do not answer from memory. When he then asks for the check, scope the card on that delta plus every criterion the last check left unmet. The body needs these parts:
- the decision it feeds;
- the exact live target (image id, StartedAt, HEAD, prompt sha, rollback tags, and what the live data currently is, e.g. a test pack);
- numbered criteria taken from the project AGENTS.md;
- "already verified by reviewer, recompute independently", with your numbers;
- an **accepted-limits list**, so known residuals are not re-reported as new defects;
- the user's pending decisions to evaluate as risks (e.g. a backend switch not yet rehearsed);
- a no-side-effect list matched to what he is doing now. If he is live-testing, that means no restart, no data reset (dry-run only) and a capped number of CLI calls on a temp copy.

When he asks to put a question to the checker ("fable한테 물어봐줘") and the main final-check
card is still gated behind later cards, create a **separate, ungated** check card for that
question now. A comment on the gated card would be answered only after the decision it
feeds. Give it your own findings as "verify or refute", the areas to extend into, and the
output shape (likelihood, impact, evidence, prep type, priority groups). Then post the
routing line.
When the question is strategy with no artifact to check ("which direction should the agent take?"), title the card as an opinion, not as 최종점검, and say in the body that the user named the checker. Ask for ≥3 compared options plus one advisory pick, the conditions that would switch the pick, each capability claim backed by file:line or a test, and facts kept apart from guesses. The report goes to the checker's scratch, with the five-line core in the summary. Point it at the prep docs it already reviewed, so it builds on them instead of rewriting them.
