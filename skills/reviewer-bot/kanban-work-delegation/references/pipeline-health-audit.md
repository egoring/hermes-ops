# Auditing the multi-bot pipeline from kanban data

Use when the user asks "how can the agent structure / bot setup be improved" or
why work is slow or flaky. Answer from the board databases, not from impressions.
The recommendation is only as good as the numbers behind it, and the first causal
reading of those numbers is usually too simple.

## 1. Inventory (read-only)

```bash
ls ~/.hermes/profiles                      # which bots exist
grep -A2 '^model:' ~/.hermes/profiles/*/config.yaml   # tier per bot
hermes kanban boards                       # boards + counts
hermes cron list                           # existing no-agent watchers
ls ~/.hermes/profiles/reviewer-bot/scripts # wrappers that may already solve a proposal
```

Per-board DBs live at `~/.hermes/kanban/boards/<slug>/kanban.db`. Open them
read-only (`sqlite3 'file:<db>?mode=ro'`) because the gateway writes them live.
Tables: `tasks`, `task_runs` (profile, outcome, started_at, ended_at, summary,
error, claim_lock), `task_events` (kind, payload), `task_comments`.
Other evidence: `~/.hermes/profiles/<bot>/state.db` (sessions/messages per worker),
`~/.hermes/profiles/<bot>/logs/errors.log`, `~/.hermes/logs/gateway.log`,
`~/.hermes/kanban/incidents/*.log`, and per-card worker logs.

## 2. Queries that expose the structure

Run them per board with `sqlite3 -header -column <db> "..."`:

- **Time per bot and outcome**:
  `select profile, outcome, count(*), round(avg((ended_at-started_at)/60.0),1) avg_min, round(sum((ended_at-started_at)/3600.0),1) tot_h from task_runs group by 1,2`
- **Crash causes, split by kind**: group `substr(error,1,140)` where
  `outcome='crashed'`. Separate dispatcher verdicts (`pid N not alive`) from real
  exits (exit codes, `rc=0` protocol violation, provider errors). Do the
  crashed-but-alive checks in section 3 before attributing anything to a crash.
- **Cost of LLM waiting**: count `sleep` commands and their total seconds in the
  worker logs, as a share of total coder run time. Measure waiting this way, not
  through crash counts.
- **Blocks used as waits**: classify coder `blocked` summaries into needs-input,
  approval or capability refusals, auto-decomposer duplicates, and "chain running,
  no human input needed" parks. Report the share of each. Only the last kind is a
  wait.
- **Card size**: runs per task (`group by task_id order by count(*) desc`) and
  review rounds per task (`sum(outcome='review_requested')`). One card with dozens
  of runs or more than 3 review rounds is a phase, not a verifiable step, and the
  3-round cap cannot work on it. Also count unblocks, reclaims and comments on
  the biggest card.
- **Review depth**: bucket reviewer runs that follow a `review_requested` by
  duration (<1m, 1-3m, 3-10m, >10m). **Exclude 0-1 s runs with `claim_lock IS
  NULL`.** Those are chat-session `complete` calls, not dispatched reviews. For the
  remaining short ones, count tool calls in the reviewer's `state.db`. The real
  defect is usually "no record of what was recomputed", not the duration itself.
- **Dual processing paths**: count 0-second runs completed from the chat session,
  and notifier wake-ups of the chat session. A chat session that transitions cards
  is a second worker and the root cause of duplicate side effects.
- **Misused verdicts**: count `changes_requested` whose summary contains a
  "GO / not a rejection" marker. Report board total and per-card counts
  separately.
- **Event mix**: `select kind, count(*) from task_events group by kind`. Look at
  heartbeat volume, `block_loop_detected`, `protocol_violation`, `gave_up`.

## 3. Crashed-but-alive forensics (do before quoting lost hours)

A `crashed` / `pid not alive` record is the dispatcher's liveness verdict, not
proof of death. For each crashed run:

1. Did the worker's session in `state.db` stay open after the verdict time? A
   session that closes minutes or hours later, or only right after the verdict
   (when the reclaim killed it), means it was alive.
