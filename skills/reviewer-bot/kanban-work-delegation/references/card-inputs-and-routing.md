# Card inputs, routing and relay checks

## Contents

- Routing (step 2)
- Card inputs (step 3)
- Relay checks (step 6)
- 3. Write the card so it cannot be satisfied by prose

Depth for steps 2, 3 and 6 of SKILL.md. Each rule names the step it belongs to.

## Routing (step 2)
- **Lookup work that needs a loop of CLI calls goes to coder-bot, ending in `kanban_complete` with no review.** Examples: licences for dozens of datasets, batch status checks. helper-bot runs single queries and blocks with needs_input when the task needs a script.
- If helper-bot has already blocked, check `runs <id>` for a live worker. If there is none: comment the reason, then `assign <id> coder-bot`, then `unblock <id>`.
- **Records that cite verdicts, causes or source cards (submission records, judgement summaries) go to coder-bot with `request-review`, not to helper-bot with `kanban_complete`.** A review-less card fills gaps by copying a neighbouring section, which brings in the wrong source card, the previous entry's composition, and a decision verb where the user decides. It can also rewrite the prefixes of an existing entry. helper-bot is only for verbatim copy of values the body supplies. Whatever the route, diff the commit against its parent: there must be no `-` lines outside the intended section.
- Several coder-bot workers run in parallel. Serialize only cards that share a working tree plus a shared doc, or a single-job host (one GPU box). Do this by chaining parents, not by assuming the bot is a bottleneck.

## Card inputs (step 3)
- **Pre-register a deterministic rule for any input a queued card would otherwise wait on you to pick.** Typical inputs: the pool, arm or baseline to use after an upstream verdict. Post it as a conditional comment now, for example "if upstream arm X is adopted use X's pool, else pool Y; write path, rows and md5 in the first heartbeat". Without it, an upstream card that finishes overnight leaves the GPU idle until someone next wakes the reviewer.
- **When the user approves a gated card ("GPU 바로 진행") before its prerequisite card is reviewed, keep the review gate and remove the human wait.** Unblocking now starts a worker with no kernel to push, and unblocking without review spends quota on an unverified artifact. Instead:
  - comment the approval (time, quota estimate) on the gated card;
  - arm a no-agent cron (~10 min) running a small script that unblocks the gated card only when the prerequisite's status is `done` (reviewer-approved). It prints nothing while the prerequisite is running, in review or sent back. It writes a state file after acting once, expires after a few days, and routes its one message through the quiet-hours emitter;
  - run the script once by hand and confirm it reads both statuses and exits silently.
  `hermes kanban show <id> --json` nests the fields under `task` (`d["task"]["status"]`). A parser that reads the top level gets `None` and never fires.
  Tell the user the real start condition ("after review approval, automatically") and the expected timeline.
