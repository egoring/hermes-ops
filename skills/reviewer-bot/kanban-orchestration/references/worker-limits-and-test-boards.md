# What a kanban worker cannot do, and how to write cards around it

Read before writing a card whose verification creates kanban activity, needs a human step, or waits
on a user prerequisite.

## Workers cannot mutate Kanban through the CLI
A kanban worker's env carries `HERMES_DELEGATED_CHILD_CONTEXT`, so `hermes kanban boards create` and
`hermes kanban --board X create|comment` are refused on every board ("delegate_task child contexts
cannot mutate Kanban tasks via the CLI"). The guard is correct; never allow `env -u` around it.

A card whose measurement needs synthetic kanban events (temp boards, card/comment bursts, latency
trials) must say, in the body:
1. The worker writes one driver script (e.g. `docs/<topic>/measure_run.sh`) that does every kanban
   mutation, the scenarios, raw-data output and the final cleanup, with a `--dry-run` mode (zero
   writes, prints the plan). Long observation windows run inside the script under `nohup`.
2. The worker passes dry-run + syntax checks (`bash -n`, `py_compile`), then hands off with
   "reviewer run pending". If the card has already blocked once, the hand-off must be
   `kanban_schedule` (with a SCHEDULED_UNTIL margin), not a second block (see below).
3. You run the script from the Discord session (no guard there) as a tracked background terminal
   process (`nohup`/`setsid` wrappers are refused), then unblock or let the schedule wake it.
4. The worker judges the criteria from the raw data and requests review.

If a worker already blocked on the guard, it was a spec error: say so in a comment ("spec
correction, not a rejection, 0/3") with the steps above. It does not count as a round.

The same worker terminal guard refuses `hermes update ...` (even `--check`/`--plan`); run those
read-only commands yourself and attach the output.

## A second block on one card triggers auto-decomposition
The 2nd `blocked` run on the same card fires `block_loop_detected` (limit 2). The auto-decomposer then
splits the card into children that re-run already finished work. On 11/09 <카드> got 4 children,
and 2 of them ran before they were caught. Rules:
- Card bodies say "block at most once on this card; waits use `kanban_schedule`, judgement calls go
  in the `request-review` summary."
- If a card was already decomposed: archive the children that have not run, `unlink <child> <root>`
  for each, and comment any running child to complete as a duplicate without code changes.
  Schedule the root first, so it does not dispatch again the moment it is unlinked.

## Temp test boards
- Cards on a temp board get no assignee and `--initial-status blocked`. An assignee makes the
  dispatcher spawn a real, billed worker.
- Always pass `--board <tmp>`; never `hermes kanban boards switch`, because the current board is
  shared CLI state for every session.
- Completion evidence: `hermes kanban --board <tmp> runs` shows 0 runs, and the board is removed
  (`hermes kanban boards rm`) at the end.
- A dashboard may hide boards by name pattern (e.g. a `_tmp` suffix treated as archived). Check
  before relying on a temp board appearing in a UI test.
- Fixture DBs (fake sessions/state.db) live under `$TMPDIR`, never in `~/.hermes/profiles/`: the
  multiplex gateway tries to serve any directory there, even one without `config.yaml`, and logs
  ERRORs. The reader takes an opt-in extra path (default off). The card's evidence includes
  `grep -c <fixture> ~/.hermes/logs/gateway.error.log` and `ls ~/.hermes/profiles`, unchanged
  before and after the run.

## Cards that wait on the user
- A prerequisite only the user can do (install an app, log in, flip a console setting): create the
  card with `hermes kanban create ... --initial-status blocked`, comment the user's steps, and
  unblock when he reports done. For a design→implementation pair the child can be created blocked
  with `--parent <design_id>`.
- A human step in the middle (typing a password into a script, an interactive prompt): write it as
  one planned block with the exact command to run. The bot never asks for, receives or prints the
  secret; it verifies only non-secret evidence (hash prefix, field empty, length).
- Subscribe the thread with `wake` only when the card ends in a user decision; intermediate cards
  get `notify`.
