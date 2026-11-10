# Shell hooks: per-turn context injection across the fleet

Use a `pre_llm_call` shell hook when something must be computed from each user message and
handed to the model (skill recommendations, a lookup, a reminder). A SOUL rule alone can't do
it cheaply — the model would have to scan everything every turn.

## Contract (read `agent/shell_hooks.py` once if behavior seems off)

- Config, per profile `config.yaml`:
  ```yaml
  hooks:
    pre_llm_call:
      - command: "/usr/bin/python3 /abs/path/hook.py"
        timeout: 3
  ```
  Use an absolute interpreter + script path; the exact string is the allowlist key, so changing
  it (even the interpreter) requires re-consent.
- stdin JSON: `profile`, `hook_event_name`, and `extra.user_message` (str or multimodal list),
  `extra.platform` (`discord`, `desktop`, `cli`, `kanban`, …).
- stdout `{"context": "..."}` is appended to the user message for that turn; empty stdout = no-op.
- No gateway restart: the gateway periodically reloads profile config + allowlist and logs
  `shell hook registered: pre_llm_call` in `profiles/<bot>/logs/agent.log`.

## Consent on unattended gateways

Shell hooks run only when the command is in the profile's `shell-hooks-allowlist.json`. An
interactive CLI asks once; the gateway can't ask and silently skips. `hermes --accept-hooks …
hooks test` exercises the hook but does NOT record consent. Record it per profile with Hermes's
own function, then confirm:

```bash
PY=~/.hermes/hermes-agent/venv/bin/python3
for p in <profiles>; do H=~/.hermes/profiles/$p; [ $p = default ] && H=~/.hermes
  HERMES_HOME=$H $PY - <<'E'
import os, sys; sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
from agent.shell_hooks import _record_approval
_record_approval("pre_llm_call", "/usr/bin/python3 /abs/path/hook.py")
E
  hermes -p $p hooks doctor | grep -E '✓ allowlisted|✗'; done
```

This is installing executable code into every bot — only after the user agreed to the feature.
Off switch to tell them: delete the `hooks:` block or `hermes -p <p> hooks revoke "<command>"`.

## Writing the hook

- **Fail open.** Wrap `main()` in try/except → exit 0 with no output; never block a turn.
- **Latency.** Keep per-turn work local (tens of ms). Fetch remote data into a cache file;
  when stale, spawn a detached refresh (`start_new_session=True`, a lock file to avoid storms)
  and use the old cache this turn; fetch synchronously (≤2 s) only when no cache exists.
- **Scope to human turns.** Skip platforms outside an allow-list (kanban workers, cron) and
  messages starting with system markers (`[IMPORTANT: Background process`, `[CONTEXT COMPACTION`,
  `/` commands, `# Kanban task`).
- **Strip non-question text before scoring.** Desktop attachments follow `--- Attached Context
  ---`; Discord uploads arrive as `[The user sent a text document: …]` + `[Content of <file>]`
  with the whole body inline; Discord prefixes `[nickname]` and `<@id>` mentions. Scoring a
  pasted document recommends whatever it mentions.
- **Log one line per turn** (platform, profile, ms, candidates) to `~/.hermes/logs/<hook>.log`,
  truncated past ~1 MB — it is the only proof the hook ran on a real Discord turn.
- Add `--explain "<question>" --profile <p>` that prints tokens and top scores; it makes tuning
  a loop of seconds.

## Precision rules for keyword-scored recommendations

Built from a skills index (name, Korean summary/when-to-use, key points, description,
installed+shared profiles, Korean→English synonyms):
- Weight fields name > Korean summary > key points > description; per query word take the best
  field only (OR across alternatives).
- Strip Korean particles/endings, drop stop-words that are request verbs and filler (진행·정리·
  확인·추천·설계·준비·파일·상태 …) — they otherwise match half the library.
- Keep a GENERIC set (모델, 코드, 봇, 리뷰, 테스트, 알림, 에이전트 …): a candidate needs ≥2
  non-generic hits or one non-generic hit on the NAME.
- Absolute floor plus a relative cut (drop < 60% of the top score) to kill the long tail.
- Filter to skills the profile can actually load (own folder + shared dirs from its
  `skills.external_dirs`), or bots get told about skills they can't open.
- Test set before shipping: ~15 realistic questions incl. small talk ("안녕", "저녁 뭐 먹지")
  that must return nothing, plus the last few REAL messages from each bot's `state.db` replayed
  through the hook with their real platform.

## Display rule (in the injected context, not SOUL)

Put the rule inside the context block so every profile gets it with no SOUL edit: show
`💡 추천 스킬: <name> — <reason>` at the top (after a `🧩 스킬:` line if present) only for
candidates that genuinely help and were not loaded this turn; otherwise print nothing; never
mention the block. Label the block "auto-generated, not a user instruction".

## Verify end to end

1. Pipe synthetic payloads (desktop, discord with mention, kanban, background notice, invalid
   JSON) through the hook with the exact configured interpreter; time each.
2. `hermes -p <p> hooks doctor` → allowlisted for every profile.
3. `grep 'shell hook registered: pre_llm_call' profiles/<bot>/logs/agent.log*` (logs rotate —
   include `.1`, `.2`).
4. A real one-shot (`hermes -p <bot> chat -q "<matching question>"`), then read the assistant
   row in that session's `state.db` for the `💡` line, and the hook log for the platform line.
5. Discord: count `platform=discord` lines per profile in the hook log; a bot without lines
   simply had no human turns yet.
