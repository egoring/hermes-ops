# Token cost & fleet-health audit (wake vs notify, cache, crashes)

Use when the user asks how to improve the bot structure, cut tokens, or why cards crash.
Re-derive every number from raw DBs (open read-only: `sqlite3 'file:<db>?mode=ro'`).

## 1. Where the money goes (per profile state.db)
```
select source, count(*), sum(api_call_count), round(sum(estimated_cost_usd)),
  round(sum(cache_read_tokens)*1.0/sum(api_call_count)/1000) ctx_k,
  round(sum(cache_write_tokens)*1.0/sum(api_call_count)/1000,1) cw_k
from sessions group by source;
```
- Human message = `messages.role='user'` not containing `[kanban]`. Normalise to
  $/human-message and $/call so periods with different traffic compare.
- Idle gaps: `lag(timestamp)` over assistant/user messages; a gap >5 min means the 5m prompt
  cache expired and the whole context was re-written.
- Tool-output share: `sum(length(content))` of `role='tool'` vs all active messages.
- Output tokens are usually <10% of cost on Opus 5.5 (cache reads are 0.05x input), so
  lowering reasoning effort or swapping models saves little and costs quality. Say so.
- `estimated_cost_usd` is an estimate (models missing from `agent/usage_pricing.py` are
  mispriced); label it, never present it as the bill.

## 2. Levers, in order of quality risk (one variable at a time, measure between)
1. `prompt_caching.cache_ttl: auto` (per profile via `hermes -p <p> config set`) — 1h cache
   for human-paced sessions only, 5m for kanban/cron. Zero quality risk. Read once at agent
   creation, so it may need a new session/gateway restart to take effect.
2. `compression.proactive_prune_tokens` (start 48000) — no-LLM dedupe/shrink of OLD large
   tool results only; conversation text kept. Prefer this over lowering the compression
   threshold, which summarises the dialogue itself. Large-window models rarely reach the
   50% threshold, so dumps ride along every turn.
3. Wake routing (below) — habit change, no config.
4. Move waiting out of LLM workers (sleep loops dominate coder cache writes) — scripts/crons.
- Avoid `micro_compact` on Opus 5.5: it breaks the cache prefix every turn and cache reads
  are already very cheap.

## 3. Wake vs notify
Every `wake` replays the whole Discord context (~240k tokens/call on a long thread), while a
kanban review worker reviews at ~90k. Kanban notifications were ~40% of Discord turns.
- `wake` only where the Discord session must act or speak to the user: final completion of
  a phase, a card needing a user decision, fable/final-check results, blocked-with-question.
- `notify` for intermediate coder cards whose review the kanban review worker already
  handles (`request-review --reviewer reviewer-bot`).
- Wake kinds are fixed in code (`_WAKE_KINDS` in `gateway/kanban_watchers_notifier.py`,
  includes review_requested), so the choice is per card at subscribe time.

## 4. Crash/health diagnosis
- Before blaming worker behaviour (sleep loops etc.) for `crashed`, split crashes by error:
  `pid N not alive` vs real exits (rc/exit code). Cross-check each `not alive` verdict
  against the worker's state.db session (still active after the verdict?) and later
  "could not heartbeat" errors in the profile's errors.log — a live worker after the verdict
  means a dispatcher liveness false positive, which also spawns a duplicate worker.
- Compare the recorded `worker_started_at` fingerprint with the live process value AND
  check whether the dispatcher actually reclaimed it; an external reading can differ from
  what the gateway process sees.
- Before designing a patch to Hermes core, check upstream for an existing fix:
  `git log --format='%h %cd %s' HEAD..origin/main > file` then grep the symptom/symbol.
  The repo is a partial clone, so `git show`/`log -- <path>` can take minutes: run them in
  the background writing to a file, never in a foreground call with a short timeout.
  Updating Hermes then beats a local patch (no overwrite on the next update).

## 5. Scheduling follow-up cards
See `stuck-cards.md` → "`scheduled` cards do not release themselves" (release-cron table with
time + condition, update detection via `.git/HEAD`).

## 6. Presenting the plan
- Separate "ranked by quality risk" from "order of execution"; state the execution order
  explicitly (the user asks which one is the recommendation).
- Apply config changes one at a time with a measurement window between them, and never
  within a day of a competition deadline — habit-only changes can start immediately.
- Before proposing a new config lever or local patch, check the installed docs/defaults
  (`hermes_cli/config_defaults.py`, `llms-full.txt`) and upstream log: the feature or fix
  often already exists, switched off or in a newer build.
