# Scheduled alerts without token cost

## Use no_agent cron for anything a script can decide

A cron job with `no_agent=true` plus `script` runs the script on schedule and delivers its
stdout verbatim — no LLM call, zero tokens. Reserve agent-backed jobs for work that genuinely
needs reasoning. Resource alerts, usage reports and health checks are script work.

```
cronjob_manage(action='create', name='...', schedule='0 9,21 * * *',
               script='resource_alert.py', no_agent=True, deliver='local')
```

Scripts resolve under `~/.hermes/scripts/`. `.sh`/`.bash` run via bash, anything else via Python.

**Empty stdout sends nothing.** That is the watchdog pattern: the script stays silent when there
is nothing to report, so a daily job does not train the user to ignore it. Non-zero exit or a
timeout does raise an error notice.

When the job posts to a chat platform itself (its own HTTP call), keep `deliver='local'` so the
scheduler does not also echo the stdout into a channel.

## Edge-triggered, not level-triggered

Alerting every run while a threshold stays breached is noise the user tunes out. Persist the
last state and alert only on transitions:

- newly over threshold → warn (with mention)
- still over → send nothing
- recovered → optional quiet notice, no mention
- breached again after recovery → warn again

Keep the state in a small JSON file beside the script, keyed by check name. Verify the
transition logic by running the script three times with a deliberately low threshold, then the
real one — assert warn / silence / recovery in that order. Reading the code is not verification.

## Standard fleet automation set

Three zero-token jobs worth proposing once a fleet runs kanban daily. Share one sender module
(`~/.hermes/scripts/_notify.py`: token read from a bot profile's `.env`, value never printed,
splits at ~1900 chars, `allowed_mentions` with `parse: []` + `users`) and keep every job
`deliver='local'`, since the script posts itself.

| Job | Schedule | What it does |
|---|---|---|
| kanban anomaly watch | every 30 min | For every board except `_archived`, read `task_events` by id watermark (DB opened `mode=ro`) and alert on new `crashed`, `reclaimed`, `gave_up`, `protocol_violation`, `block_loop_detected`, plus `blocked` tasks older than 24 h (once per task). On crash/reclaim, save evidence to `~/.hermes/kanban/incidents/<board>_<task>_<event>.log`: payload + last 200 lines of `boards/<b>/logs/<task>.log` + `gateway.log` ±3 min. That turns an unexplained-crash issue into data that accumulates. |
| daily backup | 04:30 | `hermes backup -o ~/.hermes-backups/ -k 7`; silent on success, mention on failure or when free disk drops below 10 GB. |
| weekly metrics | Mon 09:10 | Key numbers + delta vs the previous 7 days as plain lines (Discord does not render tables); the full markdown table goes to a git-ignored `reports/weekly/<YYYY-Www>.md`. |

A fourth job when the user wants to *see* that a spoken request (e.g. "final check") really changed
reasoning effort — **effort watch**, every 5 min, three signals:
- 🎚 task effort set: `task_events.kind='reasoning_effort_set'` on any board (payload has the value).
- ⚙️ profile default changed (mention — it moves cost): compare each bot's effective effort with the
  last run's. Resolve it the way the gateway does — `agent.reasoning_overrides[<model.default>]`
  over `agent.reasoning_effort` — by parsing `config.yaml` with `yaml`, not a regex.
- ✅ actually applied: new rows in `profiles/<bot>/state.db` `sessions` whose
  `json_extract(model_config,'$.reasoning_config.effort')` differs from the profile default
  (watermark on `started_at`). This is the proof; 🎚 without ✅ means set but not yet run.

`hermes config set agent.reasoning_effort <v>` prints "not a recognized config key" but it is the
key the gateway reads (`hermes_constants.resolve_reasoning_config`); add `--force` to silence it.

Test each before scheduling, and report the tests:
- **Watcher.** The first run must save a baseline and send nothing, and long-standing blocked tasks count as baseline, or the first run floods the channel. `--dry-run --since-id <past id>` must replay known past crashes. A second real run must print "nothing new". Run `save_evidence` on a real past crash into a scratch dir and check the three sections. Send one real test message, then `cronjob_manage(action='run')`.
- **Backup.** Time one real run and note its size. Extract `kanban/boards/<b>/kanban.db` from the zip and run `pragma integrity_check` plus a task count. Simulate failure by putting a fake `hermes` that exits non-zero first on `PATH`, against a copy of the script with a scratch output dir, and confirm the alert fires.
- **Effort watch.** On a scratch board, create a task `--initial-status blocked`, set xhigh →
  `--dry-run` must show 🎚; `unblock`, wait for `done`, real run must send 🎚 + ✅ (and the
  session row shows `xhigh`). Flip one bot's default with `config set … --force` and back → two ⚙️
  alerts; `diff` the config against a pre-test copy to prove it was restored. A `--since <epoch>`
  replay over old CLI sessions finding nothing is expected (they ran at the default).
- **Weekly.** Cross-check the posted numbers against direct `sqlite3` counts for the same windows, then `.gitignore` the reports folder before the first run writes into a tracked repo.

`hermes backup` already excludes the code checkout, venvs, `node_modules` and profile
`cache/` except media/citations. A profile whose `du` shows tens of GB (usually
`cache/scratch`) still backs up to about 200 MB in about 10 s, so measure one run instead of
estimating from `du`.

## Measure before claiming a threshold

On macOS: `shutil.disk_usage(path)` for disk; `vm_stat` page counts plus `sysctl -n hw.memsize`
for memory (treat free+inactive as available); `os.getloadavg()[1] / os.cpu_count()` for
sustained CPU, where 1.0 means the cores are exactly saturated.

## Usage/cost reporting spans profiles

`hermes insights --days N` reports only the profile it runs under. Sum across homes for a fleet
total:

```bash
HERMES_HOME=~/.hermes/profiles/<bot> hermes insights --days 7
```

Its cost figure is an ESTIMATE from the price catalog and omits sessions with no pricing data —
so a profile can show huge token counts and a tiny dollar figure. Parse the `Unknown: N session(s)`
line and surface it with the total; presenting the estimate as the bill understates it.
