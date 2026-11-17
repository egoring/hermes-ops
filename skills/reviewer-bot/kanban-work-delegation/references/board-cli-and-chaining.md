# Board CLI traps, chaining and editing queued cards

Depth for step 1 of SKILL.md (Learn the board before creating anything).

## Contents

- CLI shape traps
- Chaining, inserting and re-ordering cards
- Cards gated on approval or a later check
- Editing queued cards instead of commenting
- Concurrent cards, design-record cards and run counters

## 1. Learn the board before creating anything

```bash
hermes kanban boards            # current board + counts
hermes kanban ls                # existing cards; NEVER recreate an existing graph
hermes kanban assignees         # which profiles exist and their on-disk status
hermes kanban show <task_id>    # body, comments, events, runs, latest summary
```

## CLI shape traps

CLI shape traps (they fail loudly but waste a round-trip each):
- **Check that the workspace actually loads an AGENTS.md.** A project created outside the
  rule tree (e.g. not under the competitions root) loads none. Then every standing rule
  (explicit-path `git add`, no stash, `.env` untouched, review flag) rides only in card
  bodies, and the first card that omits one breaks it. Propose a project AGENTS.md with a
  folder map. Schedule its cleanup card for when no other card has uncommitted files in the
  repo; moving files under a running card causes conflicts.
- Target a board per command with the group-level flag placed **before** the subcommand:
  `hermes kanban --board <slug> create|ls|show|request-review ...`. `create` itself has no
  `--board` option, so `hermes kanban create --board x` fails. `boards switch <slug>` changes
  the default for every later call (including other sessions) — prefer the explicit flag.
- New project/competition → new board: `hermes kanban boards create <slug> --name ...`. Run
  `hermes kanban boards set-default-workdir <slug> <abs dir>` yourself from the interactive
  session once the folder exists. Worker contexts cannot run it; they are refused with
  "cannot mutate Kanban tasks via the CLI". When
  that first card creates the project folder itself, set its `--workspace dir:` to the
  existing parent directory (so the parent AGENTS.md still loads) and put the new folder path
  in the body; a `dir:` that does not exist yet is not a valid workspace.
- `comment`, `block` and `request-changes` take the text as a **positional** argument, not
  `--body`/`--reason` (`request-changes <id> "<reason>"`).
  Quote the whole body: `hermes kanban comment <id> "$(cat file.md)" --author <profile>`.
  **Give every card body its own uniquely-named file and re-read it after writing, before
  creating the card.** A generic scratch path (`/tmp/card.md`, `/tmp/body.md`) reused across
  sessions can still hold a previous card's spec, and `$(cat ...)` will ship that stale content
  as the new card's body -- the title looks right, the worker correctly implements the wrong
  task, and the run is wasted. Name the file after the card, then `grep` it for two or three
  terms that must appear and one that must not before calling `create`.
  **Never pass a body inside double quotes directly, not even a one-paragraph review
  comment** — backticks and `$(...)` in the text are evaluated by the shell (a quoted
  repro command such as `curl ...` in a review comment actually runs), so code-fenced paths and commands get executed and are
  silently replaced by their output or by nothing. The comment posts and looks fine on the
  board while lines are missing. Write the body to a file and pass `"$(cat file)"`, or drop
  backticks entirely. After posting a long instruction, re-read it with
  `hermes kanban show <id>` and confirm the paths survived.
- `create --workspace` wants `dir:/abs/path` (or `scratch` / `worktree:<path>`).
- `--project <slug>` links a card to a Hermes project (worktree anchoring); it is not a board
  selector. An unknown flag makes the
  command print usage and exit **without creating anything**, so a pipeline that greps the
  output for an id silently yields an empty variable and every follow-up call then targets
  nothing. Create with `--json`, parse the id from that, and assert it is non-empty before
  chaining `notify-subscribe` or any other command onto it.

## Chaining, inserting and re-ordering cards

- **Chain cards that touch the same file with `--parent`** (doc-record card → card A →
  card B) so they run in order instead of racing on one work log. Create in dependency order,
  parse each id from `--json`, and substitute it into later bodies (e.g. `sed` a placeholder
  in the next body file, then `grep` that the id landed) before creating them.
  This user also wants **independent** cards chained in sequence when he says so ("독립이
  더라도 순서대로 확실하게"). Hidden coupling (a shared container, the CLI quota, the same
  tests) is the reason. Chain the new chain behind whatever card is still running or in
  review, and say in the reply that nothing runs in parallel.
  When he later asks "동시에 진행하는 방향은?", parallelise only the cards that share **none** of these: the git repo or workspace, docs both edit (OPS, work log), the host test suite or CLI, a container rebuild, and each other's inputs or byte-identical baselines. A card working in a separate folder outside the repo (a blind-pack generator) usually qualifies. Cards that edit the same converter or ops doc do not. To move it: `unlink <chain parent> <card>`, then `link` every parallel branch into the downstream gate (`link <A> <gate>`, `link <B> <gate>`). Confirm with `show <gate>` → `parents`. Comment the isolation rules on the freed card ("do not rely on project ingest or tests while code is changing"). In the reply, show the new graph and give for each serial pair the concrete resource it shares.
