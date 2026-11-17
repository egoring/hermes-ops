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
