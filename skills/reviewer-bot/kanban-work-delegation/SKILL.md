---
name: kanban-work-delegation
description: "Use when delegating, steering, auditing Hermes kanban work."
version: 1.3.0
license: MIT
metadata:
  hermes:
    tags: [kanban, delegation, multi-agent, orchestration, code-review, verification, benchmarking, attribution]
---

# Delegating work through a Hermes kanban board

For orchestrator/reviewer profiles that create cards, steer workers, and accept or
reject their output. Worker profiles execute; the orchestrator designs, instructs,
and verifies.

## Role boundary (always on)

**The orchestrator does not write or edit the files the worker was assigned.** Analysis,
design, card authoring, and verification only. Reading files, running read-only commands,
and recomputing numbers are all in scope; `cp`, edits, reverts, and writes to the
workspace are not.

Running the worker's benchmark or analysis script yourself is verification, not authorship — do it. Routing, card-input pre-registration and relay checks: `references/card-inputs-and-routing.md`.

The line is **not** simply "mutating the workspace". Recomputing a stated result is yours;
**mechanical exploratory search is the worker's even when it is entirely read-only.** Probing
API endpoint variants to find one that responds, trying credential shapes, and grinding
through candidate paths are cheap-model work by definition — reaching for them because you
have the shell open is the same violation as editing a file, and the user will read it that
way. Ask "is this discovering *what* to do, or executing a known procedure?"; only the first
is yours.

When you have already over-reached and produced useful findings, **hand them to the worker
rather than discarding them** — put the attempted variants and their exact failure codes on
the card as a do-not-retry list. Withholding them to stay inside the boundary just makes the
worker repeat the same dead ends.

When a mid-task correction arrives ("revert that", "do it as a new file instead"), the
correct move is to put the new instruction on the card and let the assigned worker carry
it out — doing it yourself because it is faster is the exact failure. A stale card left
running under the old instruction is not an excuse to grab the keyboard; block or comment
the card first, then wait.

The boundary breaks under **urgency**, not under ambiguity: a worker is mid-run against
superseded instructions, and undoing its output looks like damage control rather than
authorship. It is not. Reverting, `cp`-ing a baseline back, and deleting a stray artifact
are all worker actions; the orchestrator's move is to halt the run and re-instruct. If you
catch yourself reaching for a write because "the worker is about to make it worse", that is
precisely the moment the rule exists for.

The same applies to **cleanup**: deleting a leftover file, tidying a stray copy, or fixing a
misreported deletion. Detecting it is verification and is yours; performing it is the
worker's, and goes on the card as a task with the `ls`/`diff` evidence you used to find it.
Keep your verification commands strictly read-only. Do not tack an `rm -rf` of your own probe folder onto them. A recursive delete is approval-gated, so the whole command waits and then fails unrun, and the checks inside it are lost. Use fresh uniquely-named scratch folders instead of deleting old ones.
Before running a worker's tool in its "test mode" from the live repo, read where it writes its side files (backups, logs, state), not only its main target. A test-mode override that redirects only the target file still drops backups into the production folder, and a later production rollback restores the fake value. Copy the script into a scratch tree, or set every path override. If your probe already left files, report them and their contents on the card. A side effect your own probe created is the one cleanup you undo yourself, after checking the contents are your fake values.
For an undo/rollback feature (secret swap, config switch), probe the sequence, not one step: change key A three times, change key B once in between, then roll A back until it refuses. Expect each earlier A value in order, then an explicit "nothing left, file unchanged", with B untouched and the production backup folder listing identical before and after. A single change-then-rollback passes code that restores only the newest backup or crosses keys.

This boundary is a standing user expectation, not a stylistic preference — restate it in
plain terms when corrected, own the specific violation rather than apologizing broadly, and
resume as instructed without re-litigating it. Expect the correction to be terse and to
assume you already know the rule ("you do analysis and design, the worker does the work");
treat a repeat correction as evidence the rule was not actually internalised the first time,
not as a new instruction.

## Procedure

### 1. Learn the board before creating anything

```bash
hermes kanban boards            # current board + counts
hermes kanban ls                # existing cards; NEVER recreate an existing graph
hermes kanban assignees         # which profiles exist and their on-disk status
hermes kanban show <task_id>    # body, comments, events, runs, latest summary
```

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
  `complete`d at once.** Created `ready` and assigned to yourself, the dispatcher spawns
  a reviewer worker on it within seconds. Create the implementation card afterwards with
  `--parent <design id>`; the parent is already done, so the child is ready immediately.
  If the design card was created `ready` anyway and a worker already claimed it, `complete`
  is refused and a child created with `--parent` sits in `todo`. Do not `--force` or
  `reclaim`. Run `unlink <design> <child>` so the child turns `ready`, and comment on the
  design card that the spec is final in its body and the run should only `kanban_complete`.
  Under time pressure, skip the separate design card and put the spec straight into the
  implementation card body.
- **When a user decision adds prerequisite cards in front of a blocked card**, create them
  and `link <new> <blocked>` **before** `unblock`. The unblocked card then waits in `todo`
  until they finish. Unblocking first lets the dispatcher claim it within seconds and run
  it against the pre-decision code. Check with `show <id>` → parents count.
- **`[run N]` in `show` events is a board-wide run counter, not the card's retry count.**
  Check `hermes kanban runs <id>` (one row = first attempt) before telling the user a card
  crashed or restarted.
- The subcommand is `notify-subscribe`, not `subscribe`, and it wants `--platform` plus
  `--chat-id` / `--thread-id` as separate flags — a bare `--chat` is rejected as ambiguous.

### 2. Route model tier by task kind

Check `model.default` in each profile's `config.yaml` before overriding anything — tiers
are usually already split. Put judgment-heavy cards (design, attribution, redefining
acceptance criteria) on the stronger model and mechanical cards (implement-to-spec, run
the bench) on the cheaper one. Downgrading the design card is a false economy: a bad
parameter choice there forces a full re-run of the implement+benchmark cycle, which costs
more than the model difference. Per-card override: `hermes kanban set-model <id> --model <m>`.

### 3. Write the card so it cannot be satisfied by prose

Every card body needs:
- **Background with the real numbers**, so the worker does not re-derive them.
- **Numbered deliverables**, each with the artifact path it must produce.
- **Exact expected values** where they are already known, plus "if this does not reproduce,
  the implementation is wrong — stop and report". A self-check the worker cannot fudge is
  worth more than any amount of instruction.
- **A ban list**: approaches already measured and rejected, with where the rejection is
  recorded. Without it workers re-propose dead ends.
- **Explicit permission to conclude "no improvement found"**. Without this line a worker
  manufactures a recommendation to look productive — the same failure mode that produced
  the bad input in the first place.
- **A ban on modifying the file under study.** Analysis cards should name the artifact as
  read-only and require new files for anything the worker produces, so the measurement
  baseline survives the card. State where a pristine baseline copy lives so scope can be
  checked with one `diff`.
- **Check every object a criterion names before writing it.** grep for the endpoint, file
  or setting ("/healthz 200"). A criterion on something that does not exist becomes a
  spec defect at review. A card that rebuilds and redeploys an image also ships every
  commit made since the running image was built. List those commits in the card, and state
  whether their default-off features keep the "behaviour change 0" claim true.
  When a criterion spans several configurations ("≥14/15 legit answers in full and rag"),
  check that every item can be answered in every configuration. An item a mode cannot
  answer by structure turns a faithful card into a false failure; for example, a count over
  a whole table cannot work in a top-k retrieval mode.
- **Run every code or command template you write into a spec exactly as written before posting it.**
  This covers prompt patterns the shipped artifact will show a model, snippets the worker must
  insert verbatim, and replacement blocks. Copy the block out of the card file, swap only a temp
  path in, and run it. Markdown formatting changes code: list indentation in front of a heredoc
  makes the terminator line invalid, and the copied body raises IndentationError. Neither the
  worker nor the review run catches it, because both implement the text faithfully. Treat a
  template that fails this way as a spec correction, not as the worker's 🔴.