- **Split a new experiment into a CPU prep card and a GPU run card when the single GPU is queued.** The prep card (data download, filtering, pool build) gets no parent and starts at once. The run card gets `--parent <prep> --parent <GPU predecessor>`, then `link <run> <downstream consumer>`. One card with both steps would sit in `todo` behind the GPU queue, idling hours of CPU work that blocks nothing.
  The mirror case also needs a split: a short GPU step (feature extraction, a probe) followed by a long CPU judge. If you link the next GPU card behind the whole card, the GPU sits idle for the entire CPU judge. Make the GPU step its own card, gate the next GPU card on that card only, and hang the CPU judge card off it as a side branch.
- **To insert a card into an existing chain** (a new step must run before a queued child):
  create it with `--parent <previous>`, then `link <new> <child>` **before**
  `unlink <previous> <child>`; confirm with `show <child>` → `parents:`. Unlinking first
  can leave the child with only finished parents for a moment; it turns `ready` and the
  dispatcher may claim it against the old code. The same order applies when you **swap a
  gate's parent** (new fix card in front of a measurement card whose other parents are
  done): `link <new> <gate>` first, then `unlink <old> <gate>`. The CLI's "was ready and is
  now todo" note after the unlink means the race window was open. Check `runs <child>` shows no run. Linking a `ready` child to
  an unfinished parent drops it back to `todo`, which is what you want.
  **Reordering a whole queue** (A→B→C→D becomes A→C→D→B) is several inserts at once. Run every `link` of the new order first and only then the `unlink`s of the old edges, in one script. Exception: moving a card earlier makes `link <it> <old ancestor>` a cycle (refused); unlink that old edge first, which is safe only while the card still has another unfinished parent (check it stays `todo`). Afterwards print `status | parents` for every card in the chain and `runs <id>` for any card the CLI reported as "was ready". Unlinking edge by edge opens a ready window on each card in turn; on a GPU queue that can start a second training job on a busy machine.
  Exception: when the new order **reverses** an existing edge (B used to wait on A, now A waits on B), the new `link` is refused ("would create a cycle"). Unlink only that reversed edge first. Do it only while the card it frees still has another unfinished parent, so it cannot turn `ready`. Then run the links and the remaining unlinks.
  Moving X earlier (A→B→C→X to A→X→B): `link X B` fails with "would create a cycle" while C→X exists. Unlink C→X first, which is safe while X keeps another unfinished parent.
  `link` is refused once the child is running ("child is already running"). If a new fix
  must land after a card that is already running, link the other way: `link <running>
  <new>` so the new card waits for it. Then `link <new> <downstream gate>` (final check,
  acceptance), so the gate checks the fixed state. Tell the user the order changed and why
  (a rebuild during an acceptance run would disturb it).

## Cards gated on approval or a later check

- **A card that must wait for the user's approval is created blocked, not chained and
  blocked later**: `create ... --parent <prev> --initial-status blocked --json`, then
  comment the user's gate condition ("start only after the user reviews A/B results").
  **When the gate is "parent approved", nothing wakes you.** The dispatched review run
  approves the parent silently, and the blocked child then idles (a GPU launch card sat
  ~1.5 h this way). Right after creating such a pair, either `notify-subscribe` the parent
  with `--delivery-mode wake`, or tell the user you will check at a stated time and check
  `runs <parent>` on every later turn. On approval, re-verify the artifacts yourself, comment
  the pinned hashes on the child, then `unblock` in the same turn.
  `block` on a `todo` card is refused ("cannot block"), and a plain `--parent` chain
  auto-promotes the card the moment the parent completes. To hold an existing `todo`
  card, use `hermes kanban --board <b> schedule <id> "<reason + resume condition>" --ids <more ids>`:
  it moves `todo` cards to `scheduled`, keeps links and subscriptions, and `unblock`
  releases them later. No archive-and-recreate needed.
  The same applies to a follow-up that would disturb something the user is doing by hand
  (restarting a live service he is testing): create it blocked with the gate as a comment,
  and unblock only after he reports the manual test done.
- **When a gate card completes (final check, acceptance), look at what it releases before replying.** A downstream card written days earlier, before a run of later cards, starts at once on a stale body. `block` it with `--kind needs_input` ("user decides on the report; scope predates cards X–Y"). Refresh its body with `edit` after the user says go, then `unblock`. The user decides on the report first even when he earlier said "get the check, then proceed".
  - The exception is a check of a **plan** (queue order, new card designs) when he said "최종점검 받고 진행해줘" and the check releases no side-effect card. Apply the checker's advisory items to the card designs in the same turn: new cards, reorder, added controls.
  - Open the reply with the checker's corrections of your own claims, in numbers, before listing what you applied.
  - Leave any spend, submit or deploy for his separate go.
