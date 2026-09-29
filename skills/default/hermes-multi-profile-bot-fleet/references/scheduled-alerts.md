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
