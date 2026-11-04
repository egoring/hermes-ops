# Stall watchdog for approved mechanical handoffs

## Why
Completion notices (kanban done, background process exit, kernel COMPLETE) arrive between turns and are easy to miss. Steps that are already approved and purely mechanical then sit for hours. Examples: push a kernel after its card is done, submit after COMPLETE + gates, start the next GPU card. A prose rule ("sweep before every status reply") did not prevent repeated multi-hour stalls. A no-agent cron did.

## Pattern
1. **Chain with parents whenever the next step is just "start the next card".** `kanban create --parent A --parent B` makes the child start only when every parent is done. Each GPU card still checks that the GPU is idle before it starts.
2. **For approved non-card actions, write a marker file** in the same turn the user approves. Markers go in a pending dir such as `cache/<proj>_pending/*.json`. Types:
   - `push_when_done` {task, dirs, then}: when the task is done, push each kernel dir. Retry on the account GPU-session limit. Rewrite into submit markers, taking the version from the push log line `Kernel version N successfully pushed`.
   - `submit_when_complete` {kernel, version, message, tag, need[]}: when the kernel is COMPLETE, download its output and check all of the following, then submit once:
     - local schema check
     - in-kernel schema pass
     - every `need` string present in the log
     - no `P* FAIL`/Traceback in the log
     - no existing submission description already contains `tag`
     On ERROR/CANCEL or a gate fail, alert and do not submit.
   - `remind_when_done` {task, text}: @-alert once.
   Rename a marker on completion (`.submitted`, `.failed`, `.gatefail`) instead of deleting it, so the history stays.
3. **Alerts, quiet-hours aware** (hold overnight, flush in the morning):
   - a card blocked ≥ 20 min or in review ≥ 60 min, tracked by first-seen time per (task, status) in a state file;
   - newly scored submissions (learn the existing ones silently on the first run);
   - the GPU idle ≥ 60 min with no running GPU card;
   - a card mapped in a steps file (task → "④") reaching done, once.
   Pre-mark intentional long blocks (quota waits) as alerted so they do not spam.
4. Register it with `hermes cron create "every 10m" --name <proj>-stall-watch --no-agent --script <file> --interpreter <python> --deliver discord:<thread>:<thread>`. Run the script once by hand first to initialise its state.

## Limits
- Only user-approved actions go into markers. Judgment (what to try next, whether to adopt) stays with the reviewer; the watchdog only alerts.
- Bot-posted alerts may not wake the agent session. The user sees them and can ping.

Reference implementation: `~/.hermes/profiles/reviewer-bot/scripts/ntl_stall_watch.py`.
