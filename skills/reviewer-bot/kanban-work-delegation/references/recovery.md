# Recovering stuck, crashed, or mis-steered kanban cards

Depth for the Recovery section of SKILL.md. Each item: the rule, then why.

## Headless workers cannot pass approvals

- **Dangerous commands (force push, history rewrite, remote-destructive).** The card blocks
  with `needs_input` at that step, because nobody is there to approve it. Plan for it in the
  card:
  - the worker stops after the local result and a backup (`git bundle`);
  - you verify the local result yourself;
  - you run the single push from the interactive session once the user asks, with
    `--force-with-lease=<branch>:<expected old sha>`;
  - you check the remote SHA and per-path state through the API, and close the card with a
    comment that records who pushed.
- **Protected files such as `AGENTS.md`.** The approval prompt times out and the card
  blocks.
  - Have the worker write `docs/<name>.draft`. Review the draft, then give the user a
    one-line `cp` to install it.
  - Afterwards confirm the installed file with md5 and a section-level diff.
  - If the user already wrote their own version, build a merged preview that keeps their
    edits (for example a header line they added) instead of overwriting it.
- **`pip install`.** The security scan's threat-intel lookup times out, and nobody can
  approve the install.
  - Do not route around the scan with conda, other indexes or vendored wheels.
  - Put a small stdlib or numpy implementation of the needed algorithm into the card, step
    by step, with the paper citation.
  - Loosen only the criteria that the substitution itself affects. For example, fold sizes
    vary slightly under iterative stratification.

## "Crashed" does not mean dead

The dispatcher can record "pid not alive" while the old worker process keeps running. The
retry run then works the same card alongside it, and both can push or poll the same
external job.

1. Before you tell the user it crashed, or write instructions for the retry, run
   `ps -axo pid,ppid,etime,command | grep <task_id>`.
2. Terminate the stale run with `kill -TERM <pid>`. Comment on the card which run survives.
3. **Killing it does not undo what it already did.** Read what each run executed from the
   worker's session DB. `~/.hermes/profiles/<worker>/state.db`, table `messages`
   (session_id, timestamp, role, content), holds every tool result.
   - Grep it for the side-effect marker, e.g. `content like '%successfully pushed%'`.
   - Answer "is there only one?" from that evidence, not from a listing that collapses
     versions.
   - If you already told the user a wrong count, correct it plainly and say why the first
     check missed it.
4. Do not assume the cause is a long foreground wait. Many "pid not alive" verdicts land on
   workers that are still running, a dispatcher fingerprint issue (see
   `pipeline-health-audit.md` §3). Long waits are still a cost and a real crash source on
   their own: for cards that wait on a remote job, require short single status calls or
   repeated plain `sleep N` calls, never wait-loop scripts.

**When the remote job consumes a scarce quota, prevent a repeat on two layers:**
- A pre-push checklist commented on **every** card of the board:
  - the remote job is not RUNNING/QUEUED;
  - there is no second live worker for the card;
  - a retry run picks up the previous run's push instead of pushing again.
  Each push is logged as a card comment.
- A `no_agent` cron watchdog, every 10 min, silent when nothing changed.
  - It reads new push markers from the worker's `state.db`.
  - It warns on more than one quota-using push in the window, or more than one live worker
    pid per card.
  - Its first run takes a silent baseline so old pushes are not replayed.
  - Replay a known past incident to test it before scheduling.

## Waiting on a shared remote slot is not a decision block

