# Pitfall: a second block auto-decomposes the card into duplicate children

When a card is blocked twice (recurrences reaches the limit of 2), Hermes logs `block_loop_detected`, moves the card to `triage`, and the auto-decomposer creates 4-8 child cards (`created by auto-decomposer, from_decompose_of <id>`). It makes them parents of the original card. Some children are promoted and **spawned at once**. The children re-do steps the parent already finished, such as re-uploading a remote dataset or pushing a kernel. That can break per-slug push caps and FROZEN limits.

## What to do as soon as you see `routed to triage` or new child cards
1. List them with `hermes kanban --board <b> list | grep -E "todo|ready|running|triage"` and `show <parent>`, which shows the `parents:` line.
2. For each child: `block <child> "<reason>"`. Running children accept block. `todo` children cannot be blocked, so archive them.
3. Kill the workers that are still running. Find them with `ps aux | grep "work kanban task <child>"`.
4. Run `archive <children...>`, then `unlink <child> <parent>` for each child, so the parent no longer depends on them.
5. Check that no external side effects happened. On the remote platform, the lists of your own jobs and datasets should be unchanged.
6. Put the parent back yourself: `block` it with the reason "waiting on user/reviewer", then `unblock` it once the decision is made.

## How to prevent it
- In implementation cards, tell the worker to **comment in detail before blocking** and to avoid a second block on the same card.
- **After a card's first block, every resume comment must say "from now on, for ANY problem, request-review --reviewer reviewer-bot instead of block"**, not only for a repeat of the same error. The recurrence counter is already at 1, so the next block of any kind (e.g. a new API error right after a credential fix) goes straight to triage and spawns children within seconds. Cards that call an external paid API or need a user-side setup step are the usual case: write this rule into the body from the start.
- When you unblock a card after a decision, write the decision as a comment first, so the next worker run has it.
- **A reviewer run of your own profile can also block.** On a card whose recurrence counter is already at 1, the dispatched review run may call block to "escalate a user decision". That block sends the card to triage. Your chat comment telling it to run `request-changes` does not stop this. While a user decision is pending on such a card, do not leave a review run holding it. Before you write the decision options in chat, make the card wait with `reopen-review` + `schedule` yourself.
- **A triage card with no decomposed children cannot be moved by the CLI.** `block`, `unblock`, `promote` and `schedule` are all refused, and `assign` alone does not move it. Do not wait for the decomposer. Use this path, which worked:
  1. Kill the worker.
  2. Comment "archived, not an implementation defect" on the card and archive it.
  3. Create a continuation card with the same `--parent`. Its body is a header plus the original spec. The header lists the finished commits and files, and the cumulative spend. It states the user decision, and "never block; use request-review".
  4. Subscribe the new card with `wake`, and confirm with `ps` that exactly one worker is running.
- `promote` works only for `todo` or `blocked` cards. `unblock` fails on `todo` or `triage` cards. After the decomposition is removed, a `triage` card can be blocked or unblocked again.
- A card linked as a parent of a card that is designed to stay `blocked` holds the child in `dependency_wait` forever. Use `unlink` when the link was only for reference.