- **Make sure paired numeric requirements can be met together.** Examples: a per-group sampling distribution against a minimum batch size, a cap against a count, a time gate against a mechanism gate. For a time gate, convert the headroom into the unit the mechanism spends (headroom seconds ÷ mean step seconds from baseline traces) and compare it with the fewest steps the mechanism needs to show its effect. If the headroom is smaller, the registered verdict is decided before the run; split the gates (mechanism verdict vs ship verdict) before spending quota. When a worker flags such a conflict and documents a reasonable deviation, accept it in review. The spec error is the designer's, and a rejection round costs a full cycle.
- **Never fold a correction (a known label error, a broken filter) into a card that can be skipped or made conditional.** Give the correction its own always-run step: a load-time filter commented on every consuming card, plus one same-seed A/B card that also becomes the new control. When the host card is later made conditional, a bundled correction silently drops out, and every queued card keeps training on the known-bad rows.
- When a correction changes a shared training input, comment it on every queued consumer together with "the control must use the same corrected input, else block and ask". Otherwise the correction and the card's own variable are confounded.
- When a follow-up card will consume a harness or library that another card is building, comment the extra interface needs (ids, cached arrays) on the builder card before it starts. Adding them after review costs another round.
- **Review runs execute the card body, not later comments.** When the designer profile is also the card's review worker, a body line like "if it passes, reviewer creates the follow-up card" makes the review run create it. If the chat session creates one as well, you get two parallel cards with conflicting specs and artifacts, and a "no new cards" comment does not stop it. In the body, write "the Discord reviewer creates … (review run: do NOT create cards)", or create the follow-up before the review runs. This includes the final-check (fable-bot) card: a packaging design that said "after the clean reproduction, the reviewer assigns the final check" made the approving review run create it at once, which skipped the reviewer's own planned re-run. If a duplicate appears anyway, keep the valid artifact as a named variant. Then comment on both cards so the workers keep their outputs apart: separate dirs and datasets, and diffs against the other card's commit.
- **When the user pre-approves a follow-up on the condition that a running card's result is good ("결과보고 해도되면 바로 진행"), create the follow-up now as a child (`--parent <running card>`). Make its first step a numeric gate on the parent's artifact**, for example "verdict PASS and cumulative Δ ≥ threshold, else kanban_block with the values; do no uploads". Comment on the parent which fields the gate reads, so the parent's report includes them. If the parent fails the gate, comment the measured values on the child and `archive` it before it ever runs. Check `runs <id>` shows no runs first. Do not let it start and block, because an expensive first step (a large upload) can run before the gate. A the remote platform submit stays out of the child's scope; it still needs the explicit submit instruction.
- **To revive an old queued card for a new plan, rewrite it in place instead of creating a duplicate.** Run `kanban edit <id> --title ... --body "$(cat body.md footer.md)"` with the current baseline, rule and template. Re-chain with `link <new parent> <id>` **first**, then `unlink <old parent> <id>`. If you unlink first, the card has no parent for a moment, becomes `ready`, and the dispatcher can claim it onto a busy single-job host (the GPU box). Linking to a parent that is not done flips `ready` to `todo`, which is the hold you want. Afterwards, confirm with `runs <id>` that no run started in between. Re-subscribe the card to the current thread.
- **To insert a new card into a serial queue (A → C becomes A → B → C), use the same order.** Create B with `--parent A`, run `link B C`, then `unlink A C`. Check `show C` lists only B as parent and `runs C` shows no run. Also list A's other children: a stale card left from an older plan can hang off the same parent (sometimes already `ready`) and would start alongside B on the single-job host. Move it to the end of the queue the same way (link to the last card first, then unlink); the `link` output "was ready and is now todo" confirms you caught one.
- **A start gate in a card body must use commands that work in the worker's non-interactive shell.** On the WSL GPU host, `nvidia-smi` is not on the ssh PATH; write the full path (`/usr/lib/wsl/lib/nvidia-smi`) and say "if the check command fails, treat the GPU as busy and reschedule", so a missing binary never reads as an idle GPU.
- **To hold back a queued card whose precondition just broke (host disk, upstream result), edit its body; do not try to block it.** `block` is refused on a `todo` card. A parent completing promotes the card and a worker starts from the body, so a comment can arrive too late. Prepend a numeric first-step gate with `kanban edit <id> --body "<gate>$OLD_BODY"`, for example "check X ≥ N, else kanban_block with the value". Then `schedule <id> "<reason>"`. Remove the gate when the condition clears.
  When the user stops the whole lane ("GPU 제출 스탑"), not just pauses on a precondition: comment the instruction and the path of a saved copy of the body, then `archive <id>` every queued child that would push or submit once its parent finishes. In the same turn, check that nothing else can still spend the resource: running kernels (`<platform-cli> jobs list --mine --sort-by dateRun`), armed submit/unblock crons, and same-lane cards on other boards. Leave the parent's CPU-only work running, and comment on it that the downstream step is stopped. Report what was stopped and what still runs (a submission already scoring cannot be stopped).
