# Pausing, sequencing, and deploy safety on Hermes kanban

## Pausing todo cards
- `hermes kanban block <id>` fails on a `todo` card ("cannot block"). To pause a todo card, use `hermes kanban --board <b> schedule <id> "<reason>" --ids <id2> ...`. To resume, use `unblock <id>`. A scheduled card returns to todo/ready and still waits for its parents.
- **To retire a `scheduled` card, use `archive`, not `complete`.** `complete` refuses a scheduled card ("unknown id or terminal state"), and `unblock` puts it in ready, where a dispatcher can claim it and run the very action you are cancelling (e.g. a GPU push). Comment the reason and the measurements you are keeping first, then `archive <id>`.
- When you unlink a parent, the CLI may say the child "was ready and is now todo". Run `ls` and `runs <child>` right away to confirm nothing claimed it in that short gap.

## Sequencing
- Chain cards (parent -> child) whenever two cards edit the same docs (OPS.md, WORKLOG.md) or the same module (e.g. aggregate.py), or both use the host CLI for measurement. Running them in parallel caused cross-commits and wrong baselines.
- Cards that work only in a separate folder (e.g. a blind data pack outside the repo) can run in parallel. Say so in a comment and keep the downstream measurement card dependent on both.
- A design card that creates its own implementation card may link it to the wrong parent. Re-check `parents` after every design card completes and relink.
- **Self-assigned design-record card:** create it `--initial-status blocked`, then `complete` it at once. Created `ready` and assigned to yourself, the dispatcher spawns a reviewer worker on it within seconds. Create the implementation card afterwards with `--parent <design id>`; the parent is already done, so the child is ready immediately. To complete a design card whose parent is still in `review`, `unlink <parent> <child>` first, because `complete` refuses on unsatisfied parents. Under time pressure, skip the design card and put the spec straight into the implementation card body.
  - If it was created `ready` and a worker already claimed it, `complete` is refused and a `--parent` child sits in `todo`. Do not `--force` or `reclaim`. Comment that the spec is final and the run should only `kanban_complete`.
  - That comment usually lands too late. The claimed design worker re-measures the data, writes its own refined spec and creates its **own** implementation card, so two implementation cards race on the same files. When the design run ends, list its `children` and the cards `created by reviewer-bot` in the last hour. Keep the one that has started and has artifacts; archive the unstarted one with a comment naming the survivor. Carry any scope only the archived card had (e.g. a dataset upload) into the next card in the chain, not into a comment on the running one.
- If a code card's baseline commit moves (another card changes the same module), the worker should stop and ask. Answer by re-baselining on HEAD (the deployed code), with an 'if the diff differs from the expectation, report before implementing' gate.

- **Conditional pre-approval ("결과 좋으면 바로 진행") on a card still being judged:** create the follow-up as a child of the judge card. Make step 0 of its body a numeric gate that combines every condition, e.g. judge PASS plus cumulative gain ≥ the submit threshold. Ask the judge card for the exact number the gate reads. If the verdict misses, comment the numbers and `archive` the child before it runs (`runs <child>` shows none). Costly side effects such as uploads stay behind step 0, and the final submit still needs its own explicit go.
- **Inserting a card into a serial GPU queue:** write the `link <new> <next>` line before the `unlink <prev> <next>` line, even in a quick one-liner. The slip is typing the unlink first out of habit. Then confirm `runs <next>` shows no run.

## Releasing a blocked launch card
- A launch card (GPU push, submit) created `blocked` behind a prep card is yours to release. Its conditions are usually two: the prep card is approved by the dispatched review, and the user has given his number or go (quota, approval). Once both hold, re-verify the prep artifacts in the same turn (shas, diff scope, tests, metadata). Post them as a comment, then `unblock`. The dispatcher does not do this for you: a prep card approved while nobody looked left a GPU launch idle for 1.5 h.
- **The user may approve the launch before the prep card is reviewed** ("GPU 바로 진행해줘" while prep is still running). Do not push an unreviewed kernel, and do not make him wait for a second ask either. Record the approval (time and quote) as a comment on the launch card. Then arm a no-agent cron (~10 min) whose script releases the gate itself:
  - read `hermes kanban --board <b> show <prep> --json` (the status sits under `task.status`) and stay silent until it is `done`. A prep card that was sent back for changes keeps the launch blocked until a later round is approved;
  - when it is done and the launch card is still `blocked`, post the approval comment, `unblock`, write a state file so later ticks do nothing, and print one line through the quiet-hours emitter;
  - expire after a fixed deadline with one message.
  Run it once by hand to confirm it reads both statuses and prints nothing, and remove the cron after it has fired.
- When you create such a pair, subscribe yourself to the PREP card with `--delivery-mode wake` in the same turn, so its approval wakes you instead of waiting for the user's next message.
- On every user status ping ("진행하고 있지?", "진행상황 알려줘"), check `runs` of the prep card and every blocked child before answering. If the gate is already open, release it before you reply, and own the delay in the reply if one happened. Also report anything an automation did since your last reply: an auto-submit, an auto-unblock, a finished final-check card. Each one needs its own line in the reply, because the user reads it as "it did not happen" otherwise.

## Review timing
- A chat-session comment posted after the review worker started is often missing from that round's verdict. Re-post it on the card as "round N+1 scope: also fix X" so the coder includes it and the next review checks it.

## Deploy safety
- `docker compose build` copies the working tree, including uncommitted edits. Keep code cards paused or finished during a rebuild. Check that `git status` is clean before building.
- Rollback prep: `docker tag <img>:latest <img>:pre-<date>` before building.
- Hot-reloaded prompt files (system.md) change production the moment they are written. Measurement cards must use a candidate file plus a diff. Apply it only at deploy time.
- A test may pin system.md's sha. After applying a prompt diff, expect that test to need a follow-up update.
- Ingest-time features (doc-date meta, aggregate files) only take effect when knowledge is re-ingested. Runtime features (L1 masking) take effect on restart. Say which is which in the deploy report.
