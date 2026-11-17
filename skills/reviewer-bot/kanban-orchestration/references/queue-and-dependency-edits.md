# Editing a live card queue (serial GPU host, review side-effects, parking)

Use when a card must be inserted, reordered, held, or re-scoped while other cards in the same chain are running or waiting.

## Insert a card into a serial resource queue
1. Create the new card with `--parent <card that must finish first>`.
2. `hermes kanban unlink <old_pred> <successor>` then `hermes kanban link <new_card> <successor>`.
3. Check the result: `for t in ...; do hermes kanban show $t | grep -m1 parents; done`. A child goes from ready to todo when it is linked, which is expected. The claim re-checks parents, so it will not start early.
4. Tell the user the whole queue order in one line (host: A → B → C).

## A review run asks for work that a follow-up card also does
- The review BLOCK wins, and the implementer does it on the original card. Do not let both cards do it.
- Comment on the follow-up card. Drop that step, give the artifact path the original card actually wrote (check `ls` after the fix lands; the path often differs from what the spec guessed), and say how to verify it (md5 list, repro assert json).
- If dropping the step frees the follow-up from the shared resource (for example, it no longer needs the GPU host), re-parent it straight onto the original card so it runs alongside the queue instead of behind it.

## Hold a card at the user's request
- `hermes kanban schedule <id> "보류(사용자 결정 <date> ...). 근거 ... SCHEDULED_UNTIL 없음 → 자동 깨우기 대상 아님. 재개는 사용자 지시로만."`
- Do not use block. A block on an idle card can trigger triage decomposition, and a second block auto-splits the card. A scheduled card with no `SCHEDULED_UNTIL=` is never auto-woken.

## A better path appears after a card was specced but before it starts
- Comment the revised spec on the card, marked "승인 대기, 그 전까지 기존 스펙 유효". When the user approves, add a second comment that records the decision and states what stays fixed (sample, verdict rule, budget). A comment is enough for a card that has not started. Never edit the body under a running worker.
- Ask about any package install or rule exception the new path needs in the same message.

## Reading worker state without waiting for notifications
- Last result text: `sqlite3 ~/.hermes/kanban/boards/<board>/kanban.db "select summary from task_runs where task_id='<id>' and status!='running' order by id desc limit 1"`
- Review comment `#N` named in a BLOCK message: `select body from task_comments where id=N`.
- Worker progress notes and schedule reasons: `select payload from task_events where task_id='<id>' and kind!='heartbeat' order by id desc limit 5`. Heartbeat rows only prove the process is alive.

## Watching a long remote job
- Check the artifacts, not the sentinel line in the log. A build wrapper can echo DONE after `make` failed. Grep the build log for `error` / `collect2` / `undefined reference`, and list the output `bin/` directory for the binary the next step needs.
- If you find a defect while the worker is waiting on a download, comment it on the card right away, so the fix happens inside the wait and not after it.
- If the host stops answering ssh and ping, report that to the user as a status problem: the scheduled card's download or job has probably stopped too.

## Changing direction mid-run

- When changing direction mid-run, put the correction in a card comment that says it
  overrides the body. It may not reach a running worker, but it is authoritative on requeue.
  When new evidence makes a sub-task redundant (e.g. the numbers it would produce turn out to
  be published already), cut it in that comment, lower the card's resource caps (pushes, GPU)
  in the same comment, and check the external side right away (e.g. `kernels status` on the
  slug the sub-task would have pushed) so you can tell the user whether anything was already spent.

## Retiring a card, rewriting a resumed card

- **Retire a card the moment its purpose is answered by something else**, e.g. a full-scale
  reproduction of a submission that has since scored on the hidden test. Comment why, `archive`
  it, and remove its release crons in the same pass. Otherwise it spends quota at the next reset.
- **When a pre-armed card is resumed after hours with a changed plan, rewrite its body** with
  `kanban edit <id> --title ... --body "$(cat <file>)"`. Put the revision on top with "this
  revision overrides the original below", and keep the original text under it for context. Then
  `assign <id> coder-bot` + `unblock`, and confirm a worker spawned. A comment alone may be read
  after the stale body has already steered the run.