- **"Try X; if the gate fails, revert and fall back to Y" cards: the abandon gate must be exactly the user's stated conditions.** Put any stricter check you add (byte-identical run logs, bus logs) in a report-only section. Those files carry wall-clock times and DB names, so an abandon gate built on them FAILs on correct code. Spec replay/prefix comparisons to run the reference execution in a fresh output folder. Ids derived from existing folders (AI call counters) shift otherwise, and every N≥2 comparison mismatches. Say in the body whether the worker may repair the checker (never the product) and re-run before declaring failure, and require the first failing output to be kept. Without that line the worker either abandons good code over a checker bug or retries against the letter of the spec. Then you have to explain the deviation to the user.
- **Chain a final check (fable-bot) to a card that is still running by creating it with `--parent <running card>`.** It stays `todo` and starts only after that card is approved (`done`), so the final check sees the reviewed artifacts. Tell the user the real start condition, and write "use the sha in the approval comment as the reference" into its body.
- **Before a user's explanatory wording goes into a spec as output text (a label, a reason in parentheses), find the code path that produces the case and confirm the wording names the real cause.** A user's guess ("none because single batch") written verbatim makes the shipped output state a false mechanism; the worker then has to stop mid-card. If the code says otherwise, ask with two options (code-accurate wording, recommended / the user's wording as-is) before creating the card.
- **Write a packaging secret-scan gate in three tiers**: block only real-key shapes (known prefix + ≥24 token chars, `Authorization: Bearer <20+>`); list short literal mentions (docs that say "grep 0", docstrings, test dummies) as report-only with file:line and length, values masked; and require a positive control (random fake keys of each shape in a temp file outside the tree, all must be blocked). "Any prefix hit = stop" halts on the project's own documentation, and loosening it without a positive control can silently blind the scan.
- **Keep card-body templates and design files you reuse outside the auto-pruned scratch dir** (e.g. the profile folder). Scratch entries idle for a day are pruned, and a card created from a missing template file gets an empty body that the dispatcher may start.
- **Reserved resources written in a body (seed ranges, slugs, dataset names) are not claims.** Another card can consume them first through the shared ledger or account. Claim from the ledger when you write the card, and have the worker re-check right before use.
- **Parallel cards on one working tree that append to the same shared files (work log, overrides table, seed ledger):** give each card disjoint pre-assigned ranges in both bodies (each body names the other card's ranges), and tell each worker to re-read the shared file right before editing and commit right after. Otherwise one worker's commit silently carries the other's ledger lines, or a later write clobbers them.

## Relay checks (step 6)
- **Bound-check collected values against known limits before relaying.** Examples: a leaderboard score above the current LB top, or a field reported missing for most rows. Such values mean a parsing bug, not a finding. Open a fix card that names the exact key to read.
- **Re-list board status before every progress report.** A review worker can complete a card without its completion message reaching the chat. Reporting that card as still running hides a result the user should see.
- **Own the delivery of every result you dispatched; never promise "it will arrive in this thread".** A finished final-check card or a finished background subagent can produce no chat message at all, and this user then has to ask ("결과 안나왔어?") — he treats that as a repeated failure. At the start of EVERY user turn, before answering the new message, sweep all open dispatches: `kanban ls` + `runs <id>` for cards you created, `delegate_task(action='list')` plus the subagents' output files (e.g. their `REPORT.md`) for background research, and the cron state for armed watchers. If anything finished, lead the reply with its result in your own words. When the user is waiting on a long dispatch, arm a no-agent watcher that posts once on completion instead of relying on the runtime to relay it. Say "I will check and report", not "the result will come here". An armed watcher cron does not replace the sweep: cards chained with `--parent` can finish inside one turn gap and the watcher can miss or lag them, so re-read `runs <id>` for every card you created in the thread anyway.
- When another session raises a leak or bias concern about a probe, first check what the probe actually did (scope, split, controls) from its script. Answer with that before re-running anything.

## 3. Write the card so it cannot be satisfied by prose

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