A worker that blocks because a remote push is refused for capacity (e.g. the account's
concurrent GPU-session cap is full, sometimes with another project's job holding a slot) is
waiting on a resource, not asking for a decision.
- Comment a retry policy: interval (≈5–10 min), a hard cutoff (hours), the rule that refused
  attempts do not count toward the push cap, and **never cancel or touch another project's
  job**. Then `unblock`. Name which card goes first if two cards compete for the slot.
  The pre-push "nothing of ours is RUNNING" check (`<platform-cli> jobs list --mine`) does not
  prove a free slot: the account-wide cap counts sessions the list does not show (other
  projects, web-UI sessions). Expect the refusal, and write the retry policy into the GPU
  card's body up front so the worker does not block.
- For a card that pushed and now waits for the remote job to finish, park it with
  `reopen-review` → `schedule` → `assign <worker>`. Add a no-agent cron (every 10 min) that
  polls the remote status and, on the first terminal status, runs `assign` + `unblock --reason
  <next steps>` once (flag file per job). The reason carries the verified decision, so the
  resumed worker does not re-derive it. Without this, the worker either long-polls (crash
  risk) or blocks repeatedly (triage risk).
- **User approves the GPU card before its prep card is done ("GPU 바로 진행해줘").** The push
  cannot happen yet, because the kernel does not exist. Record the approval as a comment on the
  blocked GPU card. Then arm a no-agent cron (10 min) whose script unblocks the GPU card once,
  when the prep card reaches `done`, i.e. after the dispatched review approved it. It stays
  silent while the prep card is running, in review or bounced, so an unreviewed kernel never
  spends quota. Give it an expiry that reports once, a state file so it acts only once, and
  route its output through the quiet-hours emitter. `hermes kanban show <id> --json` nests the
  fields under `"task"`; read `d["task"]["status"]`, and test the reader on the live cards
  before arming (a top-level `.get("status")` returns None and the watcher never fires).
  Tell the user the approval is recorded and when the push will happen, not that it is running.
- **A one-shot submit cron is not a score notifier.** After it submits, its idempotency lock
  makes every later tick exit silently, so the result is never announced. Once the submit is
  confirmed in the submission list, report it to the user, move the plan file to `_disabled`,
  remove the cron, and check that a result-watch cron is scheduled for the new ref (re-arm it
  if not).
- When you finish with a one-shot release cron, remove it, or pause it if it can be re-armed.
  To re-arm a release cron for a new phase of the same card, switch it to a new flag name and
  seed its seen-line state to the current log length, so old lines do not fire it.

## Resource-limit blocks are card-design defects

When a card stops on disk, quota, or rate limits, the worker asks which resource it may
consume. Answering that directly ("delete these directories") authorises destroying the
user's data to keep a bad plan running.
- Re-scope the work instead so the limit stops binding: stream and discard rather than
  accumulate, sample rather than exhaust.
- Then `comment` the new design and `unblock`.
- Ask what the card actually needs to keep; it is often a tiny fraction of what it was
  collecting.
- Deleting the user's accumulated artifacts is never the orchestrator's call, and never the
  orchestrator's hands either.

## Dispatcher state-machine traps

- `hermes kanban reclaim <id>` releases an active claim.
- **Your own blocks count toward the card's failure limit.** Blocking to change instructions
  looks to the dispatcher like a worker failing repeatedly. Enough of them route a card whose
  work was fine into `triage` and record it against the assignee. To redirect a card that is
  *not* mid-run, `comment` and let the dispatcher re-claim it. Keep `block` for genuinely
  halting work.
- `reclaim` right before `block`, or a short `unblock`/`block` cycle, trips the loop
  detector and dumps the card into `triage`.
- **`triage` has no way back.** `promote` rejects it ("promote only applies to 'todo' or
  'blocked'"). `unblock` rejects it ("not blocked/scheduled"). `complete` rejects it
  ("unknown id or terminal state"). The only exit is `hermes kanban archive <id>`. When the
  deliverable is already produced and verified, archive it with a comment recording the
  verification and why the card ended up there.
- **A card in `triage` does not sit still.** The auto-decomposer can rewrite its title/body
  (even translate it) and re-promote it to `todo`. A worker then claims it with no new
  decision and blocks again, and you get a second "routed to triage" notification for the same
  unresolved question. As soon as a card lands in `triage` with a decision still pending,
  `archive` it with a comment recording what exists (artifacts, measured gate values, what was
  NOT run). Put the continuation on a fresh card created after the user decides. Put the
  user's decision on that new card as a `사용자 결정(override): ...` comment, with "do not
  re-ask".
- A card that stops on a pre-registered gate (e.g. "stop before the one-shot evaluation if
  the drift check fails") needs a user decision to continue. Don't unblock it expecting
  progress: the worker correctly refuses again, and that refusal counts toward the failure
  limit.
- A parent card blocked or in review keeps its children in `todo`. Completing or unlinking
  the parent promotes them to `ready`.
- Close a card that met its stated goal even if the outcome disappointed. A faithfully
  implemented spec that underperformed is a spec failure, not a worker failure. Put the
  performance question on a new card.

## Taking over a card another session of yours stopped

When the user hands you a card another session halted ("다른 세션에서 하던 거, 해야 되면 진행해줘"):
1. Read `runs <id>` and the whole comment thread. Two sessions often left conflicting
   instructions (a dispatched-review bounce and a chat comment a minute apart).
2. Decide whether the card is still worth finishing given what changed since (a newer card
   may have made its question secondary). Shrink it to what is still needed.
3. Post one reconciliation comment: the rule the worker follows, the instruction withdrawn in
   so many words, and why (usually the scarce resource).
4. List the files the stopped worker left (`git status --short`) as "unverified, re-verify",
   and name other cards' files that must stay out of the commit.
5. Say what happens to a remote job still running: no further push; read its output as
   reference only, or record "user stopped, no result" once the user cancels it in the web UI.
6. Only then `assign` back to the worker and `unblock` (check no live run first).
7. At review, look for the withdrawn instruction surviving as a changed default in the code; it
   does not touch results but breaks reproduction of the recorded numbers.

## Moving delivery to a new chat thread

When the user moves the work to a new thread ("여기서 하게 변경해줘"), move every path in one script:
- cron `--deliver` for each job of that project, including jobs set to `origin` (it resolves
  to the chat that created the job, i.e. the old thread);
- ids hard-coded inside watcher scripts: grep the profile's `scripts/` for the old id, replace,
  then `py_compile`;
- every open card's subscription: `notify-subscribe` the new thread first and
  `notify-unsubscribe` the old one second, so no event falls in the gap; keep each card's
  mode. `notify-list` prints `mode=` only for non-default modes, so a parser that greps
  `mode=` must set notify-mode rows explicitly;
- remove watchers whose job is done instead of moving them, and update the thread id in the
  project skill.
Verify with `notify-list` (new id on every open card) and `cron list` (Deliver lines).
