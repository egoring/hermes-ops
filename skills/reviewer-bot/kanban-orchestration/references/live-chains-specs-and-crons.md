# Live PC chains, transform specs, submit guards, cron hygiene

Depth for reviewer cards that run long unattended chains on the training box, or that specify a data
transform. Always-on submit rules stay in SKILL.md. This file only adds what to do around them.

## Submit wrapper rollout
- When you introduce the locked submit wrapper, backfill its ledger with every earlier submit
  (slug@version and phase prefix).
- Then run it once on a known duplicate and expect REFUSE before you rely on it.
- A conditional submit cron must call the wrapper, never `platform-cli competitions submit` directly.
- **The wrapper writes its ledger line before `submit`, so a refused or unconfirmed submit leaves
  a line that blocks every retry as a "duplicate".** After a failed call, re-list submissions; if
  the prefix is absent, delete that ledger line before retrying (better: have the wrapper remove it
  itself when the post-submit listing does not show the ref). A cron that treats any REFUSE as
  final will silently mark the experiment done, so read the refusal text, not just the exit code.

## Writing a spec that touches a data transform
- **Grep the repo for an existing implementation of the same transform before you specify one**,
  e.g. `grep -rli "flip\|mirror" src/`. Cite it in the card as the reference. A from-scratch
  definition can miss what an earlier phase already worked out.
- **Apply a geometric augmentation consistently to every view of a multi-view input.**
  - For an L/R mirror of a knee or limb MRI study: W-flip the coronal and axial slots. For the
    sagittal slots, reverse the slice order (the channel order inside each window) and set
    pos → 1−pos where the slot exists.
  - Flipping only some views shows the model two different knees. A FAIL would then wrongly read
    as "flip augmentation does not help".
  - Anatomical labels (Medial/Lateral) do not change under a mirror.
- When a review finds that the defect is in your own spec:
  - Say so in the `request-changes` reason: "spec defect, coder implemented as specified".
  - Fix it before that arm trains, and record it as a pre-result amendment, not a post-hoc change.

## Changing a long PC chain while it runs
- **Never edit a running bash launcher.** bash reads the script incrementally, so an edit
  corrupts the live chain. Do not restart it, or drop a STOP file, for a small change either.
- Change behaviour only through files the chain re-reads at each step (the Python scripts it
  calls). To replace one:
  1. Copy it to the box as `<file>.tmp`, then `mv` it into place.
  2. Do this only while no process is using it (`pgrep` returns 0) and before the step that needs
     it starts (check that step's START marker in the chain log).
  3. Verify that the Mac and PC md5 match.
- **A new env or flag added to the primary run script must also go into every fallback launcher.**
  Chains often have a low-disk or crash-takeover twin (e.g. `start_full_ld.sh` started by a
  `chain<n>b` that waits on the primary's lock). If the twin lacks the new export, a takeover
  silently runs the old recipe under the new tag: a 3-epoch fine-tune becomes a 16-epoch
  from-scratch run, and the post-run gate then fails it. The takeover is likely exactly when the
  host disk sits near the primary's threshold. Verify by diffing the two launchers (only the
  threshold line and comments may differ), then compare both launchers' argv for every current
  and pre-written branch conf (n/n identical), including untouched default tags.
- **A successor chain started next to a primary and its fallback must wait on both locks**, one
  after the other, before its first run. Waiting on one lock lets it share the GPU with whichever
  chain holds the other. Give it its own lock, log, stage prefix and STOP file, and add its log to
  the post-run watcher's start-line sources.
- A value hard-coded in the running launcher (e.g. a disk threshold) stays as it is. Write a
  restart rule on the parked card instead: on that exact stop marker, check the condition, restart
  once with the launcher's skip env flag, and log a RESTART_* marker. The chain skips steps whose
  outputs already exist.
- Cancelling an arm before its result exists is a legitimate user decision. Have the next
  launcher stop it after the last needed marker, move its partial outputs to `_cancelled/`, and
  log it as "cancelled before result". Close the old card with the verdict the new chain produced.
- A parked card can show `blocked` because a reviewer run parks it on purpose. Before you report
  that to the user, read the last comment and run, and explain that it is a deliberate wait, not
  a failure.

## Restarting a chain after a crash or host reboot
- Establish what died and when before instructing: `journalctl --list-boots` on the box gives
  the previous boot's end time; the chain log's last marker and the run dir's newest files
  show which run was mid-way. Unreachable host (ping fails) means Windows-level power/sleep,
  not WSL; ask the user to bring it back.
- **Do not resume a seed run from a mid-training checkpoint unless the checkpoint stores RNG
  state.** Read the `torch.save({...})` keys first. If it holds only
  model/ema/opt/sched/step/epoch, resume re-seeds and replays epochs 0..k's sampler order,
  worker jitter and CUDA augmentation, which makes that seed a different experiment. Move the
  partial run to `_discarded/` (don't delete) and retrain that seed from scratch before any
  verdict uses it.
- Finished runs (metrics + judge outputs present) are safe to skip. Have the restart re-print
  already-made verdicts and compare them digit for digit.
- Instruction shape for the coder: verify 0 launchers/trainers → append a RESTART_* line to the
  log → restart with the exact documented command → list the expected skip/start lines →
  STOP+TERM and report on any deviation.
- Pause the card's release cron before any planned STOP/restart, and reset its `seen` line
  counter to the current log length before resuming it. Otherwise it sees launcher count 0 in
  the window and releases the card, or re-posts old markers.

## Slow epochs after a config change
A config that nearly fills VRAM (e.g. more slices per window) can run ~2x slower on a
Windows/WSL GPU (driver shared-memory fallback), independent of host uptime. Compare
`nvidia-smi` memory used vs total before blaming the host, and re-plan downstream deadlines
(5-fold step) from the measured s/epoch of that config.

## Cron hygiene
- When a conditional or one-shot cron has done its job (it submitted, released its card, or all
  its watched refs are scored), **remove it; do not just pause it**.
- Before removing, read each candidate's script or state file. Keep any cron that still has a
  pending item (e.g. a watch list with an unscored ref). Tell the user which ones you kept and why.
- When the user changes a guard threshold, update the cron and every in-code assert that enforces
  the same limit. A running launcher's copy gets the restart rule above.
