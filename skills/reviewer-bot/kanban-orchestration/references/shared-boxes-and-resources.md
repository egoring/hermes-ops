# Shared boxes, quotas, repos and RAM

Read when two cards could touch the same machine, quota, repo or RAM, when a card runs next to a live job, or when a box hangs or goes dark.

## Ownership lines for parallel cards

- **When you dispatch two cards at once that could touch the same machine or quota** (a local
  GPU box, the weekly remote GPU quota), write the ownership into each body: which card may use it,
  which may not, and a pre-start `pgrep`/`kernels status` check that must read idle. Parallel
  workers otherwise both start a bench or push on the same box, and each run's timing
  contaminates the other. Write remote process checks as `pgrep -f "src/[t]rain_v"`: a plain
  pattern inside an `ssh '...'` string matches the ssh command line itself, so the count is
  never 0 and a queue guard aborts on a phantom process. The same applies the other way round: a worker's smoke or test run whose command line matches a waiter's `pgrep` pattern (e.g. `train_b2o` inside `train_b2o_all_smoke`) keeps the waiter blocked. Give smoke runs a name outside every live waiter pattern, or tell the worker which patterns to avoid. A completion-wake cron that waits for "trainer count 0" keyed on the trainer script name never fires when the next queued run uses the same script, because a chained launcher starts it seconds later. Key such waits on the run's own `--out <dir>` string plus its log's `eval rc=` line.
  When two coder cards work in the same git repo at once, write `git add <own paths>` only (never `-A` or `.`) and name the other card's file glob as off-limits. Otherwise one card commits the other's half-built files. When the user asks "run it if it does not overlap with card X", check slug, inputs, machine and repo yourself, put the result into the body as these ownership lines, and dispatch in the same turn.
  When the user says one item is "already requested" somewhere you cannot see (another thread or bot), do not create it. Search every board (`kanban boards list`, then `list` per board), `kernels list --mine --sort-by dateRun`, `git log` and the notebooks dir for its slug or variable. Report what you found, including "nothing visible". Dispatch only the other items. Fence them off in the body: name the item as out of scope, forbid its slug, folder and name patterns, and wait if the remote platform concurrency is at 2. Then ask where it was requested, so its result can be wired into review and submit. If a later status check still finds no trace of it (no kernel, no card), say so in that report; when the user then says to take it over, re-run the same search and create it under the slug and phase number you had reserved for it, so names stay collision-free.
  RAM is a shared resource too. When two cards each plan a CPU memory test (a synthetic buffer-growth test, a smoke run) on a box whose RAM a training job already holds, they can together OOM-kill the training. Post a comment on both cards, overriding the body:
  - run one test at a time, with a `pgrep` check for the other card's test first
  - shrink the synthetic size to a few GB
  - do not start while `free -g` shows available below a floor (e.g. 6 GB)
  - afterwards, confirm the training log still advances
  Do not ask for `ulimit -v` around torch code. The virtual-address cap breaks `import torch` (ImportError) long before RSS gets near it. Use the size and available limits instead.

## WSL hard-hangs, disk floors, dark boxes

- **If a WSL box hard-hangs (ping and ssh both dead, then `uptime -s` shows a reboot), check the Windows host drive that holds `ext4.vhdx` before blaming co-running jobs.** `df -BG /mnt/c` is the number that matters. WSL's own `/` reports hundreds of GB free while the vhdx cannot grow on a full C:. The signature is `getpwnam(...) failed 5` (EIO) when `wsl` starts. Two hangs blamed on GPU training next to a tar-extracting cache build were C: at ~0 GB: both jobs were writing fast at that moment. Locate the vhdx with `ls -l /mnt/c/Users/*/AppData/Local/wsl/*/ext4.vhdx`. Its size ≈ WSL usage, so deleting inside WSL plus `fstrim` reclaims little. The space has to come from Windows or from deleting large WSL dirs.
  Guard disk with a low hard floor that stops work, not a high floor that refuses to start. This user set the rule: warn and stop at a floor he chooses (currently < 2 GB free); starting is fine while he frees space. Implement it as a no-agent cron every 10 min. It reads `df -BM /mnt/c` (MB, since `-BG` rounds up), `pkill -TERM`s the cache builder and trainers (skip-existing builders and `resume.pt` trainers make this safe), and @-tags once per episode, re-arming above ~15 GB. Put the same floor in the card body.
  **Every box-watching cron that exits silently on ssh failure hides an outage.** If all watchers "say nothing, try next tick", a box that went dark overnight is only noticed by the morning status board. Keep one watcher that counts consecutive ssh failures and emits once (through the quiet-hours hold) after ~30 min unreachable, and first thing on a status request ping the box before reading any chain log.
  After the box returns, do these in one batch:
  - Read `uptime -s`, `pgrep` the expected jobs, and look at the training dir's `resume.pt` mtime and the last log line.
  - Restart training from `resume.pt`. A trainer that saves only model, opt, sched and SWA state resumes fine, but the data order changes, so record that.
  - Delete leftover `.tmp` outputs and partial extract dirs.
  - `np.load` every cache file written before the crash. A reboot leaves truncated npz files ("No data left in file"), and a skip-existing builder would keep them. Rebuild the broken ones.
  - Until the cause is confirmed, write "no concurrent jobs on this box" into the card comment. Order the jobs by expected value: the member that can still move the score runs first, and near-zero-expected runs wait.
  - While the box is down, park the work card behind a gate card. A card blocked twice goes to `triage`, and the auto-decomposer splits it. Instead, archive the stuck card and create a continuation card (same spec, comments say where to resume) with `--parent <gate>`. The gate card is `blocked` with "waiting for box". A no-agent cron every 10 min ssh-probes the box. When the probe succeeds, it checks disk free, then `unblock` + `complete`s the gate and announces once through `emit()`. This is the one valid use of `--parent` to a blocked card: something will complete the gate.
  - Ask the user whether Windows itself froze or only WSL did, and to check Event Viewer (Kernel-Power 41 / WHEA).

## Co-running jobs on one box

- **"Why not run both at once on the box?" is answered with measurements, not caution.** Read GPU memory and utilisation (`/usr/lib/wsl/lib/nvidia-smi` on WSL, where `nvidia-smi` is not on PATH), `free -g` and load, and grep the chain launcher's kill logic to see whether it would touch a foreign job. Keep a reason only if it survives those numbers (unattended quiet-hours OOM risk, no second job ready yet, schedule slack). Offer a pre-registered 10-minute co-run smoke as the decider: combined throughput >= 1.3x a single run and available RAM >= 3 GB, else sequential. Say which earlier objection the reading disproved.

## Cards on a box with a live job

- **Cards that run on a box with a live job (training, a long download) must name every
  path the worker needs and forbid whole-filesystem scans** (`find / -name ...`). A worker
  that could not find a file ran such a scan for 13 min next to the download, which
  slowed the I/O and skewed the training-slowdown measurement the card existed for. Run
  helper commands under `nice -n 19 ionice -c3`. If a scan is spotted, comment on the card
  to stop it and say which measurement window it contaminated.
