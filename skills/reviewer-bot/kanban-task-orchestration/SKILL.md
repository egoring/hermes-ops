---
name: kanban-task-orchestration
description: "Chain Hermes kanban cards for other bot profiles."
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, multi-agent, delegation, task-board, orchestration]
---

# Kanban Task Orchestration

Creating, chaining, and handing off work cards on a Hermes kanban board so another
profile (coder-bot, reviewer-bot, helper-bot) can execute them unattended.

The bundled `hermes-agent` skill (`references/background-systems.md`) documents what
kanban IS. This skill is the workflow for actually driving it.

## Procedure

1. **Orient before creating anything.** The board is shared state with history you did
   not write; a new card that ignores it duplicates or contradicts existing work.
   ```bash
   hermes kanban boards            # which board is current (● marks it)
   hermes kanban ls                # every card + status + assignee
   hermes kanban assignees         # which profiles exist on disk
   hermes kanban show <task_id>    # full body, summary, events, runs
   ```
   Select a non-current board with `hermes kanban --board <slug> <verb>` — the flag goes
   **before** the subcommand. `hermes kanban ls --board x` is rejected as an unrecognized
   argument.

2. **Read the upstream card's `Latest summary` in full, plus any source docs it names.**
   A blocked card's summary carries the previous worker's numbers, file list, and the
   options it offered the user. Writing the follow-up without it produces a card that
   re-asks questions already answered.

3. **Write the body to a file, then pass it in.** Long markdown bodies with backticks,
   code fences, and non-ASCII text get mangled by inline shell quoting.
   ```bash
   hermes kanban create "<title>" --body "$(cat /tmp/card_body.md)" \
     --assignee reviewer-bot --workspace "dir:/path/with spaces" --parent t_xxxxxxxx
   ```
   Quote the whole `dir:` value when the path contains spaces. `--parent` is repeatable.

4. **Verify the card materialized as intended** — `hermes kanban show <new_id>` and
   confirm assignee, workspace, and `parents:` line. `--json` output is long; grep it or
   just re-show the card.

5. **Check the chain can actually run** before reporting success (see below).

6. **Subscribe the chain to the originating chat** so terminal events come back without
   polling. Do this once per card, at creation time.
   ```bash
   hermes kanban notify-subscribe <task_id> \
     --platform discord --chat-id <id> --thread-id <id> --chat-type thread \
     --notifier-profile <your-profile> --delivery-mode wake
   ```
   Fires only on terminal events (done / blocked / failed), not heartbeats.

## CLI argument shapes that differ between verbs

These are inconsistent across subcommands and each mistake costs a round trip:

- `create` takes the body as **`--body <text>`**; `comment` takes it as a **positional**
  argument (`hermes kanban comment <id> "<text>" --author <name>`). Passing `--body` to
  `comment` fails as an unrecognized argument.
- The board selector is `hermes kanban --board <slug> <verb>` — **before** the subcommand.
- `--parent` is repeatable; `link` takes bare ids (`link <parent_id> <child_id>`).

## Steering a card that is already running

When you discover mid-run that a card's instructions are wrong or self-contradictory,
append a correction with `hermes kanban comment` rather than killing the run — the
spawned worker keeps its accumulated context, and the comment is permanent board state
that any re-run will read. Open the comment with a line establishing precedence, e.g.
"this comment supersedes the body where they conflict," and restate the corrected
instruction in full rather than pointing at the paragraph it replaces.

**A comment is not guaranteed to reach an in-flight worker's context.** Say so when
reporting, and plan to reject the deliverable if it comes back ignoring the correction.
Do not claim the running agent "has been redirected."

## Always-on rules

- **A card whose parent is not `done` stays in `todo` and is never promoted to `ready`.**
  Chaining a follow-up onto a `blocked` card silently stalls the entire downstream chain,
  including grandchildren. After building a chain, state explicitly whether it is
  dispatchable and, if not, offer the two unblocking paths: close the parent
  (`hermes kanban complete <id>`) or detach (`hermes kanban unlink <parent> <child>`).
  Never report "cards created" as if that means "work will start."
- **Do not resolve the parent's state yourself when a human decision is pending.** A card
  sitting in `blocked` with `kind: needs_input` is waiting on the user, not on you.
  Recommend the action with reasoning, then stop and let them choose.
- **Never assign blame to the previous worker for a spec's failure.** When an
  implementation matched its spec and still missed the target, the defect is in the spec.
  Say so, and prefer closing the implementation card as complete over leaving it open as
  an apparent failure — the board is a record other agents read.
- **Every card must be self-contained.** The assignee starts with zero conversation
  context: restate the numbers, file paths, constant names, and prior decisions inside
  the body rather than referencing "the discussion" or "as mentioned above."
- **Mirror the existing handoff protocol on the board.** If sibling cards end with
  "`kanban_block` with a summary for user approval instead of `kanban_complete`," the new
  card carries the same clause. Inconsistent completion contracts across cards on one
  board make the board unreadable.
- **Route worker results through yourself, not straight to the user.** Subscribe with
  `--delivery-mode wake` (not `notify` or `notify+wake`) and set `--notifier-profile` to
  your own profile. `notify` pastes the worker's own summary into the chat verbatim, so a
  delegated bot appears to answer the user directly; `wake` hands you the event and you
  report after checking it. The user wants the orchestrating profile's verified account,
  not the executor's self-report.
- **Never relay a worker's summary as fact.** A completion summary is a self-report.
  Before repeating any number from it, open the artifact it claims to have produced and
  recompute the headline figures yourself — see
  `references/worker-result-verification.md`. Report what you verified, and say plainly
  which claims you could not.
- **Match the model to the kind of thinking the card needs.** Cards that decide something
  — designing a spec, attributing a regression, defining acceptance criteria — go to the
  stronger-model profile; cards that execute a fixed procedure — implementing a written
  spec, extracting and tabulating data — go to the cheaper one. Profiles usually already
  encode this (`model.default` in each profile's `config.yaml`); check before overriding.
  Per-card override is `hermes kanban set-model <id> --model <name>`. Downgrading a
  judgment card is a false economy: a bad spec forces a full re-run of every benchmark
  below it, which costs far more than the model difference.

## Card authoring

See `references/task-card-authoring.md` for the body structure, the explicit-prohibitions
section, and how to specify an analysis/tuning card so its conclusions are trustworthy.

## Verifying what comes back

See `references/worker-result-verification.md` for the check to run before relaying any
worker summary, and how to report confidence honestly.
