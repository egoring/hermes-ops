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