2. Does the worker's `errors.log` show `could not heartbeat <task> (unknown id or
   not running)` after the verdict? A dead process cannot try to heartbeat.
3. Was a second worker spawned on the same card while the first lived? That is
   the dangerous consequence (double pushes), and it is bigger than the lost time.
4. Check the liveness code path: `hermes_cli/kanban_db_dispatch.py`
   `_worker_alive` / `_pid_recycled` compare a start-time fingerprint recorded at
   spawn. On macOS that is `round(psutil create_time × 100)`, which can drift by
   seconds. Compare the `spawned` event's fingerprint with a fresh reading for a
   live worker pid.
5. **Before you write a fix spec, test the hypothesis against a live
   counterexample.** A drifted reading taken from an external interpreter can
   disagree with what the gateway process sees. A live worker whose fingerprint
   reads as drifted, yet is not reclaimed tick after tick, is exactly such a
   counterexample. When one exists, make the next card "confirm the cause with
   in-process readings and a sampled drift maximum", not "widen the tolerance".

Only the crashes that survive these checks are real; only then can lost hours be
attributed to waiting, OOM, or anything else.

## 4. Mapping symptoms to fixes (ranked by usual impact)

| Symptom | Fix |
|---|---|
| Crashes whose workers were actually alive; duplicate workers on one card | Fix the dispatcher liveness check first (tolerant fingerprint compare and/or pid+argv check). It is a platform code fix, so it needs the user's decision on a local patch vs an upstream report. Every other fix inherits the false crashes until then. |
| Chat session completing cards; two verdicts or two submits racing on one card | First check whether the irreversible part (submit, push) is already guarded by a wrapper with a lock and ledger, and whether that guard has already blocked a race. If it has, the remaining harm is a duplicated review and a confusing comment, both reversible. Then do not restrict the chat session: losing chat-side approval costs the user more than it saves. Close the gap by extending the wrapper to every project that lacks one. Restrict the chat session (single review path, enforced by profile tool policy) only where no such guard can exist. |
| Duplicate or unintended irreversible actions (submissions, pushes) | A single `submit` wrapper with a ledger, same-hash refusal, daily-quota check, required card id and a file lock. Check whether one already exists before proposing it. Generalise it after the deadline; the "no direct CLI submit" rule can apply now. |
| Short reviews, hand-typed verification commands | A per-project deterministic `gate` script (commit hash, cross-machine md5, metric recomputation, the project's pass/fail rule). The worker attaches its output and the reviewer re-runs it. Have someone other than its designer check the gate. |
| Most coder time spent in `sleep`; per-card wake crons multiplying | A non-LLM pipeline runner plus an experiment registry: train → infer → gate → conditional submit runs as a script, one experiment is a registry row, and the LLM handles specs, interpretation and decisions. A smaller step is a wake condition on a `scheduled` card, released by a no-agent cron. Give either one a TTL and a stale-condition alert, and confirm that no-agent scripts are not blocked by the command scanner. |
| Cards with dozens of runs or rounds | One card per verifiable step under a parent phase card. Steer with comment + unblock or with the next card. Turn auto-decomposition off for these cards, otherwise duplicate child cards appear. |
| Workers unable to read a spec | Find the actual cause before prescribing (body length vs `show --json` output with all comments, headless execution refusals). The fix is usually "spec = file path in the body" plus a rule against reading `show --json`, not attachments. |
| Lessons not accumulating (memory full) | A retrospective card at each project end that moves lessons into skills or the shared AGENTS.md. |

Usually not recommended, with the reason:

- **A dedicated watcher bot**: watching is already non-LLM; it repeats the cost of
  LLM waiting.
- **`goal_mode` as the completion judge**: an auxiliary judge does not replace
  numeric project criteria. Build the gate first.
- **Swarm or parallel coders**: limited value when one GPU or machine is the
  bottleneck.
- **More bots or reshuffled model tiers**: losses rarely come from model quality.
  They come from platform bugs, LLM waiting and duplicated processing paths.

## 4b. Token / cost audit ("save tokens without losing quality")

Per-session token counts and estimated cost live in each profile's `state.db`,
table `sessions`: `source` (discord / kanban / cron / oneshot), `api_call_count`,
`cache_read_tokens`, `cache_write_tokens`, `output_tokens`, `estimated_cost_usd`.
Open it read-only.

1. **Spend by bot and source**: `group by source` with sums of the token columns
   and cost, for every profile. The interactive chat session of the orchestrator
   is usually the largest line, often larger than all workers together.
2. **Context size per call** = `cache_read_tokens / api_call_count`. Compare
   chat against kanban; a chat session that runs for weeks keeps a context of
   hundreds of thousands of tokens. Check the compression threshold in
   `hermes config show` (with `HERMES_HOME` set to the profile): a threshold of
   50% of a 1M window means compression starts only at 500k.
3. **Where the money goes**: compare output-token cost against cache-write cost.
   When output is under ~10% of the spend, lowering reasoning effort or the model
   tier saves little and costs quality. Do not recommend it.
4. **Cold cache rewrites**: from table `messages`, compute the gap between
   consecutive user messages per session (`lag(timestamp)`). Any gap over 5 min
   with `prompt_caching.cache_ttl: 5m` rewrites the whole context. Split
   the user messages into human turns and `[kanban]` notification turns.
5. **Duplicated processing**: count notification turns that wake the chat
   session for events a dispatched worker already handles (review requests).

Levers, cheapest in quality first:

- `prompt_caching.cache_ttl: auto`: 1h cache for human-paced sources, 5m for
  kanban/cron. An explicit global `5m` disables it. The 1h tier writes at 2x
  instead of 1.25x, so it pays off only on human-paced sessions with 5-60 min
  gaps.
- A lower compression threshold on the orchestrator profile only, plus a new
  thread per topic. Decisions and numbers survive on cards and in docs.
- Subscribe intermediate events (review requested) with `--delivery-mode
  notify`, and keep `wake` for completion and decision events. This is an
  orchestrator habit, not a restriction.
- Move waiting out of workers: pauses longer than 5 min rewrite the worker's
  cache on every poll.

Prices for new model ids may be missing from Hermes' pricing table
(`agent/usage_pricing.py`), so the estimate for that bot is unreliable. Say
so, label every figure as a `state.db` estimate, and set a 1-week re-measure
criterion: cost per human turn, mean context per call, and a count of quality
regressions such as re-asked context. Apply config changes after a deadline,
through a coder card using `hermes config set`.

## 5. Get an independent opinion before ranking

After writing your diagnosis, put it in front of a different model (a read-only
opinion card, not a final check). The card holds your numbered claims with their
numbers, your fixes A..N, and these instructions: recompute every claim with
queries attached; give alternative explanations per diagnosis; mark each fix
agree, partial or disagree with its risks; add up to 3 missed fixes with data.
If the user wants better directions, also ask for 1-2 structural alternatives,
each with evidence, cost, migration order and a numeric falsification criterion,
and allow "no better direction" as an answer. A second model re-deriving the
cause from logs and code routinely overturns the top-ranked fix.

## 6. Reporting

- Lead with the conclusion: is the role split itself the problem?
- Every diagnosis line carries its number and board. Mark which numbers are
  causal readings vs counts.
- Own your own misuse in the data (verdict misuse, chat-side card transitions)
  plainly. When a second opinion overturns your diagnosis, say so first.
- Do not adopt the second opinion's proposals wholesale. Weigh each against what
  already guards the risk; a structural restriction justified by an incident
  that an existing wrapper has since blocked is over-weighted. When the user
  questions one, re-check that and concede plainly if the guard already covers
  it.
- Split each proposal into "now" (rules, own habits) and "after the deadline"
  (config, code). Present them as numbered decisions, and let the user approve
  them one at a time.
- Respect deadlines: do not touch running chains or restart the gateway. Rules
  can go now; code and infrastructure changes go after the deadline, through
  design → coder → review. Park post-deadline cards as `scheduled` so they do not
  start early. Propose a separate infra board so this work does not mix with
  competition boards.
- End with the decisions the user needs to make and an @-mention.