- **Write any detector or classifier rule in a spec as value-based plus a visible safety net, never as a header/keyword whitelist.** Examples are person columns, year columns, refusal detection and numeric roles. A whitelist fails silently on the first shape you did not list, and every round of review finds a new one. Specify all four parts: the value criterion, which way to err (over-mask for privacy, warn for numbers), a run-time report or invariant that lists what was classified and flags what was dropped, and an adversarial fixture of shapes absent from the corpus. Then test the rule on such inputs yourself before you post the card.
  **The direction flips for rules that decide what to expose.** Examples: keeping names on a staff list, attaching an identifier column to a precomputed answer. Write those as an allowlist of known-safe headers (non-person object stems). An unknown or generic header exposes nothing. A blacklist ("skip person-like headers") fails open whenever the header carries no information. In one case a headerless-table detector renamed columns 열1…열N, so the blacklist matched nothing and the always-on aggregate printed farmer codes.
  A **list of markers to strip before matching** (honorifics, bracket tails, title words) fails the same way as a keyword list: every unlisted marker is a new leak. A naive boundary rule ("name-shaped prefix + non-letter") swings the other way and masks real label columns. What closes the class is a second, **column-level** decision: count distinct candidate tokens across the column, then add a companion check that tells labels from names. A label prefix is followed by many different words. Gate it with a **seeded random generator of realistic mixed columns** (several seeds; silent misses 0, false masks on non-target columns 0), plus byte-identical output on existing corpora. Do not gate it on a hand-written case list. Probe the rule yourself on real-corpus shapes before posting it as a spec correction; your proposal is a spec and can be wrong.
  **Write a multi-signal detector as a three-way vote, never "any one X matches" and never a bare "every X matches".** Each signal says yes, no, or abstain, and abstains when it carries no evidence (too few non-zero values, mixed signs, all zeros, blank). Fire on ≥1 yes and 0 no. "At least one measure column equals the sum of the others" dropped real rows on sparse small-integer columns, where coincidences are common. The correction "in every non-empty column" then missed the real total rows, because their sparse and ± cells cannot match and counted as no. Both wordings were in reviewer specs, one round apart. Probe each spec clause with a coincidence fixture (false positive) **and** a true target whose other signals are non-evidence shapes (false negative) before posting.
  When a spec defines adjacency ("X directly followed by Y"), list every joiner the data uses: attached, one space, `:`/`：`, a bracket, full-width forms. A spec that named only "attached or one space" leaked `김민수(조합원)` 10/10, a common table-cell form.
  Specify the allowlist as a **full match on a closed grammar** ([modifier]? + object noun + [suffix such as 명/번호/코드]?), never as "header contains a stem". Korean compounds put the head noun last, so a substring allowlist passes 품목 출하처, 사업자번호, 시설(이용자). One such spec phrase leaked codes under 20 of 22 person headers. Probe compound, bracketed, full-width and separator forms (선박（선주）, 선박/선주), not single-word headers.
- **When a card adds a step that removes or rewrites a signal, list every downstream consumer of that signal and probe each one with the rewritten input.** Signals include headers, dates and file names. Two features in one card interact this way, and each feature's own tests pass.
- **Pin byte-identical baselines to a commit, and say what to do if it moves.** A design card that fixes expected outputs at commit X goes stale when another card lands on the same module before implementation starts. A careful worker stops and asks. Write the rule into the body up front: rebuild the baseline at the current HEAD first, commit the diff against X, and stop to report if that diff goes beyond the expected list. Keep the numeric targets. When a worker does stop on this, answer with the HEAD rule and unblock in the same turn.
- **When a spec records state before an action that can fail, state what happens to that state on failure.** Examples: a dedup or idempotency marker, a "sent once" flag, a reservation, a counter. A spec that only describes the success path gets implemented that way. The fixtures cover only success, so the tests pass, and the first transient error locks the user out of retrying. Write "keep on success, clear on <each failure outcome>" and add a fail-then-retry gate.
- **Forbid moving the goalposts**: report shortfalls as numbers, never relax the criterion.
  The same applies to you: when a fix card re-implements a decision rule the user already
  approved (a verdict function, a gate), copy that rule verbatim. Adding a condition while
  "tidying" it changes the verdict the run prints, and you then have to explain why the
  printed verdict disagrees with the approved rule.
