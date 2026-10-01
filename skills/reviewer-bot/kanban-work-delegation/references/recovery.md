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
4. Such crashes usually come from one long foreground wait (a poll of 400 s or more). For
   cards that wait on a remote job, require short single status calls or repeated plain
   `sleep N` calls, never wait-loop scripts.

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
