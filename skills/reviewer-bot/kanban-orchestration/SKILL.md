---
name: kanban-orchestration
description: "Use when delegating work via Hermes kanban board."
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, multi-agent, delegation, review, verification]
---

# Kanban Orchestration (reviewer → coder)

For running work as an analysis/design profile that delegates implementation to a
coder profile via `hermes kanban`.

## Role boundary

**Never edit files yourself.** Not even a one-line revert or a cleanup `rm`. If a
file must change, that is a card for the coder profile — put the exact desired end
state in the card and let the worker do it. Touching files directly breaks the
separation the user relies on and makes the board history lie about who did what.

What you *may* run: read-only inspection (`diff`, `ls`, `grep`), and re-running the
worker's own verification scripts to check their numbers.

## Verify every self-report

Worker summaries are claims, not facts. Before relaying a result:

- **Recompute headline numbers from the raw artifact** (pkl/json the worker left
  behind), not from its prose. Sign flips and dropped rows show up here.
- **`diff` the files** against a known-good baseline to confirm the change is
  exactly what was claimed and nothing else rode along.
- **Confirm claimed deletions with `ls`.** A worker once reported "deleted X" when
  it had actually overwritten X with the original content — the file was still there.
- Check that a claimed "no-op default" really reproduces the baseline numbers exactly.
- **Read helper-bot text edits back before relaying them.** A Haiku helper transcribing Korean prose substituted look-alike words that reversed meaning ("contaminates" became "raises") and garbled others. For verbatim doc additions, `tail` the file and grep the load-bearing phrases; fix via a coder card with exact old→new string pairs.

