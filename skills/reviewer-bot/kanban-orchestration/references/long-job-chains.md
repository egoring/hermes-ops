# Long external jobs: pre-armed chains and stage-0 rehearsal

Depth for cards whose deliverable depends on hours-long training/kernels. The always-on rule (park a
card on a detached job instead of letting it ping-pong in review) stays in SKILL.md.

## Pre-arm the next stage behind the gate
When a gate result is hours away and the next stage is pre-registered, pre-arm the next stage behind the gate instead of waiting for the review cycle. This user wants the box never idle ("if nothing is running, train ahead; stop it if it fails"). Put a `nohup nice -n 19` chain launcher in a card that polls every 5 min and starts the next training only when all of these hold:
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

## Stage-0 rehearsal while weights are still training
While a push card waits for weights that are still training, rehearse everything except the weights now ("stage 0"). Build the kernel with a stand-in checkpoint of the same architecture and save format (e.g. the fold-0 model of the same trainer). Put it in every slot and use its real sha. Then check that no placeholder is left, that the cell md5s match the previous kernel except the intended cells, and that the full-path smoke passes on CPU (fork Pool → inference → reader csv shape → base restored), with `nice 19` and `CUDA_VISIBLE_DEVICES=""` so the training GPU is untouched. Have the worker leave the morning commands as one block: sha → Dataset → files check → rebuild → GPU smoke → pre-registration commit → push. A CPU run takes the CPU fallback path, so it cannot prove the fp16/CUDA path. Keep "GPU smoke with the real checkpoints passes, else no push" as a hard gate. Afterwards `schedule` the card again.
