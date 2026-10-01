# Gateway resource usage (macOS launchd)

Use this when the user asks whether a topology change saved CPU or memory, or when an idle gateway seems to cost more than it should.

## Measure correctly

- **Find the right PIDs first.** The plist's first executable is the launchd job PID. The process that actually runs the gateway is a child of it: `pgrep -fl "gateway run --external-supervisor"`. Take the host PID from `gateway_state.json` → `pid`. Measure every process in the chain, not just the one `gateway status` reports.
- **Use CPU-time deltas, not lifetime `%CPU` or one `top` frame.**
  ```bash
  t0=$(ps -o time= -p $W); g0=$(ps -o time= -p $G)
  top -l 7 -s 10 -pid $W -pid $G -stats pid,cpu | grep -E "^($W|$G) "   # samples; the first frame is always 0.0
  echo "$t0 -> $(ps -o time= -p $W) | $g0 -> $(ps -o time= -p $G)"   # delta / 60s = real average
  ```
- **Do not divide cumulative CPU time by elapsed wall time.** Elapsed includes system sleep, when nothing runs, so the average comes out too low. Compare deltas between two measurements taken while the Mac is awake. Check sleep windows with `pmset -g log | grep -E "Sleep  |Wake  "`.
- **Take a before-number before changing topology.** Otherwise before-vs-after is an estimate. Say so if you did not take one.
- An idle Python gateway is about 200–250 MB RSS and about 0–0.5% CPU. Merging N gateways into one saves roughly (N−1) × RSS in memory. The CPU saving is negligible, because idle gateways only heartbeat.

## The osascript wrapper

`hermes_cli/gateway_launchd.py::launchd_program_arguments` wraps the launchd job in `/usr/bin/osascript` to give the gateway a macOS Local Network identity, so LAN connections are not refused with EHOSTUNREACH.

Two generations exist. Check which one the plist has: `plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/ai.hermes.gateway.plist`.

- **Old: `osascript -e 'do shell script "exec …"'`.** It polls for user-cancel the whole time the child lives, so it burns about 3–5% CPU while the gateway idles at about 0.3%. Suspect it whenever the job PID is `osascript` and its CPU-time delta exceeds the gateway's.
- **Current: `osascript -l JavaScript -e 'ObjC.import("stdlib"); … $.system(…)'` (JXA).** It measures 0.0% CPU. `hermes update` regenerates the plist with it.

**The fix for the old wrapper is `hermes update`**: see the update procedure in SKILL.md, then re-measure with a 60 s CPU-time delta. Check first whether the fix is in the installed build (`git merge-base --is-ancestor <fix-sha> HEAD` in `~/.hermes/hermes-agent`).

### Removing the wrapper by hand (only if updating is not possible)

Only do this when no profile needs LAN endpoints, such as a local LLM `base_url` or LAN platform hosts. Check first with `grep -n base_url ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml`.

1. Back up the plist: `cp ~/Library/LaunchAgents/ai.hermes.gateway.plist{,.bak_osascript_$(date +%Y%m%d_%H%M)}`.
2. Rewrite `ProgramArguments` to the inner command. Parse the `do shell script` string with `plistlib` + `shlex`, drop `exec`, and keep tokens up to the first `>>`. `StandardOutPath` and `StandardErrorPath` already route the logs. Then run `plutil -lint`.
3. Check for running kanban work, then get user approval. This reconnects every bot.
4. Run `launchctl bootout gui/$(id -u)/ai.hermes.gateway; sleep 8; launchctl bootstrap gui/$(id -u) <plist>`.
5. Verify:
   - each bot shows `✓ discord connected (profile: …)` in the log
   - `served_profiles` lists every profile
   - the dispatcher lock line appears
   - a new 60 s CPU-time delta shows the wrapper at 0

### Consequences to tell the user

- `hermes gateway status` keeps reporting the service definition as stale. That is expected here.
- **Do not run `hermes gateway start` to clear the stale warning.** It regenerates the plist and puts the wrapper back. So do `hermes update` and `gateway install`. Re-measure after each and re-apply if needed.
- LAN access from the gateway is blocked until the wrapper is restored from the backup.
- Record the change as a temporary workaround in the fleet design doc's known-issues table, and drop the hand edit once an update ships the fixed wrapper.

## Whole-machine battery / CPU triage

When the user says the battery drains fast, the gateway is rarely the cause. Rank by energy before touching fleet config:

```bash
pmset -g batt                                            # AC or battery right now
top -l 3 -s 10 -o power -n 12 -stats pid,command,cpu,power | awk '/^PID/{b++} b==3'   # last frame only
pmset -g custom                                          # per-source displaysleep / lowpowermode / powernap
pmset -g assertions | grep -E 'PreventUserIdle|NoIdleSleep'   # who blocks sleep
```

- A browser/app main process pegged at 100–200% while its renderers sit at 0% and it has run for days is hung, not busy. Recommend quit + relaunch.
- The Hermes desktop renderer + GPU process grow heavy with a very long conversation. Suggest ending the thread and starting a new one, or minimizing the window. Measuring from inside that chat inflates it further.
- Battery-only power settings need sudo. Hand the user the command; never type a password: `sudo pmset -b displaysleep 5 lowpowermode 1 powernap 0`.
- Quitting the user's apps: only when explicitly asked. Order: `osascript -e 'tell application "X" to quit'` → wait ~30 s → `kill -TERM <pid>` → wait ~20 s → `kill -KILL`. Tell the user a force-killed browser shows a restore-tabs prompt.
- Report as a before/after table of CPU-time deltas plus 1-min load average, and name what still dominates.
