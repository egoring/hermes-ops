# Kanban review loop — making the handoff actually route

## The reviewer field defaults to nobody

`request-review` takes `--reviewer` as an OPTIONAL argument. Omit it and no reassignment
happens: the task stays assigned to the implementer, and the review dispatch resolves the
reviewer by falling back to the task's current assignee. The implementer reviews its own work
and the event is recorded with implementer and reviewer as the same name.

**Always pass the reviewer explicitly:**

```bash
hermes kanban --board <board> request-review <task_id> \
  --reviewer <reviewer-profile> \
  --summary "changed files / verification method / real numbers"
```

Encode this in three places or it will be dropped: the implementer profile's SOUL.md, the
project `AGENTS.md`, and the loop instruction the designer bakes into each implementation
task body. State the failure mode next to the rule — "omitting it makes you review your own
work" — because a bare flag reads as optional boilerplate and gets skipped.

## Verify routing from the DB, never by asking the bot

Asking a bot "you're reviewing the other bot's output, right?" returns what its prompt says.
Read the events instead:

```bash
sqlite3 ~/.hermes/kanban/boards/<board>/kanban.db \
  "SELECT task_id, payload FROM task_events WHERE kind='review_requested' ORDER BY created_at DESC LIMIT 5;"
```

`"reviewer": null` or reviewer equal to implementer means the rule is not being followed,
whatever the bot claims.

Useful shape of that DB: `task_events(task_id, kind, payload, created_at)` with kinds
`review_requested`, `changes_requested`, `blocked`, `protocol_violation`, `completed`;
`tasks(id, title, assignee, status, started_at, completed_at)` gives per-assignee durations.

## Absence of review events is itself a finding

A board with dozens of completed tasks and almost no `review_requested` rows means the loop
never ran — not that reviews passed. Count the events before judging review quality, and say
so rather than evaluating a sample of one.

## Loop instructions live in the task body

Parent/child links propagate context automatically, but the review round-trip does not. The
designer must write into every implementation task: call request-review (with the reviewer
flag) instead of complete; on request-changes, fix and request review again, up to the round
cap below. Without that text in the body the task ends at "done" and no review happens.

## Bound the loop: severity levels + round cap

"Repeat until approved" has no exit, and every round costs a full implementer run plus a
premium-model review. Put both of these in the reviewer's AND implementer's SOUL.md (and the
project AGENTS.md review section):

| Severity | Meaning | Reviewer action |
|---|---|---|
| 🔴 must fix | spec deviation, bug, failed completion criterion, project-rule violation (missing seat/opponent/measurement conditions) | `request-changes` |
| 🟡 should fix | real but non-blocking | approve + note, or separate follow-up task |
| 🟢 note | style, naming, ideas | mention or skip |

- Only 🔴 justifies sending work back; the implementer fixes 🔴 items only and must not let
  🟡/🟢 expand scope.
- Cap at 3 rejections per implementation task; prefix every reason with `[round N/3]` so both
  bots and the user can see where the loop stands. After the 3rd, the reviewer does not reject
  again — it either writes a revised design task (the spec was wrong) or `kanban_block`s with a
  summary of all rounds and pings the user. The implementer blocks too if it hits a 3rd rejection.

## Scale modes — not every ask needs the full pipeline

Write the routing table into the reviewer's SOUL.md so small asks don't spawn design +
implement + review tasks:

| Ask | Mode |
|---|---|
| review an existing diff/result | review-only: answer directly with 🔴/🟡/🟢, no tasks |
| "spec only" | design task only; implementation task only if asked |
| architecture change / hard bug / escalation | full pipeline, ≤3 rounds |
| routine implementation or analysis | implementer alone, no design stage |
| quick lookup | cheap helper bot |

A few concrete "who takes this" example requests per bot pin the boundaries far better than
abstract role descriptions.

## Decision authority — the pipeline reports, the user decides

A reviewer approval means "criteria verified", not "ship it". Write this boundary into the
project AGENTS.md (its own section) and both the reviewer's and implementer's SOUL.md:

- Submission, replacing the deployed build, and closing a verification are the user's call,
  often made with a separate model outside the fleet. Bots do not conclude "submit this" and
  never run a submission unless explicitly told to.
- The reviewer ends every final review with a decision packet: each criterion with its measured
  number and met/unmet, anything unverified, risks, and a recommendation labelled advisory.
- When the user proceeds below a threshold, record it on the task as `사용자 결정(override): ...`
  and in the project's work log; bots must not reopen or re-litigate it. Without this clause a
  shipped-below-threshold build reads as a rule violation in later audits.
- In the design doc, show the decision stage as a human/external node after review, and when the
  external decider may later join the fleet, record the two integration options: a separate
  decider profile (clear boundary, one more gateway) vs a kanban `decide` stage with a
  `model_override` (no new process, decision history on the board). Either way the decider
  drafts; the user confirms.

## Per-task model pins apply to every run, including review

`--model` (CLI) / `model` (kanban_create) is stored on the task, and the dispatcher adds
`-m <model_override>` to EVERY worker it spawns for that task — the review run after
`request-review` included. So write the routing rule in the designer's (reviewer's) SOUL as:

| Task | Pin |
|---|---|
| coder implementation/analysis | none (profile model) |
| reviewer design/review | none |
| non-design work the reviewer assigned to itself (docs, collection, re-measure) | the mid model — or better, assign it to the implementer |
| mechanical work that ends in `kanban_complete` with no review (move/archive, reformat, list, log summary) | assign to the cheap **helper bot** instead of pinning the cheap model on another bot — its own SOUL then applies. Give the helper SOUL a "kanban chores assigned to you" clause (do it even if it touches files; no program logic; `kanban_complete`, never `request-review`; `kanban_block` if it needs judgment), since a generic "hand off anything touching files" line makes it refuse. Never route reviewed work to it — the review would run on the cheap model |
| implementer task needing heavy reasoning | the premium model (review stays premium too) |
| output feeds a numeric decision | none |

Don't drop the mid model from the table because it is "the default" — the designer's own
non-design tasks otherwise run on the premium model.

Test a routing change on a throwaway board before relying on it:
`hermes kanban boards create <tmp> --default-workdir <scratch dir>`, then one real task with
`--workspace dir:<scratch dir>` and the new assignee. Poll the status, check the files and the
worker's model (`sessions.model` in that profile's state.db), then `hermes kanban boards rm <tmp>`
(it archives, recoverably). The live dispatcher claims `ready` tasks within seconds, so create
any task you do not want run with `--initial-status blocked`.

## Recurring-defect checklist in the project AGENTS.md

When rejects keep citing the same analysis mistakes, turn them into a short "self-check before
implementing" list in the project AGENTS.md review section instead of a new gate script. Build
it from the `changes_requested` texts, not from memory. Let the designer bot draft it into
`docs/` as a kanban task (workspace = project dir, no AGENTS.md edits, `kanban_complete`,
user approval) and have it confirm each claimed helper path exists. Drafts regularly find that
a helper named in a handoff note does not do what the note says. Keep about six items, each
with example task ids and the helper path, and require a "n/a / done" line per item in every
review request. Demote writing-quality defects (prose contradicting a table, unreproducible
derived numbers) to one-line 🔴 examples; a long list gets skimmed and weakens the core items.

## Report honestly when the numbers are bad

An implementer that hits its own completion criteria on only some seeds should say so in the
review summary and let the reviewer decide whether the SPEC was wrong. Faithful implementation
plus bad results is a spec problem, not an implementation failure — the fix is a revised spec
with corrected numbers, not another blind implementation round.
