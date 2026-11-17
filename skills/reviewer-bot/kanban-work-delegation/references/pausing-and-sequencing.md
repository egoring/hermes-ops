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

## 5b. Pause and resume on the user's word

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