Relay your own recomputed figures, and say explicitly when a worker's framing was
misleading even if its numbers were right (e.g. "no reaction" meaning "no win/loss
flips" while margins actually moved on 51/52 games).

**A background-process completion notice is not a new request.** When a job you already harvested
finishes, reply in 1–3 lines: which job it was, that its numbers are already in the last report
(or what changed if the final count differs), and what is still running. Do not re-report. The
same holds for a late "handed off for review" or "completed" notice about a card whose approval
you already relayed.

**A worker blocked by the security scan on a non-essential step (e.g. a bulk `rm -rf` cleanup)
should not hold the essential steps hostage.** If the blocked step is not needed for what follows
(enough free space already exists), comment "step deferred to the user; do not retry or bypass;
continue with steps X–Y and document the exact command", unblock, and give the user that command
in chat. Update any sibling card that was gated on the deferred step in the same pass.

## Writing cards

- **Design → implementation pair, in order.** Create the design card assigned to yourself with the
  spec body, `complete` it with a one-line result, then create the coder card with
  `--parent <design_id> --max-retries 4 --workspace "dir:<repo>"`, reusing the same body file. The
  body must end with the request-review loop and `--reviewer reviewer-bot` spelled out. Finish with
  `kanban show <coder_id>` and confirm it reads `ready`, `assignee: coder-bot`, `parents: <design_id>`.
- **Pre-verify the premise before assigning.** Confirm the data/files the card depends
  on actually exist and have the shape you assume. Cards built on a guess waste a run.
  For a component borrowed from someone else's code, the premise includes which branch
  actually runs with the mounted assets (manifest fields, Dataset version), not what
  its variable names suggest (recipe: the deadline-reader notes in the
  project-competition-lifecycle skill's public-notebooks reference). When the worker
  finds such a premise wrong, own it as a spec error in your review comment and approve
  the faithful execution.
  For a spec that reuses a label mapping on a new release of the same source ("only swap
  the column prefix", e.g. a later study visit), print each mapped column's distinct
  values in both releases before writing the card. A release can store a coarser value
  domain: integer grades with no 2.1/2.2 subgrades sent every grade 2 to the lower soft
  value, so the same lesion got 1.0 in one release and 0.6 in the other, and the
  experiment changed two variables at once. Put the fix in the card: a conditional mean
  computed in code from the finer release (asserted, not hard-coded), negative or
  unknown codes → NaN, and a check on the shared subjects that the soft means match and
  the binarised positive rate is unchanged. A shifted mean is a value-domain question
  before it is a cohort question; do not explain it by cohort or reader composition
  until both domains have been compared.
- **For a small, well-defined rule, run a throwaway feasibility probe in your own scratch first**
  (a wrapper around the live artifact, never a repo edit) and set the card's thresholds below the
  probe's result on a DIFFERENT seeded seed list, reporting zero intersection. The probe also
  catches constants taken from memory (domain constants were wrong until checked against the
  source module). Name the probe file in the card as the reference implementation, and forbid
  importing it from the deliverable.
- **Subscribe to the coder card with `--delivery-mode wake --notifier-profile <self>`** right after
  creating it, so its completion comes back to you for re-verification instead of being relayed raw.
- **Embed expected reproduction values** (exact means, per-seed deltas, counts) and say
  "if these don't reproduce, the implementation is wrong — stop and report". This turns
  a self-report into a checkable claim. Compute every embedded count with a real parser
  (`csv` module, `json`), never `wc -l` or `awk -F,`: quoted fields holding commas or newlines
  (e.g. a CLI `description` column) inflate line counts, and the worker then measures
  against your wrong number.
- **List already-rejected approaches by name** with a pointer to where they were rejected,
  so the worker doesn't re-propose them. Do the same search for your own design before
  writing it: grep the phase docs and data dirs for the same component (labeller, mapping,
  loss). A design that silently repeats a failed phase costs a full checker round, and the
  checker will flag it as 🔴.
- **A card that spends the user's paid API credit** (LLM labelling, hosted inference) gets a
  usage-based pilot gate with an extrapolated full-run cost cap, a cumulative cap checked before
  every batch, a pinned model id (stop if missing, never substitute), and a key-hygiene clause:
  the user stores the key in a 600 file himself; you check only mode, line count and prefix,
  never print it; the worker greps outputs and logs for the key prefix = 0 at the end.
  Recipe details: project-competition-lifecycle, plateau-levers reference, label section.
  Make the first API step a **single synchronous request with byte-identical params** (HTTP 200,
  `stop_reason` not `max_tokens`, the forced output block present, every field in-enum) before any
  batch. Params the API rejects fail every item of a batch: two 50-item pilots were lost this way,
  each costing a batch wait plus a review round (errored items are not billed). Let the worker drop a
  parameter the API names as unsupported/deprecated (max 2, documented and committed before any
  result) instead of blocking each time; repeated blocks send the card to triage. Known Anthropic
  quirks (10/2026): Opus 5.5 rejects `tool_choice` type `tool`/`any` (use `auto` + schema) and
  rejects `temperature`; a key not scoped to a workspace gets HTTP 400 without an
  `anthropic-workspace-id` header, so have the user create a workspace key with a spend cap.
- **Make "no improvement found" an explicitly valid outcome.** Without this, workers
  manufacture a recommendation. Add: do not loosen the acceptance bar to pass it.
- **Spell out every time, budget and timeout limit, and forbid the worker from adding its own.**
  A worker that adds a stricter "safety" cap can kill the very measurement the card exists
  for. The rework then costs a new push and a review round.
- **Separate hard gates from soft signals.** Hard = regression guards (nothing gets worse);
  soft = the improvement you hope for. When effect size is near the noise floor, gating on
  the improvement makes pass/fail a coin flip.
- **Tag every gate with the decision it controls** ("G0,G1,G3,G5 → upload A; G6–G8 → candidate B
  only"). A multi-gate card then cannot hold one artifact hostage to another artifact's slow or
  buggy gate, and a mid-run "can we ship now?" is answered by recomputing only that decision's
  gates.
- Demand `ls`/`diff` output as evidence in the completion summary for any file operation.
- **A card whose deliverable comes from a detached job (a `nohup` launcher on the GPU box that waits for its inputs and then trains) must not sit in `ready`/`review` while that job runs.** Each worker run finds no result yet and hands off "results pending", and every review of that hand-off returns it, so the card ping-pongs. Each lap spends a coder run and a reviewer run. Park it instead. The steps are below.
  1. Run `reopen-review <id> --reason "[dependency wait, not a rejection, 0/3] ..."` (this works only while the card is in `review`).
  2. Run `kanban schedule <id> "<which result file releases it>"`.
  3. Add a no-agent cron (every 15 min, one-shot flag file) that runs `unblock` when the result file appears, or when the launcher process count is 0 and there is no result file (the launcher died, so the coder must investigate). Route its message through quiet-hours `emit()`.
  4. A card that waits on another card's artifact (e.g. a kernel that needs a checkpoint still training) instead gets `link <producer> <card>`, and it becomes ready when the producer completes.
  5. When you return such a hand-off, label it "dependency wait, not counted" so the round counter stays honest.
  6. A stage handoff that starts the long job (request-changes "[stage handoff] start fold0") must be followed by your own `schedule` as soon as the worker's "started" comment lands. "Do not block" in the reason does not stop the worker from blocking at its terminal call, and that block plus the earlier ones sends the card to triage, where the auto-decomposer splits it.
- **When a gate result is hours away and the next stage is pre-registered, pre-arm the next stage behind the gate instead of waiting for the review cycle.** This user wants the box never idle ("if nothing is running, train ahead; stop it if it fails"). Put a `nohup nice -n 19` chain launcher in a card that polls every 5 min and starts the next training only when all of these hold:
  - the predecessor's launcher process count is 0
  - its report file exists
  - every input-fix marker (e.g. `cache_merge.done` plus the expected file count) is present
  - no GPU process is running
  It then parses the report's verdict line: `PASS` → run seeds in sequence; `FAIL` → write a `STOPPED_<reason>` file and exit; a missing or odd line → `STOPPED_REPORT_PARSE` and exit.
  When the user wants the box busy even before the verdict ("start it now, discard it if the result is bad"), train ahead: start the next fold and the gate script (CPU) at the same moment, check the verdict at every poll, and on `FAIL` TERM the speculative run, discard it, and start a pre-registered fallback arm with its own fold-0 gate (e.g. a 50/50 mix of the two label sources), stopping the queue only if that also fails. Fix the fallback's definition and gate in the pre-registration commit before fold 0 finishes, and have the chain append to the same launcher log with the same markers so the existing wake cron keeps working (update the cron's marker regex and process count for the new launcher in the same pass). A timeout on any input wait also stops it. Add a reviewer kill switch: a `STOP_<stage>` file that is checked before the start and at every epoch boundary, so a defect found while verifying the gate stops the run without killing processes by hand. Require the worker to test the parser on fake reports (PASS / FAIL / garbled) and to build the new mode as a separate trainer file, so the running job's source stays untouched. Kill switch and parse fallback are what make it safe to start before you have reviewed the gate.
  The launcher must be running **before** the gate fires, so the card's pre-launch checks have to fit in the time left. Do not require a full-path CPU smoke of a large model: a 384-px CoAtNet ran at 272 s/it on CPU (about 2 h for 25 batches), and the GPU sat idle for 1.5 h after the gate. Two options:
  - Cap the CPU smoke at a few batches, with a time limit derived from a measured CPU step time.
  - Make a short GPU smoke the launcher's own first step after the wait conditions, and abort with `STOPPED_SMOKE` if it fails.
  If the predecessor finishes before the launcher is up, switch the smoke to GPU in a comment right away (the GPU is free by then). Do not let the box wait for the original smoke plan.
- **While a push card waits for weights that are still training, rehearse everything except the weights now ("stage 0").** Build the kernel with a stand-in checkpoint of the same architecture and save format (e.g. the fold-0 model of the same trainer). Put it in every slot and use its real sha. Then check that no placeholder is left, that the cell md5s match the previous kernel except the intended cells, and that the full-path smoke passes on CPU (fork Pool → inference → reader csv shape → base restored), with `nice 19` and `CUDA_VISIBLE_DEVICES=""` so the training GPU is untouched. Have the worker leave the morning commands as one block: sha → Dataset → files check → rebuild → GPU smoke → pre-registration commit → push. A CPU run takes the CPU fallback path, so it cannot prove the fp16/CUDA path. Keep "GPU smoke with the real checkpoints passes, else no push" as a hard gate. Afterwards `schedule` the card again.
- **When new evidence breaks the premise of a pre-armed chain (auto-release cron → push → conditional submit), disarm it the same hour.** Example: a sibling kernel of the same design times out. Do these in one pass:
  1. Post a `HOLD — push 0, submit 0` comment on the card. It must say that the user's conditional submit instruction is suspended for this card, and why.
  2. Edit the release cron so it only alerts and no longer `assign`s or `unblock`s the card. Keep the backup.
  3. Remove the watch crons of finished stages.
  4. Tell the user which automatic step will no longer happen, and what decision re-arms it.
  Do not leave the cron armed "to fix in the morning". It fires on its own schedule and spends a push and a submit on a design known to fail.
- **A worker that hands off mid-wait ("1/2: built and pushed, kernel RUNNING") spawns a reviewer run that holds the card.** `schedule` is refused on a card in `review`. Do not park it from the chat. Instead, comment to that run: verify the build stage, do not `complete`, park the card for the external wait. Then make the release cron `assign <id> coder-bot` + `unblock` on the terminal kernel status. The resulting `blocked` notice is your own parking; answer it in one line. Better: in the body, tell the worker to request review only once the external job has finished.
- **A card you `schedule` from `review` keeps `assignee: reviewer-bot`.** A release cron that only runs `unblock` would then spawn a reviewer run instead of the implementer. Make the cron run `assign <id> coder-bot` before `unblock`, and confirm `show` reads the implementer after the release.
- **After a reviewer run completes a card, check the follow-up cards it created.** A review run can split off the unfinished part into a new card created `blocked` with an initial-status reason such as "waiting for the box to come back". Nothing will release it, even when the condition already holds. Run `kanban list` for new ids, `show` each one, and check its blocking condition yourself (e.g. ssh reachable, GPU free). If the condition already holds, `unblock` it with the measured facts, subscribe it with `wake`, and confirm that a worker spawned. The user's pre-approval (e.g. "train if PASS") carries over to that card, so say so in the reason.
- **A decision you make in chat about a card under review does not bind the reviewer run that already holds it.** That run can decide the opposite on its own and spawn a follow-up card for it, e.g. "copy the dataset" when the chat said "hold". Before you announce a hold or a close, `kanban show` the card for an active run. If one is active, post the decision as a comment that says "complete only; create no follow-up card". If a contradicting card already exists and has run, tell the user plainly that the two decisions conflict. Then re-weigh the original decision on its merits, because the artefact now exists. Ask the user to choose; do not silently delete or adopt it.
- **Do not let a review run's "this decision belongs to the user" re-open something the user already decided.** If the chat holds a conditional instruction that covers the outcome ("train if it passes, stop if not"), proceed under it, and say in the reply that it was pre-decided.
- **An input defect found in a job that is already training: decide restart vs. stage-and-merge by the direction of the bias.** If the defect can only understate the effect being tested (a small share of the extra data missing or partially empty), do not restart. Restarting costs the whole run (hours) and the gate stays conservative. Have the fix built into a separate staging dir under low CPU priority, never in the live input dir, and merged by a waiter after the job ends, so the next stage uses the fixed set. Record the decision and the bias direction on the card. Restart only when the defect could inflate the result or invalidate the comparison.
- **When you dispatch two cards at once that could touch the same machine or quota** (a local
  GPU box, the weekly remote GPU quota), write the ownership into each body: which card may use it,
  which may not, and a pre-start `pgrep`/`kernels status` check that must read idle. Parallel
  workers otherwise both start a bench or push on the same box, and each run's timing
  contaminates the other. Write remote process checks as `pgrep -f "src/[t]rain_v"`: a plain
  pattern inside an `ssh '...'` string matches the ssh command line itself, so the count is
  never 0 and a queue guard aborts on a phantom process. The same applies the other way round: a worker's smoke or test run whose command line matches a waiter's `pgrep` pattern (e.g. `train_b2o` inside `train_b2o_all_smoke`) keeps the waiter blocked. Give smoke runs a name outside every live waiter pattern, or tell the worker which patterns to avoid. A completion-wake cron that waits for "trainer count 0" keyed on the trainer script name never fires when the next queued run uses the same script, because a chained launcher starts it seconds later. Key such waits on the run's own `--out <dir>` string plus its log's `eval rc=` line. The same applies to a one-shot "is the run finished" cron that requires `pgrep -fc <trainer script> == 0`: when a chained launcher starts the next run on the same script within seconds, the count never reaches 0, so the cron never fires and the verdict waits for a human. Check `eval rc=` in that run's own launcher log alone, and use `pgrep -f -- "--out <dir>"` for the liveness test.
  When two coder cards work in the same git repo at once, write `git add <own paths>` only (never `-A` or `.`) and name the other card's file glob as off-limits. Otherwise one card commits the other's half-built files. When the user asks "run it if it does not overlap with card X", check slug, inputs, machine and repo yourself, put the result into the body as these ownership lines, and dispatch in the same turn.
  RAM is a shared resource too. When two cards each plan a CPU memory test (a synthetic buffer-growth test, a smoke run) on a box whose RAM a training job already holds, they can together OOM-kill the training. Post a comment on both cards, overriding the body:
  - run one test at a time, with a `pgrep` check for the other card's test first
  - shrink the synthetic size to a few GB
  - do not start while `free -g` shows available below a floor (e.g. 6 GB)
  - afterwards, confirm the training log still advances
  Do not ask for `ulimit -v` around torch code. The virtual-address cap breaks `import torch` (ImportError) long before RSS gets near it. Use the size and available limits instead.
- **If a WSL box hard-hangs (ping and ssh both dead, then `uptime -s` shows a reboot), check the Windows host drive that holds `ext4.vhdx` before blaming co-running jobs.** `df -BG /mnt/c` is the number that matters. WSL's own `/` reports hundreds of GB free while the vhdx cannot grow on a full C:. The signature is `getpwnam(...) failed 5` (EIO) when `wsl` starts. Two hangs blamed on GPU training next to a tar-extracting cache build were C: at ~0 GB: both jobs were writing fast at that moment. Locate the vhdx with `ls -l /mnt/c/Users/*/AppData/Local/wsl/*/ext4.vhdx`. Its size ≈ WSL usage, so deleting inside WSL plus `fstrim` reclaims little. The space has to come from Windows or from deleting large WSL dirs.
  Guard disk with a low hard floor that stops work, not a high floor that refuses to start. This user set the rule: warn and stop at < 5 GB free; starting is fine while he frees space. Implement it as a no-agent cron every 10 min. It reads `df /mnt/c`, `pkill -TERM`s the cache builder and trainers (skip-existing builders and `resume.pt` trainers make this safe), and @-tags once per episode, re-arming above ~15 GB. Put the same floor in the card body.
  After the box returns, do these in one batch:
  - Read `uptime -s`, `pgrep` the expected jobs, and look at the training dir's `resume.pt` mtime and the last log line.
  - Restart training from `resume.pt`. A trainer that saves only model, opt, sched and SWA state resumes fine, but the data order changes, so record that.
  - Delete leftover `.tmp` outputs and partial extract dirs.
  - `np.load` every cache file written before the crash. A reboot leaves truncated npz files ("No data left in file"), and a skip-existing builder would keep them. Rebuild the broken ones.
  - Until the cause is confirmed, write "no concurrent jobs on this box" into the card comment. Order the jobs by expected value: the member that can still move the score runs first, and near-zero-expected runs wait.
  - While the box is down, park the work card behind a gate card. A card blocked twice goes to `triage`, and the auto-decomposer splits it. Instead, archive the stuck card and create a continuation card (same spec, comments say where to resume) with `--parent <gate>`. The gate card is `blocked` with "waiting for box". A no-agent cron every 10 min ssh-probes the box. When the probe succeeds, it checks disk free, then `unblock` + `complete`s the gate and announces once through `emit()`. This is the one valid use of `--parent` to a blocked card: something will complete the gate.
  - Ask the user whether Windows itself froze or only WSL did, and to check Event Viewer (Kernel-Power 41 / WHEA).
- **"Why not run both at once on the box?" is answered with measurements, not caution.** Read GPU memory and utilisation (`/usr/lib/wsl/lib/nvidia-smi` on WSL, where `nvidia-smi` is not on PATH), `free -g` and load, and grep the chain launcher's kill logic to see whether it would touch a foreign job. Keep a reason only if it survives those numbers (unattended quiet-hours OOM risk, no second job ready yet, schedule slack). Offer a pre-registered 10-minute co-run smoke as the decider: combined throughput >= 1.3x a single run and available RAM >= 3 GB, else sequential. Say which earlier objection the reading disproved.
- **Before writing a regression gate, confirm that its input can legally exist on the machine that runs it.** "Rebuild 5 competition studies with the new builder and compare to the old cache" cannot run on a box where the project rules forbid raw competition data. Gate instead on the builder's source md5 matching the commit that built the old cache, a build-twice determinism check, and recorded library versions.
- **Cards that run on a box with a live job (training, a long download) must name every
  path the worker needs and forbid whole-filesystem scans** (`find / -name ...`). A worker
  that could not find a file ran such a scan for 13 min next to the download, which
  slowed the I/O and skewed the training-slowdown measurement the card existed for. Run
  helper commands under `nice -n 19 ionice -c3`. If a scan is spotted, comment on the card
  to stop it and say which measurement window it contaminated.
- **Quote pipeline durations from the previous run's artifacts, not from impression.** Before
  telling the user how long a design→build→gates→review cycle takes, list the prior card's output
  dir by mtime (`ls -lT -tr`) and split wall time into first build, rejection rounds, and the final
  gate run. A guessed "10-12h" was really ~1h of gates plus ~2.5h of rework — and the rework,
  not the verification, is what a reusable/generalised tool removes. For a generalisation card,
  make byte-identical reproduction of the old artifact (md5) plus the old gate numbers the
  completion criteria, and keep the original scripts untouched as the reference.
- When changing direction mid-run, put the correction in a card comment that says it
  overrides the body. It may not reach a running worker, but it is authoritative on requeue.
  When new evidence makes a sub-task redundant (e.g. the numbers it would produce turn out to
  be published already), cut it in that comment, lower the card's resource caps (pushes, GPU)
  in the same comment, and check the external side right away (e.g. `kernels status` on the
  slug the sub-task would have pushed) so you can tell the user whether anything was already spent.

## CLI pitfalls (these cost real time)

- **Free text is positional on every subcommand that takes it** — `comment <id> "text"`,
  `block <id> [reason...]`, `request-changes <id> <reason...>`, and the title on
  `create <title>`. `--body`, `--reason`, `--title` are all rejected. `--body`, `--assignee`,
  `--parent`, `--max-retries`, `--workspace` *are* real flags on `create`. When unsure, run
  `kanban <subcommand> --help` — it prints the positional/optional split in one line.
- **A card that pushes several versions of one remote job slug must download each version's output before the next push.** `<platform-cli> jobs output <slug>` returns only the latest version, so write "push vN → COMPLETE → download → only then push vN+1" into the card. If a worker skipped it, do not settle for a log excerpt: the version-aware SDK output call recovers the older version's files (details in the project-competition-lifecycle skill, mixing-kernel recipe).
- `kanban archive <id>` is the disposition for a card that should not be completed or blocked
  (see Review dispositions).
- **There is no `kanban stop`.** To retire a card whose run is still active, `kanban reclaim <id>`
  to release the worker claim, then `kanban archive <id>`.
- **To close a live card *with* a verdict** (the user ends a verification early and its partial
  results still count): post the verdict comment first, then `kanban reclaim <id>` and
  `kanban complete <id> --force --result "..."`. Plain `complete` is refused while a run holds
  the claim. Afterwards confirm the worker pid from the card's `spawned` event is gone
  (`ps -p <pid>`) and that `show` reads `done` — a reclaimed worker can keep writing files.
- **`hermes cron create` takes the schedule as the first positional argument**: `hermes cron create "every 15m" --name <n> --script <file in profile scripts/> --deliver discord:<thread_id> --no-agent [--repeat N]`. There is no `--schedule` flag. A one-shot watcher script keeps a flag file in the profile cache and exits silently once the flag exists, so the job can stay registered. Run the script once by hand right after creating it, and confirm it prints nothing and writes no flag while the condition is still false.
- **Cron housekeeping ("turn off what is not needed, slow the rest").** List every job with `hermes cron list`, then for each active watcher check its target before touching it: the kernel or submission it watches (`kernels status`, the competition's submissions list) and its state file in the profile cache. Pause only watchers whose targets are all terminal; a watcher with even one PENDING target (often another competition's submission) gets a longer interval instead (`hermes cron edit <id> --schedule "every 60m"`). Report paused vs lengthened with the reason per job.
  "Clean up the crons we don't use" means `hermes cron remove`, not pause: one-shot wakes whose card is closed, gates whose condition can no longer recur, and jobs already paused with a `Next run` weeks in the past. Map names to ids by reading the `hermes cron list` output to a file and grepping the id line above each `Name:` line, then list the survivors with one purpose each.
- **Every no-agent watcher script needs a hard time cap on in-process network calls.** `subprocess.run(..., timeout=)` covers CLI calls. An in-process client (e.g. `an in-process SDK client call`) has no timeout of its own: one hung call held the job until the cron's 3600 s script limit, and the score alert it existed for never went out. Wrap such calls in `signal.signal(SIGALRM, raise)` + `signal.alarm(120)`, with `alarm(0)` in `finally`, and let the next tick retry.
  To find this class of failure, read `hermes cron list` for `Last run ... error: Script timed out` on each active job, not only the job's output files.
  After the fix, run the script once by hand under an outer cap (`perl -e 'alarm 200; exec @ARGV' python3 script.py`, since macOS has no `timeout`). That run delivers any alert the hang swallowed and updates the state file, so report the delivered line in the reply.
- **A completion-watch cron for a remote job must fire only on an explicit terminal status.** Exit unless the status line contains `KernelWorkerStatus.COMPLETE` or `KernelWorkerStatus.ERROR`. An "exit if RUNNING/QUEUED" test treats a not-yet-pushed `-b` slug (404) as finished and unblocks the card too early. When a retry moves to a `-b` slug, repoint the watcher and reset its one-shot flag in the same step.
- **When `request-review --reviewer <self>` arrives, let the spawned reviewer run own the verdict.**
  Do not reclaim or close the card from the chat. Once that run holds the claim, closing
  it from the chat needs `reclaim` + `complete --force`. That reclaim triggers the board's anomaly
  monitor, which @-tags the user with a "lock expired, reclaimed" alert. It also leaves two
  approval comments on the card. In the chat, reply that the reviewer run has the card, check that
  only one worker holds it (`ps ... | grep "work kanban task <id>"`), and wait. When its
  completion wake arrives, re-derive its numbers from the raw artifacts and report them.
  When the user is waiting on the result (e.g. a cron must be registered from the verdict), you
  may verify in the chat right away and post the verdict as a comment headed
  "[chat review — round N: approve, no 🔴. The dispatched review run completes per this verdict]"
  with every recomputed number. Do not touch the claim; the reviewer run reads the comment and
  completes consistently, and its later completion notice needs only a one-line reply.
- **A "crashed (worker exited); dispatcher will retry" notice is not proof the worker died.**
  On every such notice, run `ps -axo pid,etime,command | grep "work kanban task"` right away.
  If the card now has two workers (old pid from the `crashed` event, new pid from the next
  `spawned` event), `kill -TERM` the older one. It can take about 20 s to exit, so re-check
  with `ps -p`; if it is still alive (e.g. inside a long `sleep` in a terminal tool call),
  `kill -KILL` it and its sleeping child. Kill its process tree, not just the pid: list
  children with `pgrep -P <pid>` (the terminal tool's `bash -c` wrapper and e.g. a running
  `<platform-cli> jobs output` download), because an orphaned child keeps writing into the same
  directory the new worker is about to use. Then check every other machine the card drives
  (`ssh <box> 'pgrep -af "platform-cli|train"'`): jobs the old worker started with
  `setsid nohup` survive its death and are progress, not debris — leave them running. Then
  comment on the card what you killed, what the dead worker already created externally
  (check the remote side yourself, e.g. `datasets list --mine`, `kernels status`), every
  detached job still running with its pid, log path and which items it covers ("s0→s1 being
  downloaded; fetch only s2·s3"), and "do not re-create/re-push/re-download; continue from
  step X". The usual cause is a single multi-minute `sleep` in the worker; write every wait
  in cards as `sleep` ≤ 60 s + `kanban heartbeat`. This applies to every
  profile's cards, including read-only final checks. A second notice for the same crash
  can arrive late; check the event log before treating it as new.
  Repeated false crashes exhaust `max-retries` and the card lands in `blocked` with a
  "gave up (retries exhausted)" notice, even though the last worker may still be alive.
  Your own `kill` of a duplicate worker is counted as one of those failures, so killing the
  newer duplicate on a card already at 2/3 tips it into `gave_up` while the older worker
  keeps working. If a live worker remains, do NOT `unblock` right away (that spawns another
  duplicate). Comment "run N is alive and continues; nothing to redo", and register a
  one-shot no-agent cron (every 5 min) that waits until that pid exits and then, only if the
  card is still `blocked`, runs `assign <id> coder-bot` + `unblock` with a "continue from the
  comments; re-run nothing; pgrep before each remote step" reason.
  If the dead-looking worker had already pushed a remote job (status QUEUED/RUNNING), comment "already pushed (push n/n used), do not re-push; poll status with sleep ≤ 60 + heartbeat" before killing the older pid. A respawned run re-reading the body otherwise spends the slug's only push again.
  If no worker is alive, handle it the same way as a crash (kill the live tree, inventory finished and detached work, comment
  "continue from step X; re-run nothing"), then `kanban unblock <id>` and confirm with `ps`
  that exactly one new worker spawned. Do not create a replacement card. For long multi-stage
  cards (cache build → download → bench), set `--max-retries 3` or more at creation.
  False crashes come in bursts: one dispatcher tick can mark every live card "crashed" at the same minute. On one notice, check all running cards' worker pairs in the same pass, not just the named one. When the dead-looking worker had started a detached job on a remote box (a `nohup xargs` integrity check, a download), tell the new worker by pid and log path to adopt it and not restart it, and to `ps`-check for duplicates before each step.
  Running `kanban dispatch` from the chat to kick a `ready` card spawns a worker under a different lock than the gateway dispatcher's. The gateway then marks it "crashed" and spawns a second worker on the same card. Do not dispatch by hand. If the card was unlinked or promoted, the gateway dispatcher picks it up within a minute. If you did dispatch, handle the next "crashed" notice as a duplicate: kill the older pid and tell the survivor to rebuild over any partial artifacts and to check the external side (`kernels list --mine`) before pushing.
- **A `crashed` event with `exit_kind: terminal_provider` / `exit_code 78` ("provider rejected this profile's credential") is a real stop, not a false crash.** The card goes straight to `blocked` (`gave_up` after one attempt), and every card of that profile that was running at that minute stops with it. It does not retry. When the user reports "the login dropped", do these steps:
  1. Read the card's log with `kanban log <id>`; it shows the HTTP 401 / revoked-token line.
  2. After the user re-authenticates, confirm the profile answers with `hermes -p <profile> chat -q "reply with just OK"` (`auth list` alone does not prove the token works).
  3. Inventory what the detached jobs finished meanwhile: training logs, result files, download loops.
  4. `unblock` each stopped card with a reason that states the cause, lists the finished results with their numbers, and says what must not be re-run.
  5. `unlink` any consumer card whose producer's compute is done but whose card is still open (e.g. docs pending), so the consumer starts now.
  6. Tell the user how many hours the outage cost and which ETAs moved.
- **A card blocked from `review` (e.g. the reviewer run blocked to get the user's push approval) returns to `review` on `unblock`, not to the implementer's queue.** Reassigning it to the coder first does not change that: the next run is spawned in review mode (`--skills sdlc-review`) under the coder profile. Such a run may still act on your approval comment (it executed the push here). So after unblocking, read the external side before touching the run: `kernels list --mine --sort-by dateRun` / `datasets list --mine` / the submissions list. **Never kill a worker you think is in the wrong mode until you have checked whether it already performed the irreversible step**; a kill after the push only triggers a `protocol_violation` respawn. Instead, comment "step X is already done at <time>, do not repeat it; continue from step Y". `reopen-review` is refused unless the card is in `review` at that moment.
  If the approval arrives while the card sits in `review` (not blocked), let the reviewer run route it back with `request-changes` headed `[stage handoff, not counted as a rejection, 0/3]`. Put the approved scope (PUSH_OK, push count, slug fallback, wait and verify steps, submit 0) into that reason. The next run is then a normal implementation run, and this worked cleanly. Do not `block` and `unblock` for the approval.
  If the reviewer run already blocked the card for the approval and exited, `request-changes` is refused ("not in an active review run"). This sequence worked, run with no worker alive in between (check `ps` first): post the PUSH_OK scope as a comment (write it to a file and pass `"$(cat file)"`, because backticks inside a double-quoted comment are executed by the shell and silently drop text) → `assign <id> coder-bot` → `unblock <id>` (lands in `review`) → `reopen-review <id>` (lands in `ready`, coder). Then confirm with `show` and the next `spawned` event that a normal implementation run started.
  To avoid this whole path, split any card whose later step needs the user's approval (a remote push or a submit) into two cards. The first card builds, does the local checks and ends with request-review; you approve it. Create the second card (`--parent <build card>`) only after the user approves the push. It does the push, waits for the run and verifies the output. Its run is then a normal implementation run, so the approval never travels through a blocked review card.
- **Answering a "lock expired / reclaimed" anomaly alert:** read the evidence log it names
  (`~/.hermes/kanban/incidents/<board>_<task>_<event>.log`). `"manual": true` with a `prev_pid`
  means a reclaim you ran yourself. Then confirm it had no side effects: the reclaimed run's last
  comments, that no external action happened (e.g. the competition submissions list holds no
  stray entry), the card status, and that the pid is gone. Tell the user what triggered it.

### Getting a long spec into a card

A multi-paragraph card body inlined as `--body "$(cat <<'EOF' ... EOF)"` can be refused by the
shell guard, which cannot prove the executable body of a large heredoc and blocks the whole
command. Do not fight it by shortening the spec. Two working paths, in order:

1. Write the body to a file with the `write_file` tool (not a shell heredoc), then
   `kanban create "<title>" --assignee X --body-file <path> --json`. `--body-file` is a real flag and
   avoids shell substitution entirely; `--body "$(cat <path>)"` is the fallback.
2. If that is still refused, create with a one-line stub body (`"스펙은 첫 코멘트 참조"` /
   "spec in first comment") and post the full spec as the first `kanban comment`. The worker
   reads comments, so nothing is lost.

**Give every body file a unique, descriptive name** (`/tmp/kb_<ver>_<purpose>.md`), never a short
generic one (`/tmp/kb_sub.md`). Generic paths get reused across sessions, and a stale file a later
step never overwrote has shipped a completely unrelated spec into three separate cards here — once
silently, because the card was archived before the worker ran. Before `create`, `grep -c` the
defining keyword of the intended topic against the file, and grep the keyword of the *wrong* topic
expecting 0; run that grep through the terminal, not through the same helper that just wrote it.

Always `kanban show <id>` afterwards to confirm the body or comment actually landed — a failed
`cat` inside the substitution yields an empty body and the CLI rejects it with a bare
"comment body is required". `show` echoes the opening body lines, which is the cheapest way to
catch a contaminated body before the worker starts.
- **A comment that fails with `'utf-8' codec can't encode characters ... surrogates not allowed`
  posted nothing.** Re-post it with the emoji written as words ("red 0 / yellow 2") and no
  `$(...)` substitutions inside the text, then confirm with "Comment added". Never assume the
  first attempt landed: the card record is what the next worker and the final check read.
- `--board` is a top-level flag, so put it BEFORE the subcommand: `hermes kanban --board <slug> create ...`
  (also `comment`, `show`, `unblock`, `notify-subscribe`). Placed after `create` it is rejected. Alternatives:
  `--project <slug>` on `create`, or `kanban boards switch <slug>`. Always also pass
  `--workspace "dir:<abs path>"` to pin the working dir;
  otherwise switch with `kanban boards switch <slug>`.
- **Never announce a card id you did not see in tool output.** Run `create ... --json` in its own
  terminal call and print the parsed id on a line by itself. When `create` is chained with crons,
  comments and `notify-subscribe` in one call, the result can come back collapsed to a one-line
  summary, and the id never reaches you. Recover it with `kanban list | grep "<title keyword>"`
  and confirm with `show` before putting it in the reply or in a routing line.
- `create` prints no id in its default output — pass `--json` and parse the id out,
  or you cannot subscribe to the card you just made. The id sits at the top of the JSON, so
  piping through `tail` drops it; if it is lost, recover it with
  `kanban list | grep "<unique title keyword>" | awk '{print $2}'`.
- There is no `kanban subscribe`; it is `notify-subscribe`. `--chat` is **ambiguous**
  (`--chat-id` vs `--chat-type`) and `--platform` is required, so the working form is
  `notify-subscribe <id> --platform discord --chat-id N --thread-id N`.
- **Never `--parent` a new card to a card that is (or will stay) `blocked`** unless a cron or a person will complete that card (the box-down gate pattern above). A child waits in `todo` with `dependency_wait parent_not_done` until the parent completes, so hanging a follow-up (e.g. a diagnosis card) off a deliberately blocked card strands it forever. Use `--parent` only for real "start after X finishes" ordering; for context, name the related card in the body. If it already happened: `kanban unlink <parent> <child>` and confirm `show` reads `ready`.
- **Repeated blocks trip a circuit breaker** (`failure_limit`, default 2) and route the
  card to `triage`. Raise `--max-retries` on cards you expect to iterate on.
  From `triage` an auto-decomposer can split the card into new child cards and make them
  its parents. The children are claimed and spawned at once. They redo steps the card
  already finished, such as a Dataset re-upload or a kernel push, so they can spend
  quota or FROZEN push slots. Handle it right away, before any other action on the card. Children are claimed within
 seconds, and archiving or unblocking the original card does not stop children that
 are already running:
 1. Run `kanban show <card>` and read `parents:`. Then `kanban show` each child and look
     for `created by auto-decomposer`.
  2. Make sure the external side effects did not happen, by checking
     `datasets list --mine` and `kernels list --mine`.
  3. `kanban block` the running children with a reason that says they duplicate the parent.
  4. Kill their worker pids (`ps aux | grep "work kanban task <child>"`), then
     `kanban archive` all of the children.
  5. Run `kanban unlink <child> <card>` for each child. The original card then re-enters
     `todo` → `running` with its comments intact, and your last comment steers it.
  `unblock` and `promote` are refused on a card in `todo` or `running`, so you do not need
  them here. Expect one completion or block notice per child afterwards. Answer each in
  one line: it was a duplicate that you archived.
- **Leaving a card in `triage` is not a safe park: the auto-decomposer can still split it minutes later.** It created three child cards (one `ready` and one `todo` that would redo a remote push and a PC training run) and re-parented the card to them. Do not park in triage. Clean up as above (block/kill/unlink/archive the children; `block` is refused on `todo` children, archive works), then `kanban schedule <id> "<what it waits for>"` once the card is back in `ready`, and confirm `show` reads `scheduled` and any worker spawned during the gap has exited.
- **Your own blocks count toward that limit.** Blocking a card to redirect the worker can
  strand it in triage even though the worker never failed. Prefer a comment + reclaim.
  Parking a card for an external wait (quota reset, a kernel still running) by block → handoff →
  block also trips it. Use `schedule` for long waits.
  A card in `triage` refuses `block`, `schedule` and `promote` from the CLI. `assign <id> coder-bot`
  first takes it out of triage, and after that `block` is accepted, so a parked wait can be set up
  the normal way (block + a release cron that runs `assign` then `unblock`). Without the assign the
  dispatcher does not run it, so it is effectively parked, and a release cron must not try to move
  it: make the cron alert-only and resume the work by hand on the card or on a revised card.
- **Retire a card the moment its purpose is answered by something else**, e.g. a full-scale
  reproduction of a submission that has since scored on the hidden test. Comment why, `archive`
  it, and remove its release crons in the same pass. Otherwise it spends quota at the next reset.
- **When a pre-armed card is resumed after hours with a changed plan, rewrite its body** with
  `kanban edit <id> --title ... --body "$(cat <file>)"`. Put the revision on top with "this
  revision overrides the original below", and keep the original text under it for context. Then
  `assign <id> coder-bot` + `unblock`, and confirm a worker spawned. A comment alone may be read
  after the stale body has already steered the run.
- An unblock→block cycle also trips "unblock loop detected".
- **A worker's capability block** (e.g. a missing local tool, or an install the sandbox
  refuses) is answered on the same card. Post a comment that overrides the body and reroutes
  the blocked step, for example to a kernel the card already plans to run. Keep the push and
  GPU caps unchanged. Then run `kanban unblock <id>` and confirm that `show` reads `ready`.
  Do not create a replacement card. Do not tell the worker to bypass a security scan.
  A legitimate fix to what the scan flagged is allowed. Example: a raw-IP upload is blocked, so you add an ssh config
  alias. When a blocked step needs approval that only the user can give, and the user has already
  approved it in chat, you may run that one step yourself. Examples are a file transfer or a
  token copy. Verify it by hash, then say on the card exactly what you did. Do not edit files in
  the repo.
- **Protected files (AGENTS.md and similar) need interactive write approval.** A headless worker
  times out waiting for it, and so would a helper card. Do not put such an edit in a card at all.
  Give the user the exact old line and the exact new lines in chat, and he edits the file
  himself. He prefers this to clicking through an approval. Then `git diff` the file to confirm
  only the intended hunk changed, and let the next card commit it untouched. If a review card was
  blocked only on that edit and its reviewer run has exited, close it yourself: a verdict comment,
  then `unblock` (it returns to `review`), then `complete --result`. Plain `complete` works
  because no run holds the claim.

## Final-check handoff (independent-model checker)

Only when the user asks for a final check. In the card body:
- Pin the artifacts by hash (md5 of each kernel/script file) and the git HEAD. If another live
  card edits the same builder or source tree, name it, and say that a hash mismatch at check
  time is itself a defect.
- List the pass criteria numbered, taken from the project rules and the spec. List what you
  already verified and, separately, what you did not verify, so the checker re-derives the
  first and digs into the second.
- End with the report format: per criterion met/unmet/unverified with numbers, severity per
  defect, risks in resource units. Say the checker does not decide.
**While a final check runs, keep the independent work moving.** This user asks "what does not
need the check result?" right after dispatching one. Answer (or pre-empt it in the dispatch reply)
with two lists: items no pass criterion of the check can change — read-only analyses, assets every
branch needs (e.g. an offline wheel Dataset), facts only the user can read (quota screen) — and
items that wait on a named criterion. Offer one coder card for the first list (no GPU box, no
submit, no decisions inside it), and forward any fact the user supplies meanwhile to the running
check card as a comment.

**"Wouldn't a final check say the same?" about a plan or strategy:** when the checker model
authored the plan (a second-opinion or design card), re-checking it with the same model is not
independent. Say so, list which of its numbers you recomputed yourself and which parts nobody
can verify before results exist (subjective probabilities, approximations), and recommend
putting the final check at the first artifact that will be submitted, where there is code,
runtime and output to re-derive. Offer it now anyway if the user says the word.
When the user says "final check, then submit" in one message, the submit is pre-authorised
conditionally: write into the card body that the orchestrator submits if the report has 🔴 0
and asks again otherwise. When the report returns with 🔴 0, re-hash the kernel file against
the pinned md5, confirm the kernel status is COMPLETE, submit once, and report the check
summary and the submission id together.
The same holds for "submit if the review passes" on an implementation card: post a comment on
the card recording the user's conditional decision and the exact submit procedure (gates:
COMPLETE, gate lines in the log, remote md5 = local, UTC-day count; the exact `submit -k ... -v`
command and message; add the ref to the score watcher; "on request-changes, do not submit"),
because the dispatched reviewer run of your own profile, not the chat, will hold the verdict.
Keep "worker submits 0" in the body so the coder never submits.
**"Submit right away when fold 0 is good" on a member the submission kernel loads as K folds.** A fold-0 checkpoint swapped into a K-fold slot changes two variables (the data change and the fold count), so its LB result cannot be read. Explain that fold 0 is a gate, not a submittable artifact. Record the pre-approval on the card as conditional gates: fold-0 gate passed (reviewer-recomputed), all K folds trained, kernel diff = weights only, push COMPLETE, then one mix submit plus one standalone measurement submit. Give the ETA of the earliest real submit.

**"Decide yourself until morning"**
- Write the branch table to a plan file in scratch, with a running "decision log" section. Append one line per autonomous decision as it happens, so the morning report is a read of that file.
- Also list what stays out of scope: submits beyond pre-approved ones, deletions, threshold changes, starting a follow-up the user has not seen.

**"Decide yourself until morning; ask fable if something needs discussing"** delegates the pending go/no-go calls, not submits.
- Before the result exists, pre-register a branch table for each pending result, e.g. control ≥ baseline → start arm X and build probe Y; slightly below → start X only; far below the monitor value → suspect the eval path and investigate.
- Post the table on the gated card and on the plan card, then execute it without further asking.
- Anything the table does not cover goes to a fable-bot opinion card first (independent recomputation, no decision). Then you decide and proceed.
- Submits still wait for the explicit word. the remote platform pushes the user pre-approved in chat ("push right away") go into that card's body with the push count and the `-b` fallback.
- Report every autonomous decision in the morning with its pre-registered rule.
- **"If something gets submitted overnight, check what is next and go"** → make the follow-up mechanical before any score exists:
  - Write a decision-table file in scratch: events E1..En keyed on each pending submission's score band, each with exactly one action. An action is either a single-variable card (push 1 → submit 1) or "record only". Add a submit priority for when the UTC-day cap binds, and the rule "anything not in the table → report in the morning, no new experiment".
  - Prefix every overnight submit message with a phase tag (`p59 `, `p56s `, ...).
  - Add a no-agent cron (every 10 min) that reads the submissions csv. When a ref with a known prefix first shows a score or an error, it creates one reviewer-bot card whose body is that score plus the table. A state file keeps that to one card per ref.
  - The card applies the table, checks the board for an existing card with the same purpose, and @-tags nobody in quiet hours.
  - Do not let a score that changes two variables at once trigger an action. Example: a relabelled member's standalone score must not justify a blend-weight change; record it only.
  - When an overnight result makes an off-table action attractive (e.g. that standalone score jumped), the table still says "record only"; pitch the action to the user in the morning as a new single-variable card with its own baseline (the newest blend submit), and once approved, drop its phase prefix from the trigger cron so a second card is not auto-created.
  - A false "crashed" notice on a card that already pushed is answered with the existing crash rule (comment "already pushed, do not re-push" first). Write every kernel wait in overnight cards as `sleep` <= 60 + heartbeat, with no single tool call over 5 min.
- **When you queue a new chain behind running work, re-check every release cron that waits on the same box in the same turn.** A cron created an hour earlier whose predicate was "trainer process count 0" stops working once the new chain starts that trainer seconds after the old one ends. The gated card then waits for the whole new chain. Re-key the predicate on the old run's own tag/`--out` string, and comment on the gated card that the box's GPU is now someone else's (CPU only, `nice 19`, `CUDA_VISIBLE_DEVICES=""`, RAM floor).
- **A card that launches its own detached chain may end its first run with one deliberate block** ("chain waiting, no input needed", pid + log path). Register the release cron in the same turn. The cron emits each verdict or marker line once, and when the launcher count is 0 and the last line is terminal, it runs `assign <id> coder-bot` + `unblock`. The `blocked` notice that follows is expected: confirm the chain pid and the pre-registration commit time, and reply in a few lines.
- **Pitch an option to the user only when its trade-off is really balanced.** If the downside clearly dominates, decide it yourself and mention it in one line: it departs from the pre-registered config, adds variance that blurs the readout, or spends a submit and GPU hours for an early peek. This user said to skip such options without asking. Ask only about choices whose value depends on his priorities.
- **When the user says "act now" while an opinion card is still open, do not wait for it.** Decide from the numbers you have recomputed, and post the decision on the gated card as an override comment. In that comment, put PUSH_OK behind that card's local gates (P1). Then comment on the opinion card that the decision is made, and ask it to report any 🔴 as a comment right away. Watch the opinion card until the push. If a 🔴 arrives first, post a stop comment on the gated card; if no stop comment exists, the worker proceeds. When the opinion lands after the push, reconcile it: adopt its 🟡 as a pre-result amendment (e.g. the verdict bands) before the score exists, and correct any of its "missing" findings that the timeline already resolved.

"Submit it if the verdict looks OK" on an experiment whose results do not exist yet (overnight) is handled the same way, but needs a design card first. Its body holds:
- A mechanical selection rule that the results cannot bend: which run is picked, with a pre-named default when nothing is adopted, and "no pick, no submit" when a required seed run is missing.
- Numbered submit gates: queue finished cleanly, bug floors, kernel COMPLETE with weights md5, parity, a time-limit check, a remote = local diff limited to the selection constant, and a free UTC-day slot.

Record the user's words on the card as a user decision. In the reply, say which the remote platform GPU pushes you take the instruction to include, so the user can withdraw it.
When the user says "final check, then proceed" without the word submit, chain it overnight but
keep submission for the morning ("proceed" is not a submit instruction):
1. Create the implementation card (judge → build → push, no submit), then `kanban schedule <id>
   "<what it waits for>"` so it cannot start before its input exists (e.g. a training queue still
   running).
2. Create the final-check card with `--parent <impl_id>`; it sits in `todo` and the dispatcher
   starts it when the parent completes. Its body must cover both parent outcomes: gates failed
   with push 0 → a short re-derivation report only; pushed → the full check against the hash
   table the parent was told to put in its doc.
3. A cron checks the precondition by reading the last status line of the remote log plus a
   process count, and only then runs `kanban unblock <impl_id>`; otherwise it does nothing. When
   the input-ready time is known, a one-shot at that time is enough. When it is uncertain (a
   multi-variant queue whose last stage has no measured speed), use a recurring cron (e.g. every
   30 min) whose first step is "if the card is no longer `scheduled`, print nothing and exit", so
   it stays silent and cannot double-release. Subscribe both cards with `wake`. If the user asks
   for status and the precondition is already met, unblock it yourself right away instead of
   waiting for the next tick, and say so.
4. In the reply, say plainly that nothing will be submitted and which word the morning needs.

When the user says "final check first, then proceed" about a **design** (before any code exists),
check the design itself, not an artifact:
1. Create the design card for yourself with the full spec body and `complete` it at once (result =
   one line: "draft fixed, waiting for final check").
2. Create the checker card with `--parent <design_id>`, `--max-retries 3`, subscribed with `wake`.
   Its body pins the spec file and the hashes of the files the spec promises not to touch, lists
   what you already measured (so the checker re-derives it), numbers the pass criteria
   (single-variable, gate thresholds vs the existing per-fold distribution, selection rule free of
   the hold-out, regression testability, train **and** submission-runtime budget, queue predicate
   safety), and adds opinion questions that state your stance as a claim to rebut.
3. Do not create the coder card yet. On 🔴 0, create it from the same spec with `--parent
   <design_id>`; on any 🔴, revise the spec first. Running jobs on the shared box continue; the
   checker body makes the box read-only.
   When a second design shares the training code or cache with a design whose check is still
   open, do not open a second checker card. Create the new design card, `complete` it, and post
   on the open checker card a comment naming the spec path, the review points as numbered
   items, and "report the two designs' 🔴/🟡/🟢 separately". A shared trainer then gets one
   check, and the two verdicts stay apart.
4. Adopt the checker's 🟡 that change a threshold, a test procedure or a branch rule before the
   coder card exists, not in review: write them as a numbered "amendments — this section overrides
   the sections above" block (each with the evidence you re-derived from the checker's output),
   append it plus the request-review loop to the spec file, and create the coder card from the
   concatenated file. Post the same list as a comment on the design card. Threshold changes made
   here are still pre-result, so they keep the pre-registration valid; keep the original wording
   in the doc next to the new value. Items needing a user decision (e.g. spending the remote platform GPU on a
   side measurement) stay out of the card and go to the user.

When the report returns, read the full run summary from the board DB (the `result` field can
be a one-line stub). The checker's structured report (criteria, defects, opinion, unverified)
is usually the `metadata` argument of its own `kanban_complete` tool call: read it read-only
from the checker profile's `state.db` (`select tool_calls from messages where tool_calls like
'%<task_id>%' and tool_calls like '%kanban_complete%' order by id desc limit 1`, then parse
the JSON arguments). If neither that, `task_runs.summary` nor `task_comments` carries the defect list
(the summary may only count "🔴 0, 🟡 1, 🟢 2"), read the checker's own last assistant message
from its profile's `state.db` (`select content from messages where role='assistant' and content
like '%🟡%' and content like '%<artifact keyword>%' order by id desc limit 1`). Do not report a
🟡 you have not read as "to be checked later". Re-verify each 🟡 yourself against the code, and
say which ones you will handle operationally. Give an advisory recommendation that names its trade-off, and @-tag the
user for the decision.

**"Final check, and ask fable's opinion too" is one card with two halves.** Keep the numbered
pass criteria, then add numbered opinion questions, each stating your current recommendation
as a claim to confirm or rebut with numbers, the candidate options to rank, and "end with one
line: checker's advisory pick = X, reason = Y". When the checker disagrees and backs it with
external evidence (a public bundle, a scored notebook), open that evidence yourself before
relaying; if it holds, say in the reply which of your earlier recommendations was wrong and
adopt the corrected one as yours, rather than presenting two competing opinions.

### Second-opinion card ("ask the other model what it thinks")
When the user asks for the checker model's opinion on direction (not a final check), give it
the same assignee but an opinion-shaped body. Put no time cap and no "keep it short" in it:
this user wants depth over speed for strategy cards. Instead, name the raw artifacts it must
recompute from: our OOF and hold-out prediction files (inter-member Spearman, per-label
weak spots), the scored notebooks' blend cells, the borrowed bundle manifests. Allow long
reports split over several comments. The body holds the situation with every number and its file,
**your current stance as numbered claims it must confirm or rebut**, the concrete questions
(next-step design with numeric criteria, why a past approach failed, ranked paths with cost,
defects you missed), and "no code, no cards, no submit, does not decide". If a long job is
running on a shared box, make the box read-only for it (read files only; start/stop nothing).
**"Is there anything more we can do with X?" (a resource the user has decided to keep, e.g. an
external dataset).** Shape the body so the answer is a ranked, priced list rather than a debate:
- Open with the user's fixed premise ("we keep using X; host ruling Y") so the checker does not
  re-litigate it.
- State the current use of X with measured numbers, including any null LB result and the label
  or member weak spots, plus the hard constraints: freeze date, which box is busy until when,
  quota, the submission kernel's remaining runtime headroom, and the data-handling rules.
- Give candidate directions as examples "not limited to" (other releases or visits, unused
  label fields, self-supervised pretraining, a different backbone for decorrelation,
  pseudo-labelling, auxiliary targets). Require for each: expected ΔA and ΔLB with the
  reasoning, expected correlation with the current base, box GPU hours, quota hours, download
  size and time, added inference seconds in the submission kernel, feasibility before the
  freeze, failure risk, and rule conflicts.
- Ask why the measured effect of X vanished in the blend and what would have to change for it to
  survive (answered from principles, never by tuning on the LB or the small hold-out).
- Ask which in-progress runs on X should be stopped, then for a ranked top 1–3.

When it returns:
- Read the full report from the comment it names (`task_comments` in the board DB), not the
  one-line result. Recompute its headline numbers from the raw files.
- If it computed results before a criterion was fixed, any criterion set afterwards is post
  hoc; keep the pre-existing project threshold.
- Agreement between two models is not evidence. Test its load-bearing claims ("X is not worth
  it", "break-even needs score Y") against external data such as public notebooks before
  adopting them, and say which ones failed.
  **When the user forwards the checker's proposal and asks "shall we do this?", answer it piece by piece.**
  - Adopt the parts your own measurements already support: target resets, cancelling a retrain, GPU order.
  - Test the load-bearing premise against a with/without pair you already hold before you agree to a new card. Example: a per-label gain the proposal assumes.
  - If the premise fails, do not reject the proposal outright. Convert it into a pre-registered condition on the card already in flight ("proceed only if ≥ 2 of these labels gain ≥ +0.02 at fold 0"). Post that condition as a comment on that card.
  - Ask the user only about the leftover optional items, each with its cost.
  - Implement "go ahead only if it does not touch running resources" as ownership lines in the new card: no box GPU or RAM, quota only, push cap.
  A causal explanation for a failure ("the stage cost
  was underestimated 3×") counts as a load-bearing claim: relay it to the user as a hypothesis
  plus the measurement that would test it, never as the cause. Acting on an untested cause
  pointed the next design at trimming compute when the measurement later showed compute fit.
- While the card is still open, forward new evidence to it as a comment rather than waiting
  for its report. Examples: a score that just landed, or a memo the user shared. Give the
  file path, list the claims, and mark which ones you have already refuted with numbers.
  Ask the checker to confirm or rebut each one in its report. A report written without that
  evidence must be redone; a comment costs nothing.
- **Run `kanban show <id>` before forwarding.** If the card already reads `done`, nobody will
  read the comment. Reconcile the report yourself instead: read it, mark which of its
  conclusions the new evidence confirms or changes, and post a correction comment for the
  record. Any statement of yours that the report proved wrong (e.g. a fact about our own
  code) gets an explicit "[reviewer correction]". Then tell the user which points of the
  report still hold.

### Design delegated to the checker model ("let fable design the next step")
The checker still writes no code and creates no cards; its deliverable is a design document.
- Body: the situation with every number and file, the open question (e.g. a collapsed run to
  diagnose), the design template it must fill (one-line summary, evidence, single-variable
  variant table with tag/out path/time, run order within the overnight budget, pre-fixed numeric
  gates with a multi-comparison margin, "no passer is valid", contamination note, honest pass
  probability), and "post the design as card comments, then complete; the box is read-only".
- Create it with `--parent <judging card>` so it starts only after the results it must react to
  exist, and write both result branches into the body (something passed / nothing passed).
- When the judging card returns, add a comment to the design card with any pattern you saw in
  the results, framed as "confirm or rebut", not as a conclusion.
- On return, review the design like any spec, then turn it into the coder card yourself;
  execution still waits for the user.
- When the user approves ("do both"), write a design-final card for yourself with
  `--parent <design card>`: cite the design's comment ids, list the claims you accept, the
  claims you correct with your evidence (e.g. a public score it called unverified that you
  read on the page), and any scope cut (e.g. "judge only, no blend kernel this phase").
  `complete` it, hang every coder card off it, and chain any final check with
  `--parent <impl card>`. Write the machine/quota ownership into each parallel body, and
  delete the previous phase's one-shot release cron once its card has started.

## "Is anything running?" / "can we continue where we left off?" / "can we ship before it finishes?"

Answer from the machine and the board, not from memory. Run one batch:

1. `ps aux | grep -iE "python|bench|eval"`: the worker's actual script, its CPU% and start time.
2. `hermes kanban list | grep -viE "done|archived"`, then `kanban show <id>` on each live card for
   the round number and the latest review summary.
3. `ls -lat <card output dir> | head` and the tail of its run log: what was rewritten and when.
   An empty log next to a busy process means the process is still running, not that it hung.

Report per card: what finished, what is running and for how long, and the headline counts
(e.g. how many games passed the fidelity check). Flag counts that look like a spec defect
rather than a worker defect.

**"How can I see what is running from Discord?"** Offer a no-agent status-board cron at fixed hours (e.g. 9/12/15/18/21 local, through quiet-hours `emit()`). It prints one screen:
- box up/down, host-disk free, running job names, and the progress line of the live run
- RUNNING/QUEUED kernels
- best score and PENDING submission refs
- live cards with a status icon and assignee
Long-dead blocked cards are skipped. Pair it with the box-down gate cron, so an outage is reported within minutes instead of through a worker's report. `/kanban --board <b> ls` in the thread is the instant, card-only alternative.

**"Summarise everything so far into an md and upload it"** means a file attached in the chat
(`MEDIA:<abs path>`), not a the remote platform or git upload. Refresh the live facts in one batch first
(submissions list with status and score, every live card's status and last events, `git log`,
remote job progress), because a result often lands while you write. If one did, put it at
the top of both the file and the reply. File sections, in order: header (time, competition,
deadlines, current best, [measured]/[estimated] legend) → submissions table → completed work
by phase with key numbers → in progress with ETAs → decisions needed, each with options and an
advisory pick → ops state (quota, box, active crons, cards) → risks and unverified items →
file locations. Write it in scratch, not in the repo. In chat, give only the new result and the
decisions list, plus the `MEDIA:` line.

**A card can close without you noticing.** Small cards (a figure script, a doc edit) finish within
minutes. When the user cancels or changes their mind right after you dispatch, `kanban show` before
replying: if the card is already done, say so, list the artifacts it left (and that nothing was
published), and offer removal as a separate cleanup instead of claiming it was stopped.
A `request-review --reviewer <self>` spawns a separate
reviewer run of your own profile that may approve and complete the card on its own
(a chat-side `complete` then fails with "unknown id or terminal state": post your check as a
comment instead). Before
telling the user a card is "still running" or summarising a build, `kanban show <id>` and read
the run list and last events; if a reviewer run already completed it, re-read the result files it
cited (hash the artifact, open the summary JSONs) and report that verdict as confirmed-by-you.

**"Is there anything left to do?"** First sweep for loose ends: runs whose result files exist but whose card was never judged. A wake cron keyed on a process pattern can miss them. Judge each one from its raw files against its pre-registered gate, then `complete` it. Remove the watch crons of finished phases in the same pass (`hermes cron remove <id>`). Only then list the remaining options as a table: expected Δ, cost, verdict. Say plainly when no experiment is worth starting, and name the cheap standing work instead: daily public-notebook watch, and the final-slot selection.

**"Did we miss anything?" / "review everything"** — run this checklist in one batch and report each line as fixed / OK / needs a decision:
- Work-log doc: `grep -n "^## Phase"` against every card closed since the last sweep. A phase judged in chat or by a reviewer run often has no section (project rule C4). Hand the missing sections to helper-bot with "copy the numbers from the card's last reviewer comment, no recomputation", path-only commit.
- Board: `kanban ls` minus done/archived. Archive long-blocked cards that later phases superseded, with a one-line comment saying which.
- Crons: every job's target terminal? Remove finished-phase one-shots and jobs paused for a week or more. Keep any watcher with a PENDING target, including another competition's submission.
- Our uploads: confirm each private Dataset is really private with an anonymous request (`curl -s -o /dev/null -w "%{http_code}" https://www.platform-cli.com/api/v1/datasets/view/<owner>/<slug>`: 403 = private). Run a known public Dataset alongside it as the 200 control.
- External-data ruling: re-read the host post in the browser and quote the condition we meet, plus any unanswered objection.
- Final slots: whether the user has selected them, and what auto-selection would do on a displayed-score tie.
- In a code competition, a scored submission is fixed: its hidden-test run is already done. Public weights changing later cannot affect it, so do not list a "final-day sha check" for scored submissions. That check applies only to a new submit.
End with the numbered decisions for the user, and @-tag outside quiet hours.

For a resume check, add two things to that batch: `kanban show` on every **blocked** card (its
last comment records why it stopped and what the re-issue plan was), and the output directory of
the most recently closed card. Collected-but-unjudged data is the usual loose end — a collection
card closes "done" while the comparison it fed was never made — so say explicitly which numbers are
raw and not yet a verdict. End with one recommended next step and why (prefer the one that feeds a
pending decision and has no external blocker), then ask.

If the user proposes shipping before the card closes, do not answer "wait for review"
reflexively. Look up which pre-declared gates control *that* artifact. Recompute each one from the
raw results file yourself: completion status, max step time, win counts under the declared
seat-dedupe rule, and per-opponent regression. Hash the file you are handing over against the
copy that was measured. If those gates pass, recommend shipping now, with the post-ship criteria
and the control slot that must stay. The still-running gates keep deciding only the artifacts
they were declared for.
The same applies to "is there anything to submit?" while a push card is still writing docs: the
remote job often finishes long before the card closes. Run `kernels status <slug>` and read the
downloaded log's gate lines (ERRORS, WEIGHTS md5, PARITY, G, EST_SEC) yourself. Then give the user
two labelled options, "final check, then submit" (recommended if the agreed condition said so) or
"submit now", and say which exact words trigger each.

## Notification routing

`kanban notify-subscribe <id> --platform ... --chat-id ... --delivery-mode <mode>`

- `notify` / `notify+wake` post the **worker's raw summary** into the chat.
- `wake` wakes you only — you read the board and report in your own voice. Use this when
  the user wants the reviewer, not the worker, speaking.
- Set `--notifier-profile` to your own profile so delivery is owned by you.
- **Subscribe the chat the user is in now, not the one an earlier card used.** Each new
  Discord thread has its own id. If you copy the chat/thread id from a previous card's
  subscription, the wake goes to an old thread the user has left. Take the id from the
  current session's source. When unsure, subscribe both, and pass `--chat-type thread`.
  `kanban show --json` does not list subscriptions. Read them with
  `sqlite3 -readonly ~/.hermes/kanban/boards/<board>/kanban.db "select * from kanban_notify_subs where task_id='<id>'"`.

## Check the card itself before acting on it

A card can be defective independently of the worker. Run these checks when a card completes or
blocks, before you approve, relay, or act on its output:

- **Does the title match the body?** A card titled for one build can carry a body specifying an
  entirely unrelated one. The worker will faithfully build the body, so the deliverable is not
  what the title promised. Read both, and when they disagree treat the body as what was built
  and the title as the bug. Put "if the title and body contradict, do not reinterpret — block"
  in cards you write.
- **Is the deliverable already on disk from an earlier card?** Hash it. A re-issued card can
  reproduce a byte-identical artifact under a new name, leaving the same bytes carrying two
  version numbers — a lasting citation hazard. Compare `sha256` against the existing candidates
  before treating the output as new information, and recommend collapsing to one name.
- **Is the premise still current?** A card written days earlier can reference a baseline the line
  has since moved past. Evidence gathered against a superseded baseline has never passed the
  project's own acceptance gate, however clean the card's execution was.

## Review dispositions: approve execution, correct the premise separately

When a worker executed the spec faithfully but the *spec's* numbers or premise were wrong, do not
reject the card — rejection asks the worker to fix something it did not author, and a second
block can trip the circuit breaker. Instead:

- **Approve/leave completed**, and post a comment that states the correction with your own
  recomputed figures and labels itself as superseding the card's quoted numbers. The board then
  carries both the honest execution record and the corrected conclusion.
- **Archive** a card whose body was defective at birth (wrong subject, stale candidate). Say in
  the comment that it is not the worker's fault and name what was wrong with the body. Leave the
  artifacts on disk; they usually have record value even when unusable.
- Reserve `changes_requested` for things the worker can actually fix: factual errors in its own
  document, missed spec items, unverified claims.
- **State the scope boundary in the rejection: what passed, and what must NOT be re-run.** A
  worker facing a rejection defaults to redoing everything, so a request to fix a derived table can
  cost a full re-measurement. List the parts you independently verified ("fidelity gate, the
  N-game matrix, the runtime checks — all confirmed, do not re-run") alongside the numbered fixes,
  and say plainly whether re-measurement is needed. Scoped this way a rework lands in minutes
  instead of rerunning the expensive step.
- **When a long job is already running from the card's code, fence the rework off from it.** A
  rejection on a doc mismatch can make the worker "fix" the source or re-run smoke tests on the
  box that is training. Add to the follow-up comment: no process may be started, stopped or
  restarted on that machine; the running script's source file must not be edited (the commit
  must keep matching the running code); the only allowed check is a read-only `pgrep -fc`. Then
  verify yourself that the job's start time did not change.
- **Number the required changes and give each one the evidence that it is wrong.** Quoting your own
  recomputed figure next to the worker's makes the fix checkable rather than a matter of authority,
  and the worker can verify it landed without another round trip.
- **Record an override the moment the user picks an option below a pre-set criterion** (e.g.
  "proceed" when one gate missed by a hair): a `사용자 결정(override): <criterion, number, choice>`
  comment on the card the next step hangs from, plus the same line in the next card's doc step.
  Left for later, the final check flags it as a defect.
- **Do not @-tag inside the user's quiet hours** (see memory), even when a decision is pending.
  Check the clock before writing the tag; say "for the morning" instead and let the cron flush.
  When the user lifts quiet hours for one night only ("OK to alert until 1 am tonight"), keep the window itself as it is. `is_quiet()` already honours an `OVERRIDE_UNTIL` file (epoch; ignored once past or unreadable) in the quiet-hold dir, so write the epoch of the stated end time there and confirm with `python3 -c "import quiet_hours as q; print(q.is_quiet())"` from the scripts dir. Note that held alert files from old jobs will flush on the next tick.
  To actually use such a window, add a one-night no-agent watcher cron (every 15 min, `--repeat` bounded) that keeps a small state JSON and emits once per event: long-job milestones (e.g. every 2 epochs with the monitor metric labelled as monitor-only), job finished (with the raw final log lines + tag), download done, and a stall alert after 2 unchanged ticks. Route it through `emit()` so anything after the override expires is held for the morning, and tell the user which expected events will likely land after the cutoff.

After you have issued a terminal review action, your obligations to that card are discharged even
if the harness keeps asking for one. Do not `complete` a card you just rejected (that is
rubber-stamping the work you objected to) and do not `block` one that has no real blocker (that
kills the worker's in-flight fix and burns a retry). Say so in a comment and move on.

**A status notification can be your own action echoed back.** A `changes_requested` you just issued
arrives worded as "review requested changes (BLOCK); implementation is not approved — decide the
next step", which reads like fresh work. Before acting, `kanban show <id>` and check the event log
and run list: if the latest `changes_requested` carries your own reviewer name and a new worker run
is already claimed against the card, the loop is healthy and the correct action is **none** —
confirm status/assignee routed back to the implementer and stop. Creating a follow-up card here
duplicates work the worker is mid-way through fixing.

## Statistical hygiene for benchmark work

- **Re-run the headline measurement yourself on inputs the card never touched.** Recomputing from
  the worker's raw artifact only proves its arithmetic; it cannot catch a biased input set. The
  strongest findings of several sessions came from drawing fresh inputs and getting a materially
  different number — approve the execution, then correct the conclusion.
- **Never accept an evenly-spaced parameter sweep as the evidence base.** Strided seeds/IDs
  select a correlated slice of the space and inflated a win rate three separate times here
  (90% -> 67%, 96% -> 73%). Require inputs drawn with a seeded RNG, pin the list in the card, and
  make the worker report a zero intersection with previously used values.
- **Calibrate every CI gate against a null pair before putting it in a card.** Recompute the gate on two runs that differ only by seed (same config): if that pair already fails it, the gate cannot pass for any real comparison. A "ΔG CI lower bound > −0.010" gate on a 58-study gold set failed for a seed-only pair (CI [−0.018, +0.011]), so it was a coin-flip gate; judge single-fold A/Bs on the low-variance metric and keep the small set as a report-only guard.
- **The same applies to "behaves identically" gates on GPU code** (e.g. "feature ON vs OFF, loss |Δ| ≤ 1e-3"). fp16/cuDNN runs are not bit-reproducible: two identical-config smoke runs differed by 0.002–0.028 in epoch-1 loss, so the worker burned runs chasing a gate it could never meet. To prove a side-effect-free addition (checkpoint save, logging), gate on a deterministic check instead: assert the RNG states (python/numpy/torch/cuda) are byte-identical immediately before and after the new code, plus identical loss up to the point the new code first runs. Report the ON/OFF loss gap only as a reference number. If such a gate is already in a running card and the worker is looping, correct it in a comment at once and own it as a spec error.
  The same holds for "output sha equal to the previous run" gates on a multi-GPU inference kernel after any change to scheduling (chunking, worker count): write the gate as rank equivalence plus a metric Δ bound, and keep byte equality only for stages the change does not touch. A worker that follows a byte gate literally stops a push that was fine.
- **Set a new model's adoption gate from the strongest existing comparable member on the same metric and label source, not from the baseline the plan names.** A gate of "baseline + τ" that sits below a member we already have (0.8781 vs an existing 0.8792) passes a model that adds nothing. List every member's value before writing the threshold. In the same spec, fix the checkpoint-averaging epochs in advance (e.g. the last three) instead of "top-k epochs by OOF", because choosing epochs on the evaluation fold biases the gate it is judged by and the all-data run has no fold to choose on.
- **Calibrate per-fold auto-stop gates against the same fold's baseline, never a single absolute value.** CV folds differ in difficulty: a "stop the queue if A_fold < 0.85" gate, set from fold0 (0.870) minus a margin, halted an overnight 4-fold queue on the hardest fold (ViT baseline there 0.812 vs 0.836–0.839 elsewhere) although the new model's gain on it (+0.034) matched the other folds (+0.031, +0.033). Gate on Δ vs the baseline's same fold (e.g. Δ ≥ 0, or ≥ half the fold0 gain), and when an absolute gate does fire, check that Δ before treating it as a failure.
- **Several experiments that each need trainer changes → one experimental trainer copy with default-off flags, not one edit per experiment.**
  - Leave the frozen trainer (the one shipped in the kernel) untouched. Copy it once and add flags for every planned experiment.
  - The default path must be bit-identical to the original: no new RNG calls on it, and the original loss line kept as it is.
  - Prove it once on CPU before queueing: step-loss and EMA max|Δ| = 0.0, same thread count for both runs, `nice 19` on a box whose GPU queue is busy. Add a grep showing that every added RNG call sits inside a flag branch, because a CPU test cannot see CUDA RNG.
  - One checker round then covers all experiments, and every later run is argument-only.
  - Things to spell out in the spec, since checkers caught each of them:
    - **Masked or weighted losses:** write `(w*bce).sum() / w.sum().clamp_min(eps)`, plus a unit test on an all-masked batch. A graph-detached 0 crashes `backward()`, and an all-masked batch is likely over a few epochs, which kills the queue.
    - **Judge scripts:** copy helper functions instead of importing them from another record script. Scripts with module-level argparse and no `__main__` guard run their whole report, and exit, on import.
    - **New queue's kill and wait patterns:** they must match the new trainer's path. Patterns copied from the old queue miss it, which silently disables stall and EP0 guards.
    - **Flag plumbing:** trace every new flag to the function that consumes it through every call path, e.g. an aug flag stored as a model attribute so `forward()` passes it on and the EMA deepcopy inherits it. A flag parsed but never reaching the transform makes the arm a silent copy of the baseline.
    - **Fine-tune continuation arms** (init from a baseline ckpt): give both arms the same new seed. Re-using the baseline's seed replays the baseline's first-epoch shuffle and windows.
    - **Augmentation ranges:** state them in image-side units. `affine_grid` translation lives in [−1, 1] coordinates, so t = 0.20 shifts by ±5% of the side, not ±10%.
    - **Weighted samplers with replacement:** compute the expected unique-study fraction and the per-label positive exposure per epoch before fixing the weight (w 3 left 41% of draws as duplicates; w 2 was gentler). Re-derive the rare-label set from the actual train-fold prevalences, because a round threshold can exclude the very label the arm was meant for.
    - **Auxiliary metric for a loss-mask arm** (e.g. AUC on explicit cells only): print each label's cell count next to it. A label with ~100 cells adds its own bootstrap SD to the mean and inflates τ, so pre-register the full mean as the gate and the mean without that label as report-only.
- **Pair an uninterpretable single-variable arm with its control in the same queue.** A bigger batch at a fixed lr cannot tell "batch does not help" apart from "lr was not rescaled", so run it next to the lr-scaled twin. A fine-tune continuation that adds a loss mask needs a same-steps, no-mask continuation, so that "trained longer" is separated from the mask itself. Do not chain a new queue by editing the running queue script, because bash reads scripts incrementally. Copy it and add `^bash analysis/run_<prev>.sh` = 0 to its wait predicate.
- **Design a multi-arm fold-0 screening queue so every arm differs from the baseline in exactly one variable.**
  - Fix the micro-batch for all arms up front (the smallest that fits the heaviest arm, e.g. bs2×accum4) and forbid per-run OOM fallback. A fallback that fires only on the high-resolution arm silently changes batch size too, which voids that arm's verdict.
  - Use the mean of 3 seed reps of the baseline as the reference, not one run. With 4 arms judged against a single baseline run, the family false-adoption rate is ~15–35% at τ = 0.003. Set τ = max(floor, 2.6σ_seed) against the 3-rep mean (≈3.2σ against a single run).
  - Put the seed reps first in the queue, so σ exists before any arm finishes, and put the longest, lowest-prior arm (e.g. 2× epochs) last, behind an elapsed-time skip.
  - Before claiming a pipeline lacks a feature (augmentation, flips), grep that pipeline's own code. A wrong "X has no augmentation" premise reshapes the whole screen.
- **Do not let an unvalidated proxy gate a go/no-go.** An OOF metric computed against one label source is not comparable across models trained on different label sources, so "OOF does not track LB" from such a table is confounded, not shown. Until a same-label-source OOF→LB link is measured, use the proxy only as a bug floor and decide on the LB readout.
- **Anchor pass probabilities on our own base rate before external testimony.** Count how many of our own comparable submissions cleared the bar (k/n, Laplace (k+1)/(n+2)). External "we got 0.95 with X" claims may move it, but they cannot replace it. In one case 0/5 own singles ≥ the bar gave ~14%, while testimony alone had suggested 35–45%.
- **A watcher that parses an append-only log must judge by the last status line.** After a manual restart the old `QUEUE_STOPPED` line is still in the log; a substring search keeps reporting "stopped" and blocks the release forever.
- **A chained queue's start predicate must not match the predecessor's own wait lines.** A waiting queue logs lines like "WAIT for run_16a ALL_DONE ...", so a downstream `grep -qE "ALL_DONE|QUEUE_STOPPED" <upstream log>` is true from the first minute. Only the "no training process" condition then holds the downstream queue back, and it races the upstream queue at its end or in the few-second gap between folds. Exclude the wait lines (`grep -vF " WAIT for " log | grep -qE ...`) or anchor the marker. In the card, require the predicate to be tested on four copies of the log: the current one (false), with `ALL_DONE` appended (true), with `QUEUE_STOPPED ...` appended (true), and 100 wait lines only (false). When reviewing, run the script's own function on those copies (`eval "$(grep '^fn ()' script.sh)"`) and do not trust "it is waiting, so it works".
- **Check whether the sample can even detect the effect** before acting on a verdict.
  A result can flip sign across sample sizes (n=5 negative, n=20 positive, n=50 negative)
  when the between-sample sd is ~15% of the mean and the effect is ~0.5%.
- Report paired bootstrap CIs; if the CI includes 0, say the result is not established
  no matter how good the point estimate looks.
- **Pool every distinct measurement before judging, deduping repeats.** Per-card win rates from
  different input blocks can disagree wildly while the pooled estimate is stable and modest; the
  pooled number with its CI is the one to report and to set the next card's bar from.
- **Set an implementation card's completion threshold from the lower bound of the pooled CI**,
  not from the best point estimate, and write "do not lower this bar to pass it" into the card.
- In chaos-sensitive simulations, a "win" by a margin far below the known perturbation
  scale is noise, not an improvement — name it as such.
- Measure the metric the user is actually scored on. Optimising mean score when ranking
  is win/loss based means large margins on already-won games are worth nothing. Corollary: when
  the win-rate CI excludes the break-even point but the mean-margin CI includes 0, the result
  still counts — say which criterion decides so the worker does not reject on the wrong one.
- Before proposing to merge two workstreams, confirm they share a code path. Two
  "improvements" can live in entirely separate agents, in which case one contributes zero
  to the scored artifact.