- **When the approval that releases a chained child carries a risk note, fold a measurement of that risk into the child at once.** A good example of such a note: "this may be a parser-level cause, so the fix may not help". The dispatcher can claim the child within seconds of the approval. Post the added measurement as a comment first, because a comment reaches a live run. Then `edit` the body for any re-run. Write the item as "report X next to the baseline value Y, not part of the verdict", so it informs the decision without changing the pre-registered rule.
- **Before unblocking a long-gated check card (final check, audit), comment its current scope.** Its body predates the cards that ran meanwhile. Give the base HEAD, the cards completed since the body was written, any manual session's time window and log paths, and the list of code changes made **after** that manual session. Ask the checker to judge their impact on the session's verdict as a separate item. Otherwise it re-derives an old verdict for code that has since moved.

## Editing queued cards instead of commenting

- A `todo`/`blocked` card can be re-scoped in place with `hermes kanban edit <id> --title
  ... --body "$(cat file)"` and re-routed with a comment + `unblock`, instead of archiving
  and recreating it (keeps subscriptions and history).
  **Fold requirements added to a queued card into its body with `edit`; do not leave them
  as comments.** Before every `comment` on a `todo`/`scheduled` card, ask whether it changes what the worker must build, measure or judge. If it does, use `edit`. Comments are only for notes that change none of those: a status note, a context link, or a user decision that is already in the body. Workers implement the body and skip comment-only items, typically the
  side-file edits such as an ops doc. This includes a user change of the card's objective
  or adoption rule ("maximise the success rate instead of the simplest fix", "CLI only"):
  rewrite the goal, sample size and rule in the body, rather than a comment that says it
  outranks the body. The same goes for two easy-to-miss cases: a 🟡 from one review that
  you carry into the next queued card ("add this OPS line too"), and a user decision you
  apply to a `blocked` card just before `unblock` ("API ≤20 calls replaces item X").  Both
  feel like small add-ons, which is exactly why they end up as comments. `edit` the body
  first, then `unblock`.
  The largest case is a **batch plan change** ("전부 반영해줘" after a final check). Such a change rewrites the judging rule, the arms or the inputs of many queued cards at once, and posting one amendment comment per card is the tempting shortcut. Use one script instead. For each card, append that card's amendment file to its current body as a dated "## 수정 (<date>, 사용자 결정)" section, apply it with `edit --body`, and re-`show` it to confirm the section landed. A comment-only amendment on a card that starts days later gets implemented against the old body. Add-on comments on a running card are fine, because
  they are injected live. Either way, at review, tick every comment item off against the
  commit's file list (`git show --stat`) before reading the code. Do this before a
  chat-side approval opinion as well, not only in the dispatched review. **Include the
  add-on comments you posted yourself.** Your own probes cover the behaviour you asked for,
  so the output-surface items in your comment are the ones you skip, e.g. "also show it in
  the status command". The same goes for each **alternative branch** of a rule you wrote. For
  "keep when proven per row OR by the dataset README", a hash-and-leak recheck confirmed only
  the per-row branch. The README branch was never implemented, and the review bounced it.
  Write one probe per branch, e.g. a source that only its README proves must come out kept. A long-queued
  acceptance card that collected comment-only deliverables over days (a check script, OPS
  sections, a checker feature) is the most likely place to miss one. List them with
  `show <id>` comments, then `ls` and `grep` for each artifact.

## Concurrent cards, design-record cards and run counters

- **Cards that can run at the same time in one git repo must commit with explicit paths.**
  Put `git add <this card's paths>` in the card and forbid `git add -A` / `commit -a`.
  Otherwise one card's commit sweeps in the other's half-done files, and an `index.lock`
  clash looks like a failure.
  Explicit paths do not help when both cards edit the **same** file (the ops doc, the work
  log). A doc-fix card opened by a dispatched review often runs next to the next
  implementation card. Comment on the later one at once: "do not edit <file> until
  `git log` shows <other card's commit>; before committing, check `git diff <file>` holds
  only your hunks, and use `git add -p` otherwise".
  When both concurrent cards rebuild and redeploy the same container image, comment on
  both at once: one rebuild at a time, build from a clean `git archive HEAD` tree (so the
  other card's uncommitted files do not ship), and after redeploying compare host vs
  container sha256 of **the other card's** changed files too, so a later build does not
  silently roll back an earlier card's deploy.
  To complete a design card whose
  parent is still in `review`, `unlink <parent> <child>` first — `complete` refuses on
  unsatisfied parent dependencies.
- **A self-assigned design-record card is created `--initial-status blocked`, then
  `complete`d at once** — created `ready`, a reviewer worker claims it and may spawn a
  duplicate implementation card. Recovery: `references/pausing-and-sequencing.md`.
- **When a user decision adds prerequisite cards in front of a blocked card**, create them
  and `link <new> <blocked>` **before** `unblock`. The unblocked card then waits in `todo`
  until they finish. Unblocking first lets the dispatcher claim it within seconds and run
  it against the pre-decision code. Check with `show <id>` → parents count.
- **`[run N]` in `show` events is a board-wide run counter, not the card's retry count.**
  Check `hermes kanban runs <id>` (one row = first attempt) before telling the user a card
  crashed or restarted.
- The subcommand is `notify-subscribe`, not `subscribe`, and it wants `--platform` plus
  `--chat-id` / `--thread-id` as separate flags — a bare `--chat` is rejected as ambiguous.