- **State git expectations as two explicit yes/no lines** ("local commit: YES, message
  `<msg>`; push: NO") and put `git status` empty + the commit hash in the completion
  criteria. "Commit locally, push forbidden" written as one phrase gets read as "no git",
  and the round trip costs a full review cycle.
- **Size every absolute threshold to the sample before writing it.** A floor like "Hit@5 ≥
  0.70" on n≈50 is inside the binomial noise of a result a few items short; prefer a paired
  criterion against the previous version or baseline, or write the floor with its CI. A
  floor missed only by noise is a spec defect: approve the faithful implementation, record
  the miss, and raise the threshold question to the user instead of bouncing the worker.
- **When a run has a time guard that can stop it early, order the items so every gate keeps its sample.** Interleave control items with the treatment items. Do not append them at the end, because a late cut then removes the whole control gate. Pre-register a minimum completed count per gate, below which that gate reads "not measurable" and nothing is promoted.
- **Compute a metric's no-op and oracle values before writing a delta threshold on it,
  and check that criteria can all hold at once.** A similarity score where "do nothing"
  already reaches 0.96 cannot rise by 0.05; a success floor plus a per-item step cap can be
  jointly unreachable on the real size distribution. Ask the card to print both reference
  values first. When the worker flags such a conflict at review, decide each flagged item in
  the approval comment (replacement metric or criterion, with its numbers) so the next card
  inherits the corrected rule, rather than bouncing a faithful implementation.
- **For public-facing text edits, ship the exact replacement sentences and an explicit
  do-not-touch list.** Workers "improve" wording and replace every occurrence of a value;
  name the lines to change, the look-alike occurrences to leave (e.g. measurement tables),
  and make the diff hunk count a completion criterion.
- **For verbatim rule/document insertions (AGENTS.md sections, templates), put the block in
  its own file and require a block-level `diff` with 0 lines as a completion criterion.**
  A code-fenced block inside the card body "to insert as-is" still gets paraphrased by
  cheaper models (items merged, duplicated, tone changed) and the commit gets skipped.
  Verify yourself with an awk-extracted block diff, the file md5, and `git show --stat`.
- **For remote-history rewrites (force push), require a backup and remote verification**:
  `git bundle create <path> --all` before touching anything, `--force-with-lease`, then
  `git ls-remote` sha == local HEAD and an API read-back of what the user will see. Tell the
  user about the force push and the backup path when you hand the card off.
- **For any push card, anchor to the remote as fetched at run time, not a SHA from the chat.**
  The user edits public repos on the web between cards. A card that hard-codes the base SHA,
  the original line text, or an absolute commit count gets a non-fast-forward rejection.
  Make the card `git fetch` and rebase onto `origin/<branch>`. Treat the user's web commit as
  intentional: keep it and resolve conflicts in its favour. Write the criteria relative to
  that head ("diff since origin/master = these files only", "origin/master is an ancestor of
  HEAD"), not as total commit counts.

### 4. Resolve contradictions you introduce

If a card forbids touching code but its analysis requires toggling behavior, the worker is
stuck between two orders and will either block or guess. Post a comment that names the
contradiction and carves the narrow exception ("refactor to extract toggles only; defaults
must reproduce current numbers exactly"). State that the comment outranks the body.

A comment on a **running** card is normally injected into the live run as operator steering
(that is how a scope extension such as "also recommend alternatives" reaches a running
opinion card). It is still durable on the board for any re-run. When the result comes back,
check that it actually addressed the comment before relaying it.

### 5. Route notifications through yourself

Intermediate coder/helper cards: `--delivery-mode notify` (user cost rule 10/27). `wake` only for a
phase's final card, a card needing a user decision, and fable cards.

```bash
hermes kanban notify-subscribe <id> --platform <p> --chat-id <id> --thread-id <id> \
  --chat-type thread --notifier-profile <orchestrator> --delivery-mode wake
```

`--delivery-mode` choices: `notify` pastes the worker's own summary into the chat;
`wake` wakes the orchestrator to read the board and speak in its own voice; `notify+wake`
does both. **Use `wake` when the user should hear one voice** — `notify+wake` leaks the
worker's raw summary and looks like the worker is answering directly. Re-running
`notify-subscribe` on an existing subscription updates it in place.
Every `wake` replays the orchestrator's whole chat context. Use `wake` for completion
and decision events, and `notify` for intermediate ones (review requested,
handed off), which a dispatched reviewer run already handles.

To watch another board's card from this thread, subscribe to it here. Remove it with
`notify-unsubscribe <id> --platform <p> --chat-id <id> --thread-id <id>` once the
dependency is gone. Otherwise its events keep landing in the wrong conversation.

**Moving a project's alerts to a new thread ("크론 답변 여기서 하게 해줘") has three layers; do all three in one script.**
1. Cron jobs: `hermes cron edit <id> --deliver <platform>:<chat>:<thread>` for every job of the project. A job set to "origin" follows the chat that created it, so pin it explicitly. Remove a watcher cron whose trigger already fired (e.g. an access-approval poller), rather than moving it.
2. Scripts: grep the profile's `scripts/` for the old thread id. Watchers that auto-subscribe new cards often hard-code it. Replace it, `py_compile`, and print old-id hits = 0.
3. Card subscriptions: dump `notify-list` first and keep each card's delivery mode. For every open card, `notify-subscribe` the new thread **before** `notify-unsubscribe` of the old one, so no event falls into a gap. Then print the list again and check every card shows the new id.
Also update the thread id in the project skill note, or the next session's card template brings back the old thread.

**Live progress in the chat for a long worker job.** "Can I watch it here" means periodic
aggregates, not a stream. Stream the raw work only if it contains no restricted content
and would not flood the thread; neither is usually true. Recipe:
- The card makes the worker keep a `progress.json` with fixed field names: done/total,
  batches, failures, ISO start and last-update times, running cost, per-category rates.
  Post the field list as a card comment too.
- Create a `cronjob_manage` job with `no_agent=true`, a script in the profile's `scripts/`,
  `deliver=<platform>:<chat>:<thread>`, `failure_deliver=local`, every 30 min. The script
  prints one summary line with an ETA. It prints nothing when unchanged or not started, and
  warns **once** when progress stalls. Test it on a fake progress file first: fresh,
  unchanged and stalled cases.
- It costs no tokens and never sends restricted text (e.g. competition data).
- **Respect the user's quiet hours (23:00–09:00 local).** No-agent alert scripts must not
  print during that window. Route their output through a shared helper
  (`scripts/quiet_hours.py` `emit(msgs, name)` in the profile). Overnight it appends to a
  hold file and prints nothing. The first run after 09:00 prints "held overnight: N" and
  then the held lines. Test it on 22/23/00/08/09 o'clock timestamps. Your own @-mentions
  follow the same window: overnight wake-ups get a short reply with no tag. When the user lifts the window for specific work ("시간상관없이 알려줘"), scope the exception to those cards. Comment it on each card (approve/bounce/block results may tag overnight; this card only) so the dispatched review run follows it too. Do not set the global `OVERRIDE_UNTIL` file for this, because it also releases every unrelated cron alert overnight. Tell the user that other alerts stay quiet. Tell the user
  two things. Card-event wake-ups still post to the thread overnight; muting the thread to
  mentions-only silences them. A held duplicate-GPU alert costs up to one session of
  quota, so offer to exempt that single alert class.
- `hermes cron create --script` takes a script name only, with no arguments. To reuse a
  parameterised watcher (slug, state file, label, warn hours), have the card add a small
  wrapper script in the profile's `scripts/`. The wrapper imports the watcher's `check()`,
  calls it with fixed arguments, and prints through `emit()`. Before you register it, test
  it with a fake `status_fn` and a temporary state file. Then run it once for real: while
  the job is still running it must print nothing.
- Pause a progress cron once its job is finished (`hermes cron pause <id>`), and do not leave
  it posting "no change".

**Before quoting an ETA, read the live process, not the output folder.** Take `ps` for the
running command (flags such as `--fresh` mean the worker restarted from zero), and take the
progress line of the log it writes (`[k/N]`). Then compute the rate from two timestamps.
A records folder left by an earlier pass can be nearly full while a fresh rerun is at 7%.
"Done in 10 minutes" read off that folder turned into a 5-hour run, and the estimate had
to be withdrawn. If you can't tell why the worker restarted, say so; don't guess a reason.

**"Is this overloading the machine?" — answer with four readings and the end time.** Give
load average against the core count, `memory_pressure` free %, `docker stats` per
container (CPU, memory against its cap), and `pmset -g therm` and power state. Add the
time the job ends, since the load stops then. List stale containers you see (days old,
0% CPU) as cleanup for a card, not something to delete yourself. Give the one knob the
user can turn (concurrency) and what it costs in time.

For your own "is it still running?" checks, keep one read-only status script in the
profile's `scripts/`. It covers board `ls`, progress files, remote job status, and live
worker pids per card. Run it with `bash <path>`. Long inline one-liners that chain many
commands are rejected by the command parser, and a script is re-runnable anyway.
Write verification probes the same way, as `review_<card>.py` in scratch, with a step argument (`tab`, `dup`, `sym`, ...). The terminal lifecycle guard refuses inline heredocs that name large data files, because it cannot scan them. The next review round of the same card then re-runs the same file unchanged.

### 5b. Pause and resume on the user's word

"Finish what is running, then stop so I can test" → let the running card (and its review
loop) finish, and `schedule` every queued `todo` card downstream of it (see step 1). Then
tell the user which code state the live service is actually on: cards approved but not
yet deployed do not show up in his manual test, so offer the redeploy as a separate
choice.
On "do the next one", resume only the next card (`unblock <id>`). Keep any code card that
follows a planned rebuild in `scheduled` until the rebuild is done, because the image
build copies the working tree and would ship its half-edited files. When a resumed card
runs the CLI, warn him his live chat replies may slow down while it measures.
If the user asks for a deploy at a state change (a pending card is approved), ask "now or
after your test?" before acting: the redeploy changes the bot he is testing.

"Pause this until X is done" → `block <id> "<reason + what exists + resume instructions>"
--kind needs_input`, then confirm with `ps` that the worker process exited. If the user
later says "wait for my approval", that **replaces** the automatic condition. Comment the
change on the card, drop any cross-board subscription you added for the old trigger, and
do not unblock when X finishes. On resume, first post a comment listing the artifacts that
already exist and must not be regenerated (frozen folds, uploaded datasets). Then unblock.

**Taking over a card that another session stopped ("다른 세션에서 하던 거 해야 되면 진행해줘").** Before `assign` + `unblock`:
- Confirm with `runs <id>` that no run is live.
- Read every comment from both sessions. If a bounce and a later chat comment give different fix rules, name the one that governs and withdraw the other explicitly, using the scarce resource as the tiebreak (GPU quota).
- List the uncommitted files left in the tree, and mark them as unverified half-state to be re-verified from scratch. Name the other cards' files that must stay out of the commit.
- If a remote run the stopped worker launched is still live and the CLI cannot stop it, the card must not push again. Its output is reference only and stays out of the verdict. Ask the user to press Stop in the web UI, with the quota reason. When he reports it, check that the remote status reads cancelled, and comment "user stopped, no results" for the report.
The next review continues the old round counter.

**"Fix it, then final-check, then proceed" means the fix card stops before the side effect.**
When a fix card also performs the irreversible step (push a GPU run, submit, publish), the
user's "check first" request arrives after it already happened. Split it: fix + CPU proof
in one card, the push/launch in a separate step gated on the check. When the user has
already approved the run ("fix, check, then run"), create the launch card after the check
returns go. Chain it with `--parent <last fix card>`, so your approval of that fix starts
the launch with no extra round trip. Give the launch card its own pre-push re-checks and a
one-push cap. For a read-only final check ("fix it all, then get the check"), create the
check card now with `--parent <fix card>`: it waits in `todo` through any bounce and starts
by itself on approval. Scope its body as `<base commit>..HEAD` plus "read the fix card's last
approval and bounce history first", since the fix commits do not exist yet. If you already bundled
them, say so plainly and give the user the stop path (e.g. Cancel in the platform web UI,
since the CLI has no cancel) together with the rule you will apply if the run starts
before the check returns.

"Stop this" (for good) is not a pause.
- `block` with the user's decision, the list of kept artifacts, and "do not resume".
- `block` does not stop a live run. Kill the worker pid **and** any child process it
  spawned, then confirm with `ps`.
- Check the cards that depend on it. `hermes kanban unlink <parent> <child>` so they do not
  wait forever, and comment what they must now mark "n/a".

### 6. Verify before relaying — worker summaries are claims, not results

Status-report sweep, helper-vs-coder routing for scripted collection, scraped-number bounds: `references/worker-output-checks.md`.

Never forward a worker's summary as fact. Reproduce the load-bearing numbers yourself from
the artifacts, then report in your own words. See `references/verifying-worker-results.md`
for the verification gates and the statistics trap that invalidates most benchmark verdicts.

**Two reviewers, one decision.** A `request-review` also dispatches a separate reviewer run
on the card while you may be reviewing it from the chat. If both of you make a design
decision (a resolution, a threshold), they can disagree, and the child card starts on
whichever one landed first. After the dispatched review completes, read its summary before
you report. When the bounce lands and its fix rule differs from the one in your chat comment, post a reconciliation comment at once: name the rule the worker follows (normally the bounce's), withdraw the other in so many words, and attach your extras as 🟡 add-ons. A worker holding two conflicting specs implements one of them, or a mix, and the next round bounces again. On a conflict, pick one by the scarce resource (GPU quota, deadline). Then
comment the correction on any child card that already started, and check that nothing was
pushed under the losing value. Tell the user plainly that the two reviews disagreed and
which one you kept.

**Label a chat-side opinion as unofficial in the first line of the reply** (the chat reply itself, not only the card comment you posted) ("채팅 확인 — 공식 판정은 리뷰가 냄"), and give the dispatched run's state (running since, retries). This applies most to a clean result: "직접 확인했어요, 🔴 없음" with no label is exactly the line that gets read as the approval. A "🔴 없음" from the chat reads to the user as the verdict, and when the dispatched run is slow or requeued after a quota wall he asks why the result has not moved. Never open with "문제없이 통과했습니다" while the review run is live. A data-import card was told "passed" from the chat twice in a row, and the dispatched review bounced it both times.
The slip happens most when you answer a "handed off for review" wake-up. You verify, post the comment, see `runs <id>` print `(running)` in the same command, and still open the reply with the result. Make the label your reply's first line whenever that output shows a live review run, and add "공식 판정은 리뷰 실행(<시각> 시작)이 냄" before any 🔴 count.
A chat-side "🔴 0" means only that **the probes you ran** found nothing. When the fix under review was a rule you wrote, probing just the fix tests your own rule against itself. One example: a check that only confirmed "no rows with provider containing AI Studio" passed, and the dispatched review then found the same label error behind a different route name. Before the opinion, run one probe for the whole defect class (here: every route for that label), not just the string the bounce named. Then list in the reply what you did not probe.

**When the dispatched review approves without your 🔴, the defect still gets fixed.** Its
approval does not cancel a correctness defect you reproduced (e.g. a year column summed as a
measure). This includes an approval that records your finding as an accepted "remaining limit"
(e.g. "names ending in 비 pass, 4 cases"). A privacy leak you reproduced is not a limit the
review may accept for the user. Do not reopen the closed card. Open a small child card (`--parent <closed id>`)
that carries your reproduction as a test fixture and requires the old fixture outputs to stay
byte-identical, so no re-measurement is needed. Announce it as your call, not the review's.

**Clear 🟡 findings that change the configuration a queued measurement card will use, before that card runs.** Examples are a default to flip off, a parsing false positive, or a code path that skips the feature. A blind or mock run on a configuration you already plan to change measures something you will not ship, and its numbers cannot be reused. Insert one small card in front of the measurement with the insert recipe above (unlink/link). Give it numeric gates and a byte-identical check for the off path. Tell the user the new order. Leave 🟡 items that do not touch measured behaviour (docs, naming) for later.

**Hold code changes to measured behaviour until a running measurement card finishes.** A dispatched review may open a follow-up design card for the same module (e.g. a privacy fix) just as the mock or blind measurement starts. Comment on that design card: "its implementation card gets `--parent <measurement card>`". Comment on the measurement card: "record the rows this behaviour affected", e.g. every mask/warn line and the wrong answers caused by it. The measurement then scores one code state, and its output becomes the fix's input.

**Near the round cap, merge both reviewers' 🔴 into one fix.** The dispatched reviewer's bounce lists only what it found. When you hold a separate 🔴 with the same root cause (e.g. another variant family the detector misses), comment it onto the card in the same round. Label it "fix together, the cap is 3" and give one combined acceptance test. Otherwise round 3 fixes half, and you are left with a 4th rejection or a redesign.
When the dispatched review ships a **model** of its corrected rule (a scratch copy of the module), run your own earlier reproduction against that model before the worker starts implementing it. A model built from the reviewer's probes can still fail your case; then comment the missing condition as part of the same round.
A chat-side 🔴 posted after the dispatched review run has already started usually misses that run's bounce text. The worker fixes only what the bounce lists. As soon as the bounce lands, comment on the card: "fold the chat-side 🔴 (comment <time>) into this round; the next review treats it as 🔴". Restate its repro and gate in a few lines. Check its fix in the next round before anything else.
When the last allowed bounce goes out, tell the user in the same reply what happens if it fails too. Name the fallback you will recommend, usually shipping with the new behaviour switched off or narrowed to its safest form, and say what that costs. Then a failed final round turns into a decision for him, not another loop.
When he says to drop it because it is getting too complex, do not kill a round that is already running and nearly done (e.g. a worker porting a reviewer's model). Killing it leaves half the change in HEAD and needs a revert card. Comment on the card: "this is the last round; port only the given rule; record newly found gaps as limits in the work log, do not fix them; no further bounce on this card". Then give him the endpoint choice with numbers: ship the current state if every gate moved only in the improving direction (the remaining holes existed before the card), or revert the card's commits and ship without it. Tell him he can still say "stop now" and what that costs.
When he picks the redesign after the cap, `complete` the escalated card with the decision as its summary (e.g. "user decision: redesign in <new card>; current code stays deployed with the switch off"). A blocked parent would hold the redesign child forever. Then create the redesign card with `--parent <escalated id>`, and `link` it in front of every queued card and gate that should see the redesigned code (cleanup cards, final check). In its body, list every probe folder and reproduction from all earlier rounds as required regression tests.

Before re-running a long check yourself (an offline dry-run takes minutes), run `ps` for
the dispatched review's process. If it is already running the same check, do not start a
second copy. Two copies compete for the CPU, and a foreground shell call can hit its
timeout. Wait for the dispatched verdict instead, and reproduce its claim afterwards with
a cheap targeted probe (e.g. a tiny fixture for the one function in question).

While that dispatched review run is live, `hermes kanban complete` from the chat is usually
refused ("a live worker is running it"). Post your verdict as a `comment` (severity-tagged, with the
numbers you reproduced) and let the dispatched run close the card. Do not `--force` or
`reclaim` to get your own approval in: that kills the run mid-review and leaves the card
with a crashed run and two half-verdicts.
**Run `show` (status + latest Events) immediately before `complete`, and skip it if a review run
is `claimed`.** The refusal is not guaranteed: a chat `complete` once landed in the same minute
the dispatched reviewer issued `request-changes`, so the card read `done` while the worker was
already re-running the bounce. The bounced fix then lands on a closed card; inspect the file it
rewrote yourself, and put any remaining defect on a small child card (`--parent <closed id>`,
round number continued) instead of reopening. Tell the user the two verdicts collided.
`request-changes` from the chat is refused the other way round: it works only inside an
active review run ("task is not in an active review run"), so a card sitting in `review`
before the reviewer run starts cannot be bounced from the chat. Post the 🔴 as a comment
that says "bounce this in the review run", with the exact fix and any "do not re-run the
side effect (no second push)" line. If the missing item is separable from an
irreversible step the card already did, have it moved to its own small card rather than
re-running the original body.

**`request-changes` is only for a 🔴 rejection, never for "GO, next step".** Using it to
steer ("not a rejection, round 0/3") inflates the round counter, which makes the 3-round
cap meaningless and hides real rejections in the audit. Steer with `comment` + `unblock`,
or approve and open the next step as its own card.

Take every time label in an amendment or pre-registration from `date`; a label later than the real post time reads as a post-result edit.

**Judge a measurement card by its pre-registered rule as written, never by a metric you
thought of after seeing the results.** If the wording is ambiguous, read it by its intent.
"Same accuracy and −30% tokens" means "accuracy not lower", not "exactly equal". A concern
the rule did not measure goes on the card as a separate decision-info table, labelled "rule
limit, not in the verdict". Examples are the extra LLM call's own tokens and the end-to-end
latency the user feels. Using such a concern to flip the verdict is moving the goalposts,
and the dispatched review will rightly bounce your approval. When you write the next rule,
fix the gap there. For an LLM post-processor, define efficiency end to end: every call's
tokens, and retrieval plus answer latency against the interim threshold.
If the design lists a known limitation that could move a gate, write it into the pre-registered rule itself. Use an exclusion criterion, a stratum, or a gate computed only on unaffected units. A limitation that lives only in a "limits" paragraph does not stop the gate from failing on it. That FAIL then has to be reported as the verdict, with the limitation as labelled decision info and an override offered to the user. One extra rule line written before the run removes that whole decision round.

When your chat-side human grading and the dispatched review's differ on a measurement card, report the dispatched number, scored by the pre-registered rubric, as the official one. Give your reading next to it as a labelled dissent with its reason, e.g. "the answer key is ambiguous because the new document is titled 조정안". Put the item's design flaw on the next pack's spec, not into this score.

**Re-running the worker's own script proves only that it is deterministic, not that its counts are right.** Before a chat-side "🔴 없음", check each headline count's definition against the raw records with an independent probe. Typical traps: a cap counted from trace length that includes rejected calls, a "first edit" that includes scratch-file writes, and "arguments not visible" when the trace does keep them. One rerun-only opinion got three headline numbers wrong in a doc already sent to the user, and the dispatched review bounced them.
The same holds for a worker's "dry-run exit 0": before agreeing, check which venv/library versions it ran under (see Deployability in `references/verifying-worker-results.md`). Matching the summary against the raw tables does not catch a dry-run run on the wrong environment.

State residual weakness even when every gate passes — a criterion cleared by a hair, or a
confidence interval still spanning zero, belongs in the report next to the PASS.

Verifying that a result is *real* is only half the job; also check that the quantity being
optimized is the one that moves the user's actual objective, that the evaluation pool still
describes the current environment, and that any stated cause survives a discrimination test.
See `references/measuring-what-matters.md` — a technically flawless benchmark aimed at the
wrong metric, or averaged over a population that has since shifted, produces confident,
worthless work.

When a production metric moves sharply while the offline benchmark still looks fine, trust
the production signal and check the benchmark pool for drift before proposing any fix.

**Also verify file-operation claims by listing, not by reading the summary.** "Deleted X"
is routinely reported when the file was overwritten, moved, or left in place; one `ls` or
`diff -q` settles it, and an unverified file claim is the kind that turns into a real
accident on the next card. "Output unchanged" claims get the same check: compare the
**set** of output names before and after, because a worker that diffs only same-named files
misses a newly created output. The same goes for a reported commit hash: check it with
`git log --all --oneline`, because workers amend after writing the summary and the quoted
hash may not exist.
Cards that finish without review (helper-bot) need this check most. A helper told to
"append one section" to a work log rewrote three past lines with `\"` escapes in place of
`"`. Right after such a card, run `git show <hash> -- <log>` and require zero removed
lines. Put the restore on whichever running card already edits that file, so two cards
do not edit it at once.
**Give every doc-correction card grep-count completion criteria for each defect it fixes**, e.g. `grep -c '^|- ' <file>` = 0, `grep -c '<old timestamp>'` = 0, and the expected count of the new string. List every occurrence of the defect too, including table rows and detail sections that repeat the same value. A fix written only as "replace X with Y" got done in one place and left in another, and a format fix (`||-` → `|-` instead of `- `) got applied the wrong way. Each miss cost a full card round.
For a card that aligns a runbook with a new user decision, derive the grep terms from **every concrete token the old plan used**: times (`08:30`, `14:30`), subcommands (`run`), step names and owners. Run that grep over the whole doc yourself before writing the card and list each hit with a fix-or-keep verdict. Also grep the **scripts the runbook tells the operator to run** for the instructions they print (usage text, failure hints such as "to undo: … --rollback"). Those strings are runbook text the operator reads first, and a doc-only grep passed while a script still printed the now-unsafe step; the review bounced it. A spec that named only the four places you remembered left two contradicting sentences (a timetable row, a tool-budget line), and the round bounced. After one helper miss on a format-exact edit, send the next correction to the coder tier with those counts. Re-run the counts yourself before calling it done.
For a file the worker rewrote, check its first bytes (`od -c <f> | head -2`), not only its
rendered content: a worker that edits through a line-numbered read tool can write the `N|`
prefixes into the file, which `cat`-style views and the worker's own grep hide.

**Read a report card's full result, not the truncated summary.** `hermes kanban show`
cuts a long `kanban_complete` summary mid-sentence and drops its metadata. The quickest
full copy is the board DB itself: open `~/.hermes/kanban/boards/<slug>/kanban.db`
read-only (`?mode=ro`) and `select summary, metadata from task_runs where task_id=?` —
`metadata` holds the per-criterion verdicts, the checker's own numbers, defects by
severity and any rubric disagreements; `tasks.result` holds the one-line advisory. The
worker's `~/.hermes/profiles/<worker>/state.db` (`messages`, last assistant row whose
`tool_calls` holds `kanban_complete`) is the fallback when the run row is empty.
Relay from that, and say which of your earlier claims it overturned.
A fable opinion card's raw numbers also sit in its own scratch (`~/.hermes/profiles/fable-bot/cache/scratch/<topic>/probe*.log`). Read those logs before you relay, because the summary drops the per-arm tables (bands, ratio-shift grids) you need to judge its advice.

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

### 7. Let the human approve side effects

When a card blocks for approval on a change with real consequences, present the verified
findings and recommendation but do not `unblock` unilaterally. After `unblock` the card
returns to `ready` and the dispatcher **re-claims it within seconds** — so finish the
conversation about whether it should run before unblocking, not after.

In a group chat, hand a decision back by **@-mentioning the user** rather than leaving the
question in prose; an unaddressed question in a busy thread reads as narration and stalls.
Say up front which classes of thing you will decide alone (re-instructing a worker, rejecting
an unverified result, technical course corrections) and which will always come back to them
(irreversible side effects, deployments, anything consuming a limited resource), then hold to
that split.

Slots, quotas, and publish targets are limited resources: recommend, quantify the expected
gain on the current regime, and let the user spend them.
Before pitching a spend, grep the project AGENTS for a clause that classifies the case, such as a list of "things we do not use GPU for". If your pitch conflicts with it, say so in the pitch with the reason the situation changed. Then, if he approves, write `사용자 결정(override)` into the card body and the work-log step. A pitch that skips the clause gets approved unaware, and the next audit flags the spend as a rule breach.
When a spend needs a number only the user can see (remaining weekly quota on a page you cannot log into), create the spend card `--initial-status blocked`, comment the floor, and ask for the number with an @-tag. Once his number clears it, `unblock` at once if the rest is a parent gate: the card waits in `todo` and the parent's approval releases it. Holding it for your own re-check leaves a manual release nobody is woken for; post those checks as a pre-push comment.
**An approval holds only for the evidence it was given.** Suppose the user approves a spend ("추천대로 진행") and then asks a question before the cards exist. If your answer turns up evidence that weakens the plan, do not create the cards. Examples: forum measurements against the lever, or a peer consensus that matches your own negative smoke. Say the cards are on hold, and present the new evidence next to the approved plan. Ask again with an @-tag. Cards created on stale approval run before he has seen the counter-evidence.

**Batch the user's hands-on checks into one session.** When a new feature needs the user
to do something himself (send a chat command, register a key, eyeball one message), do
not ask him per card. Build it so it works without him, with the feature off by default
and a test double in the card's criteria. Then append his steps to the final acceptance
script and tell him they are queued there. He wants "build it all, then check once".

**Do not automate spending of a limited resource on a guessed schedule.** A cron or retry
loop that keeps spending quota (API credit, free-tier generation, GPU hours) is itself a
spending decision. Propose it with its trigger and cap, and arm it only after the user agrees.
Never base it on an unverified assumption such as "quota refills at 00:00 UTC". When the user
says he will check the quota himself, pause the cron, kill any run it already started (and
that run's children), confirm with `ps`, and report the row and cost delta that run produced.
An explicit event-triggered request ("submit X as soon as the pending one finishes") is that agreement, even under a standing "no auto-submit cron" rule. Record it as a one-time override. The worker extends the guarded script and writes fake-backend tests. You run those tests and one live read-only dry-run yourself, then arm the cron at once, because the trigger can fire any time. Do not wait for the dispatched review to arm it. Pause the cron if that review finds a 🔴, and remove it after it fires. The submit-specific recipe is in the project-competition-lifecycle skill, code-agent-eval-harness reference, §6b.

**A decision that conflicts with a source you flagged stays open until the user names the governing source.** When his answer matches one of two conflicting official statements (a mail vs the main page), ask which one rules before you push the value into cards, docs or skill notes. If he says he has asked a third party ("문의 남겼으니 냅두고"), mark the item "unconfirmed" everywhere: post a correction comment on every card you already instructed, and keep the safe default (run longer, do not rewrite dates). Do not apply your own recommendation to it.
When he later confirms the value, ask first whether he means the exact boundary ("11/1 24:00 = 11/2 00:00?"). Then resolve it everywhere in the same turn. Send a doc card for the rest, carrying the exact replacement lines and a grep criterion: no "unconfirmed" or old date left. Keep the protected-file line off the headless card; apply it yourself only after his approval. Also update any operational constant tied to it (an alert window) and your skill notes. Keep a safety margin past the confirmed end for uptime.

**Write a user decision into the project work log in the turn it is made.** When he relaxes
a criterion or a standing rule (accepting a missed floor, dropping a one-shot held-out),
open a small helper card that appends a `user decision (override): <what>, basis: <numbers,
card>` section verbatim and commits it. A decision recorded only in a card comment is
invisible to the next audit and gets flagged as a rule violation.

**Re-read the gate you just approved before declaring the work done.** A contamination or
safety guard can pass its own tests and still fail open on a missing input (e.g. a
reference file absent → a check silently degrades to a weaker mode and exits 0).
For a triage or review tool ("a person reads only the flagged items"), walk the operating
doc's procedure literally. List every output state the tool can print, such as skipped,
unjudged, parse-failed or over-cap. Any state the procedure does not tell the human to read
is silently dropped, even when it is visible on screen. Errors must fail closed into the
bucket the human reads ("review needed (grader failed)"). Recompute recall with failures
counted as the tool actually reports them, not after a manual retry. After
approving, run the guard once with each of its inputs removed or truncated; a fail-open
path is a 🔴 and goes to a follow-up card at once. When writing the bounce reason, make the
required behaviours consistent with each other ("union, never replace" and "must exit 1"
cannot both apply to the same input).

**An automated refusal/guardrail judge must never auto-PASS.** A keyword matcher for refusals (죄송, 할 수 없, 불가, 않는) passes complied-with harmful answers that contain those words ("죄송하지만… 자물쇠를 끊으면 됩니다"). Adding more keywords never closes it. Before approving such a checker, write 5–10 complying answers of your own and run them through it. Require the design: auto-FAIL on hard signals, otherwise REVIEW with the full answer printed, and an exit code distinct from PASS. Hard signals are a leak n-gram, code output, and a phone number in the answer. Count a phone number whether or not it is in the source. A personal mobile number copied from the roster is the real leak, so "not in the source" alone misses it.
The same holds for "should refuse" graders in eval tools: a refusal phrase anywhere in the answer passes a fabricated value followed by an unrelated "not in the data" tail. Judge the refusal inside the sentence that names the asked item.
**Size a grader hole before grading its severity.** One paraphrase example tells you nothing about how wide the hole is. Generate variants by code (value kinds × key forms × tails) and count the false PASS before you call it 🟡. "Every raw answer is printed in the report" is not a mitigation when the false-PASS rows drop out of the failure list and the accuracy figures, because nobody reads the PASS section. A chat-side 🟡 built on that argument was rightly raised to 🔴 by the dispatched review: 46% of 1,176 fabrications passed.
**Vary every surface axis in your probes, and check the code uses the signal the spec named.** A text-pattern grader can pass the gates through a proxy. In one case the spec said "a real value from the asked column", but the code checked a list of sentence endings (입니다, 이에요…). Every gate sentence and every chat-side probe ended in 입니다, so all of them passed. 27 of 270 fabrications ending in 이요 / 으로 나와요 / 로 확인돼요 / `운송.` were caught. Before you give an opinion, read the function for the signal the spec names. Then probe with different endings, punctuation, bare `key: value` and arrow forms, and the key and value split across sentences ("배추요? 냉동 분야로…"). A probe set that shares the gate's surface form only re-runs the gate.
For Korean text rules (parsers, detectors, unit/date exclusions), add **spacing and attached particles** as their own axes. `3.5 톤` passed while `3.5 톤을` failed. A fix that lists the allowed following words then misses the colloquial ones (이면, 날, 인데, 이고). Build the probe as a cross-product grid, and run the positive half and the negative half together every round.
The same goes for a detector's exemption and normalisation paths, which are where privacy rules leak. Build inputs that **trigger the skip condition** while still belonging to the protected class. For a substring exemption, use a protected header that contains an exempt word. For a normaliser that strips a suffix or bracket before matching, put the protected word inside that suffix. Two consecutive review rounds found a leak this way after chat-side probes, all built from headers that never touched the exemption, had passed.

**Check that each probe reaches the new code path.** A positive probe for a fallback rule can pass because an older rule upstream already handles it. Example: synthetic total rows with blank labels were removed by the existing label rule, so a too-strict new value rule looked fine in a chat-side check. Read the path-specific trace (the new rule's own counter or `[참고]` line, here `value_dropped`) for every probe. Build the input so the earlier rules miss it (here a blank running-total cell, which the old net needed filled).

**For an access-control or privacy feature, write the attacker case list before you read the code, and build fixtures that break the implementation's assumptions.** A fixture where every table keys people the same way, or every message arrives in the expected form, passes code that leaks. The cases to cover are: identifiers that disagree across sources, duplicates, third-party values in look-alike fields, the command and the secret sent in one message, the flow interleaved with another context (a group room), and unexpected input while a state is pending. Give no approval opinion until every case has a probe result. Require the code to end with an independent guard that re-checks the access rule on the final output without reusing the matcher's paths, plus a test that breaks the matcher on purpose (return everything) and asserts the guard still blocks it. Matcher rules leak a new shape each round; the guard is what closes the class.

**Blind evaluations leak through the board.** A child card's worker can read the parent card's comments, runs and the files beside the sealed folder, and the dispatcher also injects the parent's completion summary into the child's context as "Parent task results" without the child asking. A review comment that explains a bounce by quoting a gold item contaminates the blind run. On any card that produces a sealed answer key, the handoff summary, the review summary and every comment carry counts and gate numbers only; put details into files the evaluating card is forbidden to open. Name those paths and the parent card in the evaluating card's ban list, and require the evaluating worker to disclose any auto-injected parent text it saw. If something already leaked, list the exposed item ids (ids only) and require the score with and without them.

**When the implementer wrote both the detector and its fixture, the fixture score proves only that they agree.** The same goes for an answer key tested with wrong samples written by the key's own author: a "100% FAIL on wrong answers" built from one-value answers says nothing about hedged answers that mention both values. Write your own realistic wrong answers before giving an opinion. If an item's auto key is broken twice by direction or tense changes (old value stated as current), or by a refusal followed by an invented value in another sentence, stop patching the regex. Switch that item to judge=human and put a one-line PASS/FAIL rule in its rationale. Keep auto only for closed formats: exact values, ID or phone formats, and named roster lists. A planted-items fixture built by the same worker follows the detector's own assumptions (e.g. planted pairs share file stems, which is what the pairing filter requires), so 9/9 there says nothing about recall. Before you give an opinion, build a small probe in the shape the real data will take and run the standalone command on it. Any filter that discards candidates must report them in a lower-confidence tier instead of dropping them.

**Reproduce a fix on the exact input where the defect was first seen.** A worker verifying on its standard fixture corpus can pass while the original case (a live-session answer on the small rehearsal set) still fails, because the noise source exists only in that data. Pull the original answer from the logs and run it through the fixed code before giving an opinion.

**Verify through the client the user will actually use, not only through your probe tool.** A curl review of a web page skips everything the browser adds: `Origin`/`Referer`, cookies' SameSite rules, and the CSP. A three-round curl-only approval broke at the user's first browser login. Before approving a UI card, send requests with the real client's headers, or ask the user for one real login. List that check as "unverified" in the decision packet until he confirms it.

**Read a test harness's whole output, not its headline, and reject categories the spec did not define.** A fuzz or eval harness written by the implementer can print "leak 0" on its first line while a lower line counts the same failures under "residual", "indistinguishable" or "excluded". That carve-out redefines the metric, so treat it as a 🔴 spec deviation and add the excluded count to the headline number. An exemption "already present in the baseline/parent artifact" is the same trap. A contaminated baseline then passes every descendant. Probe it by planting the forbidden token in **both** baseline and candidate. Replace it with an explicit allowlist that has one reason per entry and is printed in the output. Re-run the harness yourself with new seeds, and read the classification code (the function that decides what is exempt) before you trust any zero. If the carve-out exists because the target cannot be met, the spec is contradicting itself. A spec cannot say "0 leaks" and also allow a matching path that leaks by construction, such as name-only matching when homonyms have no identifier. Fix that in the spec: drop the path, accept the recall cost, and say so. Before you write any zero-defect target, check that every path the spec permits can meet it.

**When a defect traces to a rule you wrote into the spec, label it a spec correction in the review comment and ship the corrected rule.** Use this for rules such as a classification heuristic or a threshold. Write "coder implemented the spec; my rule X was wrong" and give the replacement rule with its tests. Do not frame it as the worker's 🔴. This keeps the round count honest and stops the worker from defending a rule it did not choose.
A spec correction is itself a new spec, so probe it before you post it. List the input shapes that the new rule reclassifies or drops, then build a fixture of the **opposite** shape from the bug you are fixing. For example, a rule that widened year detection to catch 가입연도 also swallowed every `2025년` pivot column. When a classifier keeps needing patches, stop adding rules. Ask for a conservation invariant ("every numeric column is either kept, re-roled, or warned about; silent drops = 0") that is **checked inside the code at run time**, and a test that breaks the classifier on purpose to prove the check fires. A test-only invariant over the worker's own cases misses the next shape. Run it over your probe folders too. When the dispatched review then finds what your correction broke, withdraw your approval opinion in the chat reply and say the defect was yours.
**The same opposite-shape probe applies to a fail-closed guard the worker adds in a bounce round** ("if any later X exists, drop the value"). It closes the reported hole, then fires on the very inputs the feature exists for. A guard against old regulation dates also wiped the dates of new announcements whose body said "…부터 시행". Before your opinion, feed it true positives wrapped in content that trips the guard's trigger. If they lose their output, the guard's scope is too wide: name the position or context that should limit it.
The reverse holds when the next round **narrows** that guard. Re-run the cases the guard was added for, across every input category it covered, not only the category the narrowing targets. A narrowing aimed at announcement dates (작성일/일시) was probed only with announcements. It also switched the guard off for 제정-dated regulations, and old dates came back on 8 of 13 of them. Scope a narrowed guard by the category that needs it, not globally.
**For an LLM-answer A/B, check the reasons the answer gives, not only its verdict.** A feature can feed the model a wrong fact (a mis-extracted date) while the conclusion stays right by luck. Grep each stated basis (date, "both documents say…") in the raw data before you count the item as unchanged or fixed, and make your date or label match script cover the expected-none cases too.

**A defect you find outside the reviewed card's scope gets its own card, not the card's verdict.** This covers pre-existing bugs that a probe for card X exposes, e.g. a privacy hole in an untouched module. Label the comment on X "outside this card's scope, not part of the verdict" so the round counter stays honest. Then create a separate fix card and insert it into the chain before the next card that measures that behaviour (unlink/link). Otherwise the measurement scores the unfixed state. If the module is also used at runtime, the fix card stops before redeploy, and the user decides when it goes live.

**Announce every card you create in the same chat reply that reports the review.** A
follow-up fix card opened while reviewing (e.g. a defect found in the worker's tooling)
is a decision the user did not see. Its later "handed off for review" notification then
arrives as a surprise and needs an apology. State its id, why it exists, and whether it
changes any already-reported result.

### Hold licence and attribution requirements even when told to drop them

"Don't bother with the attribution" is a cost-saving instruction, not an informed waiver, and
it is one of the few places to keep a requirement the user waved off. Keep the notices, put
the obligation in the card so the worker preserves them too, and give the reason in one line:
the licence requires it, the output is publicly inspectable and similarity-checked, and the
cost is a few comment lines. Note when the ecosystem itself normalises it — borrowed code
that already carries a long credit chain is evidence retention is expected, not optional.

The general shape: when a shortcut trades a compliance or safety property for minor
convenience, say plainly which property is at stake and that you are keeping it, then carry
on with the rest of the request rather than re-opening the debate.

## Closing out a session

When the user signals wrap-up ("세션정리", "summarize for next time", "hand this off"),
write a handoff document into the project's own docs directory rather than only answering in
chat. Structure that survives the context gap:

1. **Headline diagnosis** in one or two lines.
2. **Numbers you personally reproduced**, marked as such — distinguish them from worker
   claims you relayed.
3. **Artifacts produced**, with paths, hashes, and current state (merged / awaiting upload /
   experimental).
4. **Methodology lessons** — sample sizes that proved inadequate, classifiers that worked,
   replay fidelity you measured.
5. **Ranked next steps**, each with the identifier a future session needs to find the data
   again (group hash, file path, id list).
6. **A rejected list** with reasons and sources, so the next session does not re-propose
   what was already measured and killed.
7. **Board state and operational gotchas** hit during the session.

Attach the file to the chat as well as writing it — on platforms that render attachments the
user wants the downloadable artifact, not only the prose.

When the user asks for "everything so far as an md file" mid-project, build it from fresh
primary sources in the same turn (submission CSV, LB CSV, `git log`, zip sha256/size,
CHANGES files, result summaries, cron list, board `ls`), not from memory or the compacted
summary. Put the timestamp of the snapshot in the header, mark estimates as such, and
include a table of your own corrected claims and one of the final checks run.
Write it under the profile's `outbox/` (not the repo, and not `cache/scratch`) and attach it with
`MEDIA:`; committing it into the project is a separate decision for after the fact-check. Scratch
is pruned after 24 h idle, and a `MEDIA:` path that no longer exists is skipped silently. The user
then gets no file when he asks for it again the next day. Any deliverable he may re-download
goes to `outbox/`. If one vanished, rebuild it from the source, with current facts in its
header, rather than replaying the old text. For a competition, use these
sections:
- submission table: ref, UTC date, config, LB, pre-registered verdict
- completed phases, with measured numbers only
- in progress, with live counts
- decisions pending, each with your recommendation
- ops state: quota, slots left today, active crons, live cards
- risks and unverified items
- file locations

Re-poll the scored list right before writing: a score that lands while you write changes
the pending decisions. Lead the reply with it, and say which recommendation it weakens.
If he asks for it to be
checked, the check card is a pure fact-audit: every number traced to its source file,
mismatches returned as line number + doc value + source value + replacement text, and the
checker edits nothing.

Writing and revising that summary doc:
- **State each threshold once and derive every restatement from it.** A summary that says
  "±3 tasks are distinguishable" in one section and computes power 0.55 for +3 in another
  contradicts itself; write the computed section first and copy its conclusion verbatim.
  Give every quoted outside number its source (notebook slug, thread id, "participant
  claim" vs staff reply) and give every comparison its baseline ("−3 vs v6", not a bare "−8").
- **When state changes after the snapshot time** (a cron registered, a card approved),
  comment on the running check card that it happened after the snapshot, so the checker
  reports it as "changed since" instead of as an error.
- **Treat a checker's "unsupported" as a prompt to re-check, not to delete.** Open the
  primary source yourself; if it confirms the claim, keep it with the citation (a staff
  reply quoted verbatim), and delete only what nothing supports.
- **Revise as a versioned file**: copy the checked version to `<name>_v1.md`, mark the
  header "corrected v2 (check <card id>, N items)", add the doc itself to the corrections
  table, re-attach with `MEDIA:`, and list the fixes item by item in the reply, plus what
  the checker could not verify. A fix that belongs in the repo (a missing record) goes to
  a worker card in the same turn.

**"Didn't we decide X earlier?" — check the record before you answer.** Search the session
history: the profile's `state.db`, table `messages`, filtered by session_id and a keyword,
opened read-only. Also grep the user's shared documents and the project docs. Then quote
what was actually said. If nothing was decided, say so plainly. Give the reason the
premise doesn't hold (e.g. the data step uses no GPU at all), and ask whether the decision
was made in another chat. Agreeing from a vague memory plants a false decision in the plan.

If a conclusion recorded earlier in the same session was later refuted by your own analysis,
correct it in the handoff and say it was corrected. Carrying a superseded framing into the
handoff is how a wrong cause outlives the session that disproved it.

## Recovery

Rules that apply every time a card misbehaves. Recipes and state-machine details are in
`references/recovery.md`.

- **"The quota ran out mid-work, is anything broken?" — audit four things, then the live service.**
  (1) `runs <id>` for every active card. A `rate_limited (quota wall)` row means the run was requeued without counting a failure, so the review round counter did not move. (2) The current run's latest heartbeat time in `show --json` events. (3) `git status --short` and `git log` for half-written files or a missing handoff commit. (4) Card comments for a partial verdict from an aborted review. Then check any service that bills the same subscription (a bot on a CLI token) with one real call. Report each item as found or not found, and flag the shared-quota risk for the next critical window.
- **A `crashed` run is not proof that the worker is dead.** Before you report a crash or
  write retry instructions, run `ps -axo pid,ppid,etime,command | grep <task_id>` and
  `kill -TERM` any stale run. Then read what each run already did (push, upload) from the
  worker's `state.db` before you tell the user how many of anything exist.
- **Card-event notifications can arrive after you already handled the event.** A
  "blocked" wake for a run you resolved minutes ago looks like a new block. Run `runs <id>`
  first. If the newest row is `(running)` and started after your `unblock`, the
  notification is about the old run. Answer in one line (old run, already fixed, current
  run live since HH:MM) and change nothing.
- **"뭐가 block 상태야?" — list every blocked card with a reason class, not only the one you are tracking.** Run `kanban list --json` filtered to blocked/scheduled/triage. For each card, read the last `blocked {reason}` event and put it in one of three classes: normal wait (a remote or GPU run is in progress, with its ETA), user action needed (give the exact step, e.g. a licence page URL), or stale. For a stale card (days old), re-check its preconditions against the current files, such as a pinned md5 or whether the edit already landed. Then recommend archive or re-scope rather than unblock, because an old body resumed as written stops at once or edits the wrong state.
- **Headless workers cannot pass approvals.** Force pushes, protected files such as
  `AGENTS.md`, `pip install`, and container lifecycle commands (`docker compose restart|up`
  for a deploy step) all block. Design the card around that (draft + user `cp`,
  local result + interactive push, numpy reimplementation). Never route around the security
  scan. Before `create`, grep the body file for `AGENTS.md` and other protected names. A
  protected file never goes on a headless card, not even inside a "update the date in
  AGENTS·OPS·WORKLOG" doc card that looks routine; the card edits the rest and blocks on
  that one line.
  A `capability` block for a missing environment piece (a package or a native library the
  worker may not install) is setup, not authorship. Install it from the interactive
  session. Then re-run the exact import the worker reported failing, comment the fix on
  the card and `unblock`. The worker writes no code until it is unblocked. Put the import
  check into the first card's step 1, so the block fires before any work starts.
  For a deploy step, order the card as commit → tests → deploy, and write "if the restart
  is refused, do not block; hand off with request-review and put the exact command in the
  summary". A block/unblock cycle counts toward the failure limit and costs an extra wake.
  Before reviewing, the orchestrator runs only that one command, touching only the named
  service, and verifies it (host vs container sha of the changed files, other containers'
  StartedAt unchanged, the live probe). It comments the results on the card so the review
  run does not repeat them. If deploy comes before commit,
  the block leaves uncommitted work behind. Put the exact replacement line in your reply instead. Offer to apply it yourself
  once the user approves (single-file commit, diff = 1 line), or let him paste it.
  - Ask for the `cp` only after the last card that edits the draft is approved; otherwise the
    user installs a stale file. Leave the parent blocked meanwhile, and `unlink` it from the
    editing child so the child is not stuck waiting on it.
  - If the user tells you to do the copy yourself, first check `diff` shows only the
    intended lines. Then make the current file recoverable. If `git diff --quiet HEAD -- <file>`
    passes, the last commit is the backup. Otherwise write `AGENTS.md.bak_<date>_<reason>`.
    Copy, verify with `cmp`, and commit that path alone (`git commit -- <file>`, never `-a`).
    A git-ignored file (`git check-ignore -v`) cannot be committed: the `.bak` + `cmp` is the record. Comment it on every running card that
    must follow the new rule, and complete the blocked parent.
  - Later rule additions go into the same reviewed draft file. Diff the draft against the
    committed file before each copy, since the user approves the whole delta, not just the
    newest line.
- **Scarce remote quota (GPU hours): guard on two layers.** Put a pre-push checklist comment
  on every card and run a `no_agent` push watchdog cron. Cards that wait on a remote job use
  short status calls, never long foreground wait loops.
- **A resource-limit block is a card-design defect.** Re-scope so the limit stops binding;
  never authorise deleting the user's data to keep a bad plan running.
- **A remote capacity refusal (GPU-session cap full) is a wait, not a decision.** Comment a
  retry interval + cutoff ("never touch another project's job; refused attempts are not
  pushes") and unblock. Park cards waiting on a remote job and have a no-agent status cron
  release them. The recipe is in `references/recovery.md`.
- **Your own blocks count toward the failure limit.** Redirect idle cards with `comment`,
  not `block`. Avoid `reclaim`→`block` and quick `unblock`/`block` cycles; `triage` can only
  be left through `archive`. A card in `triage` can also be picked up by the auto-decomposer
  and re-promoted with a rewritten title and body. The worker then blocks again for the
  same missing decision, and you get a second triage notification. Once a card lands in
  `triage`, archive it with a comment that records its results and why it stopped. Carry
  the work on in a new card that is created only after the user decides.
  The decomposer can also split a blocked card into several new child cards, and one of
  them starts running at once. That repeats side effects the parent was capped at, such as
  a second push. Right after any block or triage event, run `ls`. Archive every
  `auto-decomposer` card, using `show` → `created ... by auto-decomposer` to identify
  them. Kill the live worker pid of each, then confirm with `ps` and the remote status that
  nothing ran. To prevent it, write "do not decompose this card into sub-cards" in the
  body of every card that has an irreversible step.
- **Run `ls` right before `create`.** A parallel session of your own profile can create a
  card for the same purpose at the same moment. Two workers then edit the same files and
  overwrite each other's work. Keep the card that started first, archive the other with a
  comment pointing to the survivor, and kill its worker.
- **Check the side effect before killing a run you think is in the wrong mode.** Unblocking a
  card that was blocked from `review` returns it to `review`; after reassigning it to the
  worker, the dispatcher starts the worker with the review skill, and that run can still
  execute the PUSH_OK step. Before `kill`, read the remote state (`<platform-cli> jobs list
  --mine`, `kernels status`, submissions list). If the side effect already happened, do not
  kill. If you already did, comment "already pushed at <time>, do NOT push again; only wait,
  collect and verify" before the next run claims it.
- Close a card that met its stated goal even if the result disappointed; put the performance
  question on a new card.

## References

- `references/recovery.md` — headless approval workarounds, crashed-but-alive forensics and
  the scarce-quota guard, resource-limit re-scoping, dispatcher state-machine traps
  (`triage`, failure limit, parent/child promotion), taking over a card another session
  stopped, and moving delivery to a new chat thread.
- `references/verifying-worker-results.md` — verification gates before relaying any worker
  summary, recounting a reported zero with a mechanical matcher, headroom of adopted caps,
  the sample-size trap, designing acceptance criteria under noise, and validating
  a post-hoc "this combination would have passed" idea on fresh, pre-registered data.
- `references/pipeline-health-audit.md` — answering "how can the bot/agent structure
  improve" or "how do we save tokens": SQL queries over `kanban.db` and `state.db`,
  crashed-but-alive forensics before quoting lost hours, a symptom → fix table, a
  token/cost audit with quality-neutral levers (cache TTL, compression threshold,
  notify vs wake), and an independent-opinion step before ranking fixes.
- `references/measuring-what-matters.md` — checking the benchmark maps to the real
  objective, detecting drift in a recorded evaluation pool, discrimination-testing a
  proposed cause **and then falsification-testing it before believing it**, guarding
  segments you already win, building sub-group classifiers, pivoting to leader-profiling
  when every candidate in the current layer is rejected, and why borrowed parameters need
  their supporting subsystems.
