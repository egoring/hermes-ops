---
name: hermes-multi-profile-bot-fleet
description: Use when running Hermes bots across profiles. Fleet ops.
---

# Hermes Multi-Profile Bot Fleet

Operating several Hermes profiles as chat bots with split roles (implementer / reviewer /
quick-tasks), coordinated through a kanban board, plus the alerting and dashboard plumbing
around them.

**The governing rule of this whole skill: a bot's self-report is not evidence.** Ask a bot
"are you following rule X?" and it answers from its prompt, not from what it did. Every claim
in this file is verified against process state, logs, or the kanban DB instead.

## Layout

| Layer | Path | Reaches the bot |
|---|---|---|
| Bot identity / role | `~/.hermes/profiles/<bot>/SOUL.md` | **only after gateway restart** |
| Project rules | `<project>/AGENTS.md` | next session, no restart. Kanban workers (cwd = board `default_workdir`) get it in the system prompt. A chat turn gets it in the system prompt **only if the profile's `terminal.cwd` is the project dir**; unset, the gateway cwd is `$HOME` and AGENTS.md arrives lazily as `[Subdirectory context discovered: …]` inside the first tool result touching the project, so the first reply is written without it |
| One-off instruction | kanban task body | immediately |

Put standing role rules in SOUL.md, project conventions in AGENTS.md, and per-task loop
instructions in the task body. A rule placed one layer too high gets restated forever; one
layer too low is forgotten next task. For a project-dedicated bot, pin the project into its
system prompt: `hermes -p <bot> config set terminal.cwd "<project>"` for each bot (back up
`config.yaml` first). Side effect to tell the user: the bot's commands now start in the project
dir, not `$HOME`. Keep the "read `<project>/AGENTS.md` before any project work" line in SOUL.md
as a fallback for bots without a pinned cwd. Keep project
facts (seed lists, opponent sets, thresholds) in AGENTS.md only — a copy in one bot's SOUL.md
drifts from AGENTS.md and bots then disagree on the standard.

## Gateway topology: one multiplexed gateway

The supported direction is one host gateway (default profile, launchd `ai.hermes.gateway`)
serving every profile; per-profile gateways are a deprecated compatibility mode. Each bot still
connects with its own token and uses its own model/SOUL/memory/keys/`terminal.*` per turn.

Migrating (needs user approval — it SIGTERMs every bot gateway):
1. `hermes gateway migrate --multiplex --dry-run` — shows per-profile stop/uninstall steps and
   any blockers (e.g. two profiles sharing one bot token). Show the plan before asking.
2. Check `hermes kanban --board <board> list` for running tasks first.
3. `hermes gateway migrate --multiplex -y`.
4. Verify from state, not the command output: `gateway_state.json` → `served_profiles` lists all
   profiles and every `<profile>:discord` entry is `connected`; `gateway.log` has
   `✓ discord connected (profile: <bot>)` per bot and the kanban dispatcher lock line;
   `launchctl list | grep hermes` shows only the host gateway (+ dashboard).

Trade-offs to state when proposing it: no per-bot restart any more (`hermes -p <bot> gateway
restart|stop|start` exits 78 — only `hermes gateway restart`, which reconnects all bots at once);
one crash takes down all bots (launchd relaunches); old chat threads lose continuity because
secondary session keys become `agent:<profile>:…`; no one-command rollback
(`gateway_migration.json` resumes a failed apply, it does not undo — reverting means
`gateway.standalone: true` per profile + reinstalling services).

After migration all bot logs go to `~/.hermes/logs/gateway.log` (profile named per line), and a
`fatal` entry for the default profile's own platform is pre-existing noise if the default
profile is not used as a bot — check its timestamp before attributing it to the migration.

`⚠ Service definition is stale` → `hermes gateway start` regenerates the plist and restarts
(approval needed; all bots reconnect). Exception: if the plist was hand-edited on purpose (e.g.
the osascript wrapper removed — `references/gateway-resource-usage.md`), the stale warning is
expected and `gateway start` would undo the edit (`hermes gateway restart` does not — it keeps the hand-edited plist; re-check `grep -c osascript` on the plist after any restart anyway). `Bootstrap failed: 5: Input/output error` lines during
it are harmless when the next line reports the service started — confirm with
`hermes gateway status` and the per-bot connected lines.

## Keeping SOUL.md project-agnostic / switching projects

SOUL.md holds role rules only (role split, override clause, severity levels, loop cap, decision authority, mention token). Anything naming a project, path, seed set, opponent list, tool file, or AGENTS.md section number belongs in that project's AGENTS.md. SOUL says only "read AGENTS.md in the working directory; project rules override habits; completion criteria are numbers against the project's own validation method".

Moving rules out of SOUL — order matters:
1. Back up SOUL.md ×3 and AGENTS.md with one timestamp suffix.
2. Add the missing rules to AGENTS.md **first**, then strip SOUL.md. Reversing the order leaves a window where a freshly spawned kanban/review session has neither copy.
3. Grep all SOUL.md files for project words to confirm nothing is left.
4. Run one-shot tests: reviewer "summarize role + review rules + this project's validation" must cite both layers; helper reading a named log must use the project loader.

Editing SOUL/AGENTS while a kanban task runs is safe. Sessions build their system prompt at start, so a running task finishes on the old rules. Only sessions spawned after the edit, such as the review run, see the new ones.

Project switch recommendation:
- Sequential projects: reuse the bots. Create a new project folder with its own AGENTS.md, set `hermes -p <bot> config set terminal.cwd "<new project>"` for each bot, and make a new kanban board.
- Concurrent projects: clone a new bot set with `hermes profile create <name> --clone`, give it new Discord apps and tokens, and a separate channel. One profile has one `terminal.cwd`, so one bot serving two projects mixes their rules.
- Alternative for concurrent work without new bots: set `terminal.cwd` to a common parent. AGENTS.md then only arrives when the first tool call touches the project, so the thread must name the project.
- Per-channel settings (`platforms.discord.channel_overrides[<channel>]`) cover only model, provider and `system_prompt`, not cwd. A channel-per-project setup can only point at its folder through that channel's `system_prompt` ("this channel is <folder>; read its AGENTS.md first").
- Also clear project facts from bot memory when switching; memory is injected regardless of cwd.

### One parent folder, one subfolder per project (e.g. per client or product)

This avoids new bots. AGENTS.md discovery walks from the git root down to the cwd and loads every AGENTS.md on that path. Without a git root it loads only the cwd's file. Target layout: parent `AGENTS.md` = shared rules (reporting, review severity/loop cap, roles, decision authority), `<project>/AGENTS.md` = project-only rules (validation set, domain rules, current deployed build, failed ideas), `git init` at the parent with `logs/` and `.venv` in `.gitignore`, bot `terminal.cwd` = parent, and one kanban board per project whose workdir is the project subfolder.

Timing: don't move a project while kanban verification runs on it. If a second project must start before the first is wound down, create `<parent>/<new>/AGENTS.md` (shared sections copied in) plus a new board and skip `git init` for now — a project-specific parent AGENTS.md would leak into every subfolder. Once the user says the live project is winding down, do the full move.

Full move (rename + symlink — no path rewriting, no venv rebuild):
1. Preflight: `hermes kanban --board <b> list` (nothing running), `ps` for processes under the project path, `du -sh` of top-level items, count files hard-coding the absolute path (`grep -rIlF "<old path>" --exclude-dir={logs,.venv}`), check `.venv/pyvenv.cfg`, bot memories, cron jobs, board `default_workdir`. Hundreds of hard-coded paths is the normal finding — that is why the symlink is used.
2. Back up bot `config.yaml`s, `kanban/boards/<b>/board.json`, AGENTS.md and any memory file you will edit into one `~/.hermes/backups/<ts>/`.
3. If the target parent name already exists, show its contents and age and move it to `~/.Trash/<name>_<ts>` rather than `rm` (recoverable). `ls ~/.Trash` is TCC-blocked; verify with `stat` on the exact path.
4. `mkdir <parent>; mv "<old>" <parent>/<project>; ln -s <parent>/<project> "<old>"`. Same-volume `mv` is an instant rename even for GBs of logs; the symlink keeps every hard-coded path and the venv working. Verify: venv import + one real data read through the project loader.
5. Split AGENTS.md: parent = shared rules (reporting, roles, review, decision authority, behavior tests); project = original domain sections kept verbatim + short "supplement" sections for project-specific review/report/override details, with a header naming the board, work-log doc and interpreter. Draft both in scratch, then prove coverage in Python: every non-blank line of the original must appear in one of the two drafts or be deliberately rewritten into a shared section — list the misses and account for each before writing.
6. `git init` at the parent with `.gitignore` (logs/, **/.venv/, _tmp_*, *.pkl, *.gz, .DS_Store, *.bak_*) — required for the chain load. Commit only when the user asks, and size the candidate set first: `git status --porcelain -uall | wc -l` plus a byte sum of the listed files. Experiment folders (`analysis/`) typically hold hundreds of MB of regenerable result data (json/jsonl/html/csv/txt/log) — add `**/analysis/**/*.<ext>` rules so only scripts and md are tracked, then re-sum. Set `git config core.quotepath off` so non-ASCII paths print readably. Local only: never add a remote unless asked (submission code must stay private).
7. Point Hermes at it: `hermes -p <bot> config set terminal.cwd <parent>` ×3; board `default_workdir` → `<parent>/<project>` (`hermes kanban boards set-default-workdir`); rewrite the old path in bot memories and your own memory.
8. Prove the load chain offline: from `<parent>/<project>`, `agent.prompt_builder._agents_md_directory_chain(Path(cwd))` must return both files and `_load_agents_md(Path(cwd))` must contain a phrase from each.
9. Behavior tests, then ask before `hermes gateway restart` (all bots reconnect) so chat bots pick up the new cwd.

What each surface gets after the move: kanban workers (cwd = board workdir = project) get parent + project AGENTS.md from turn one — boards pass `default_workdir` only to `dir`/`worktree` task kinds, not scratch. A chat bot with cwd = parent gets only the shared file up front; project rules arrive when a tool first touches the project folder. So a no-tools "summarize this project's validation set" test correctly answers "not loaded" — rerun it with file tools allowed; a pass is citing the project numbers after reading.

Each new project needs its own AGENTS.md, but only the project-specific part is new. A bot can draft it from the rules page using the existing file's structure. The user sets the numeric pass thresholds (seed count, cut-off) themselves, since every later verdict hangs on them.

Keep the "current deployed build / main line" lines in AGENTS.md current. A stale baseline there makes every h2h compare against the wrong file. When the user names a new deployed version, check the file exists (`ls submissions/`), update the validation-set line and the structure/lineage lines together, and keep the old baseline as an extra opponent rather than dropping it.

## Editing prompts — always verify the restart landed

Back up before editing any SOUL.md or AGENTS.md: `cp <file> <file>.bak_$(date +%Y%m%d_%H%M)`,
and name the backup path in the report so the user can roll back.

SOUL.md is read at process start. Editing the file changes nothing until the gateway restarts,
and a restart can silently fail to replace the process (drain waits on in-flight runs).
Existing chat sessions also keep their already-built system prompt (cache preservation), so
old threads keep the old rules. With Discord `auto_thread` on (default), every fresh @mention in
the channel opens a new thread = a new session, so the instruction to the user is "start new work
with a fresh channel mention"; `/new` is only needed to reset inside an existing thread (pick the
right bot's `/new` in the slash menu when several bots share the channel). Kanban workers spawn a
fresh process per run and need neither.

```bash
hermes gateway restart                          # multiplexed: all bots
hermes -p <bot> gateway restart                 # only with per-profile gateways
```

Then prove it — compare the serving process's start time against file mtime, not just "the
command printed OK". Same PID as before = not applied. `scripts/verify_fleet.sh` does this for
every profile and handles both topologies (reads the host PID from `gateway_state.json`).

A restart that hangs in drain is usually not real work: check `ps -o %cpu=` first. 0.0% with
repeated `Watch pattern notification` lines in `logs/agent.log` means a chat thread keeps
injecting events — stop that thread rather than escalating to a kill.

## Switching one bot's model

1. Read the current block first: `grep -n -A3 '^model' ~/.hermes/profiles/<bot>/config.yaml`.
2. Set it through the CLI, never by hand-editing: `hermes -p <bot> config set model.default <model-id>`.
   Use a model id you can verify (current session's model, provider catalog) — an invalid id
   fails silently at request time, not at set time. Leave `reasoning_effort` alone unless asked.
3. Restart (needs user approval): `hermes gateway restart` when multiplexed (all bots
   reconnect — say so), else `hermes -p <bot> gateway restart`. Check the bot's running kanban
   work first with `hermes kanban --board <board> show <task_id>`
   (status + latest `[run N]` events) instead of assuming — tasks finish or get closed by the user
   between turns. Kanban workers are separate processes launched by the dispatcher-owning gateway,
   so a bot gateway restart does not interrupt them.
4. Prove the new model loaded from the log, not the restart message:
   `grep -E "Model context warmed|Connected as|discord connected" <log> | tail -3` → a timestamp
   after the restart. `<log>` is `~/.hermes/logs/gateway.log` when multiplexed, else
   `~/.hermes/profiles/<bot>/logs/gateway.log`.
5. Audit the other model-bearing keys in every profile (`delegation.model`, fallback) for stale
   ids while you are there. Verify a NEW id before setting it — the source catalog lags new
   releases, so "not in the catalog" is not a rejection. Do a one-call live probe through the
   bot's own credentials instead (the raw `.env` key may not be the auth path Hermes uses):
   `hermes -p <bot> chat -Q -m <model-id> --max-turns 1 -q "reply with one word"`, then confirm
   in `profiles/<bot>/logs/agent.log` a line `API call #1: model=<model-id> ... finish_reason=stop`
   (or `sessions.model` in state.db). The bot's own answer naming the model proves nothing — it
   echoes config. Dotted ids (`x-5.5`) are normalized to dashed (`x-5-5`); set the dashed form.
   Back up as `config.yaml.bak_<ts>_<purpose>` first.
6. Tell the user to start a fresh session (new channel mention, or `/new` inside a thread).
   Gateway sessions never auto-reset on idle or daily boundaries, and a model switch invalidates
   the prompt cache — continuing the old thread resends its whole history uncached at the new
   model's price.

Restart output warnings about a *stale service definition* or *profiles running their own
gateway* are informational; report them and propose the fix (see Gateway topology), do not act
unasked — multiplexing changes the fleet topology.

## Resuming an old Discord session

Sessions are never deleted by restarts or migration; they stay in `profiles/<bot>/state.db`. A fresh channel mention opens a new thread, which is a new session, so continuity only comes from going back into the ORIGINAL thread and running that bot's `/resume`. Resume is scoped to the thread's session key.

List candidates:

```bash
sqlite3 ~/.hermes/profiles/<bot>/state.db "select id, substr(coalesce(title,''),1,30), message_count, session_key, thread_id
  from sessions where source='discord' order by started_at desc limit 5"
```

(Columns are `session_key`, `chat_id`, `thread_id` and `origin_json`; there is no `origin` column.)

- A session whose key is in the new `agent:<bot>:…` namespace appears in the `/resume` numbered list.
- A session from before multiplex migration has an `agent:main:…` key. It is hidden from the list, so give the user `/resume <session_id>` to run in that same thread.
- A long resumed history is resent every turn and may still carry old rules. Suggest `/compress` after resuming. When the rules changed, suggest a new thread plus "summarize the previous session and continue" instead.

## A long-lived session can start failing every request

`finish_reason=content_filter` with `refusal=(no text)` is the provider refusing server-side,
not a local misconfiguration. Grep `logs/errors.log` for `content_filter` and check the session
id: when every occurrence shares ONE id, the trigger is something already sitting in that
conversation's history, so it is resent on every turn and "try again" fails identically forever.

**Read that session's own user messages before guessing at the trigger** — the usual cause is a
credential the user pasted into the chat, which then matches a secret-detection filter on every
subsequent call:

```bash
sqlite3 ~/.hermes/profiles/<bot>/state.db \
  "SELECT role, substr(replace(content,char(10),' '),1,180) FROM messages
   WHERE session_id='<id>' AND role='user' ORDER BY rowid DESC LIMIT 6;"
```

Fix by starting a fresh session (`/new` or a new thread) rather than rewording. A weeks-old
thread is also carrying its whole history into every call, so the reset cuts token cost at the
same time. Switching to another model in the fleet is the fallback when the history must be kept.
When the cause was a pasted secret, a fresh session is not enough — see below.

## Secrets never travel through chat

A secret pasted into a chat message is persisted in `state.db` in plaintext and replayed to the
provider on every later turn of that session, so one paste both leaks the value and can wedge
the whole thread behind a content filter. Refuse the paste even when the user offers it directly
and even when they point out they did it before — that earlier paste is typically the very thing
breaking the session now, so say so rather than treating it as precedent.

Intake procedure:

1. **Treat an already-pasted secret as compromised.** Have the user revoke/expire it at the
   provider first; moving it to a file does not un-leak a value sitting in a session DB.
2. **The user writes the new value themselves**, in their terminal, straight to the file the tool
   reads — a downloaded credential file moved into place is best, since nothing is ever typed.
3. **Verify without ever printing the value.** Check shape only, then prove it by exercising an
   authenticated command:

```python
s = open(path).read().strip()
print("len:", len(s), "prefix:", s[:5] + "...")   # never the whole value
```

A successful authenticated call is the only real proof; file existence and correct length say
nothing about whether the credential works. Report the shape check and the live call, not the
secret.

When handing the work to a fresh thread, write the new location into the handoff note along with
an explicit "do not print or log this value" instruction — otherwise the next session re-derives
the same unsafe habit.

## Installing a third-party skill into both runtimes

Hermes and Claude Code read different directories (`~/.hermes/skills/` vs `~/.claude/skills/`);
installing to one leaves the other without it. Hermes additionally enforces a **60-char cap on
the frontmatter `description`** — upstream skills written for Claude often carry a paragraph
there and are rejected outright. Trim the copy's description to a short trigger sentence and
move the original text into the body as a comment, so the activation criteria are not lost.

After installing into Hermes, confirm it registered with `skills_list` rather than trusting the
file copy — a frontmatter the loader rejects leaves the files on disk but the skill absent.

## Making skill usage visible in answers

When the user wants to know which skills actually fire, add the requirement to the instruction
layer (`SOUL.md` per profile, `~/.claude/CLAUDE.md` for Claude Code) rather than wiring tool
hooks — every runtime honors it and there is no plumbing to maintain. Require a one-line marker
at the top of the answer naming the loaded skills, and state explicitly that **nothing is printed
when no skill was used**; without that clause every reply grows a "none" line and the signal is
lost in noise.

## Protected instruction files and approval timeouts

`AGENTS.md` writes require per-write approval that can **expire silently**; the write is refused,
not queued. When the refusal says not to retry, don't — tell the user to approve and batch the
remaining edits into that one approval instead of firing them one at a time. Put the exact
pending patch into the deliverable (e.g. an appendix of the design doc) so nothing is lost.

Terminal commands can hit the same approval gate (heredoc `python3 - <<EOF`, multi-command
pipelines) and time out after ~1 minute even when read-only. For read-only inspection of
profile files, logs, and request dumps prefer `read_file` / `search_files`, which don't prompt.
If a terminal probe is blocked, hand the user a short copy-paste command and how to read its
output instead of rephrasing the same probe.

When a blocked command must be retried on the user's "다시 해줘", rerun the identical command and
say beforehand how many approval prompts it will raise (each dangerous op in a chain — force
push, visibility change, private-key-looking text — prompts separately) and that each must be
allowed within 1 minute. Do all reversible prep (edits, local commits, scans) in earlier
unprompted calls so the gated command is only the irreversible tail.

## Verifying which rules a bot actually receives

File contents are not proof the bot sees them. Check, in order:
1. `profiles/<bot>/sessions/request_dump_*.json` (newest) — search for a distinctive phrase from
   SOUL.md and one from the project AGENTS.md; also the `"model"` field. Dumps may predate the
   last restart; get a fresh one with a new channel mention (or `/new` in a thread) + one message.
2. Behavior tests in a fresh session: an ambiguous "fix this" to the reviewer (must delegate), the
   explicit override phrase (must comply), "summarize your role, bans and review rules" (must
   cite both SOUL and AGENTS content — missing AGENTS content means cwd isn't the project).
3. Kanban events (see `references/kanban-review-loop.md`).

To confirm AGENTS.md reached a chat turn: with `terminal.cwd` pinned it is in the session's
`system_prompt` (state.db `sessions.system_prompt`); without it, search for `Subdirectory context
discovered` inside a tool result. Offline check of what a profile would load (run outside the
install tree, or discovery refuses and falls back):

```bash
cd /tmp && HERMES_HOME=~/.hermes/profiles/<bot> ~/.hermes/hermes-agent/venv/bin/python -c "
import sys; sys.path.insert(0,'$HOME/.hermes/hermes-agent')
from agent.prompt_builder import build_context_files_prompt
s=build_context_files_prompt(cwd='<project>', context_length=1000000)
print(len(s), '<distinctive AGENTS.md phrase>' in s)"
```

### Behavior tests without Discord (one-shot CLI)

A one-shot run is a fresh process and fresh session, so it reads the current SOUL.md with no
gateway restart and no `/new`:

```bash
hermes -p <bot> chat -Q -t file --max-turns 6 -q "<test prompt>" 2>&1 | grep -vE "dashboard \[default\]|Ask its owner"
```

- The profile's `terminal.cwd` wins over the shell's cwd: `cd scratch && hermes -p <bot> …` still
  resolves relative paths against the pinned project dir, so the bot reports "file not found".
  Always put ABSOLUTE paths in test prompts.
- Restrict `-t` to `file` (add `terminal` only when needed) so no kanban task can be created.
- Role-split tests run safely against throwaway files in the scratch dir (a 2-line buggy
  function + a small diff): T1 "fix this" with "(no kanban tools here — describe what you would
  do in ≤5 lines)" must yield a spec + coder task plan and leave the file unchanged; T2 the
  explicit override phrase must edit the file (`cat` it after); T4 "review this diff only" must
  return 🔴/🟡/🟢 with no task. These need no Discord.
- Run several bots in parallel from `execute_code` with a thread pool calling `terminal()`; the
  terminal tool rejects `&` backgrounding in foreground commands.
- Give concrete paths in test prompts. A vague "pick any log under logs/" fails on discovery and
  tests the wrong thing; name the file so the test checks the rule (e.g. which loader was used).
- Read the answers for cross-layer contradictions the bot points out — a bot summarizing its
  rules is a cheap way to surface drift between SOUL.md and AGENTS.md.

## Role split that actually holds

The reviewer/architect profile drifts into writing code whenever the user phrases a request as
"just implement it". Counter it in that profile's SOUL.md with an explicit override clause: a
plain "implement this" is NOT permission; only an unambiguous phrase ("don't delegate, write it
yourself") overrides the split, and anything ambiguous gets a one-line clarifying question.

The bot pipeline ends at "criteria met/unmet, with numbers". Shipping, replacing the deployed
build, and closing a verification belong to the user (who may consult a separate model outside
the fleet). Write that authority boundary into AGENTS.md and the reviewer/implementer SOUL.md,
or a user decision to ship below a threshold later reads as a rule violation the bots try to
reopen. See `references/kanban-review-loop.md` → Decision authority.

When the user says the cheap model "couldn't do it", escalation to the expensive model is the
designed path — do not flag it as a role violation. Check what the cheap model was actually
asked to do before calling the routing wrong.

## Model choice: mixed fleet beats one big model

When most of the workload is repeated measurement, log collection, and bulk runs, keep those on
the cheap model and reserve the expensive one for design decisions and reviews — its output is
short and its call count low, so it buys judgment without carrying the token volume. Do not
switch the whole fleet to a single premium model to "simplify"; that pays premium rates for the
bulk work the cheap model already does well. Per-task pins (`--model`) refine this, but a pin
also applies to the task's review run — routing table in `references/kanban-review-loop.md`.
Per-task reasoning effort exists in kanban (DB column, worker gets `--reasoning <v>`, survives unblock) but the v0.21.4 CLI/tools can't set it; call `hermes_cli.kanban_db.set_reasoning_effort` from a small script (see the ops repo's `kanban_set_effort.py`). It applies to every run of that task, so a higher-effort final check must be its own task: create `--initial-status blocked` → set effort → `kanban unblock` (a `ready` task can be claimed before you set it).
A pin-routing table must name every tier, including the default workhorse (e.g. reviewer-owned
non-design chores → Sonnet), not only the exceptions.

Reasoning effort per stage: without any task pin, each run uses its assignee profile's
`agent.reasoning_effort` (`hermes -p <bot> config get agent.reasoning_effort`), and a review run
is dispatched as the reviewer — so "high only at final verification" already holds when the
reviewer profile is high and the implementer medium. A per-task `reasoning_effort` column exists
(dispatcher passes `--reasoning`, settable via the dashboard API) but, like `--model`, it applies
to EVERY run of the task including review, and bots have no CLI/tool to set it; stage-specific
switching would need a custom hook. Recommend keeping design on high (spec defects are a real
share of rejects and cost more loops than the effort saves) and cutting cost via model routing.

Cron jobs are not a model tier: check `cron/jobs.json` per profile before claiming which bot
"does cron". Monitoring/usage reports should be `no_agent` scripts (zero tokens, deterministic);
put a job on the cheap bot's profile with a model only when its output needs interpretation or
summarizing.

## Depth

- `references/kanban-review-loop.md` — making implementer→reviewer handoff actually route.
- `references/discord-bot-plumbing.md` — mentions, tokens, profile/account mapping.
- `references/scheduled-alerts.md` — zero-token cron alerts, edge-triggered notification.
- `references/dashboard-service.md` — running the web dashboard, autostart, the env trap.
- `references/fleet-design-doc.md` — writing/revising the fleet architecture document, and
  evolving the design from kanban metrics (reject rate, crashes, unused task features).
- `references/gateway-resource-usage.md` — measuring gateway CPU/RAM right (CPU-time deltas,
  sleep bias), the macOS osascript-wrapper idle-CPU cost and how to remove it, and whole-machine
  battery triage (energy ranking, hung apps, pmset battery settings).
- `references/ops-repo-publishing.md` — keeping ops docs project-agnostic in their own repo,
  kanban hygiene (notify-subscription cleanup), pushing the repo + own skills to GitHub without
  leaking IDs, going public (withholding live-project content, squash, per-folder commit
  labels), and filing upstream bug reports.
- `scripts/verify_fleet.sh` — one-shot check that prompt edits are live on every profile.

## Operator vs bot work split

This session's operator (you, outside the fleet) owns Hermes ops: profiles, SOUL, shared
AGENTS.md, gateway, board settings, the fleet design doc. Project/domain work (committing bot
outputs, work-log entries, blocked task triage, path cleanup inside the project) goes to the
bots. When a review turns up project-side leftovers, don't do them yourself: write
`<project>/docs/봇_인계_<date>.md` with a numbered table (task / owner bot / notes), a
"changed environment" preamble (new paths, git rules, no push) and a "do not touch" list (Hermes
config, SOUL, shared AGENTS, ops doc), then give the user a one-line paste-ready Discord prompt
for a fresh thread. Before listing uncommitted files as bot leftovers, check whether a running
kanban task produced them (`kanban list` + task workspace) — they may vanish when it finishes.

## Full health check ("전체적으로 확인")

One batch, then a findings table: folder/symlink layout, git (commits, untracked count and
biggest files, no remote, no logs/.venv tracked), AGENTS.md headers + stale-version grep, SOUL
project-word grep, per-bot `terminal.cwd` + model, board `default_workdir`, gateway (launchd PID,
osascript count, CPU, ERROR count since last restart, per-bot connected lines), kanban
non-done tasks, venv import + one real data read, memory files grepped for old paths, disk.
Separate "new findings" (with a proposed fix and a question) from "all green" rows, and fix your
own stale memory entries in the same pass.

## Reporting to this user

When the user says "하나씩 체크하면서 진행" or "추천해주는대로 해줘", track the items with the todo
list, execute in the recommended order without re-asking per item, and still stop for the
standing gates (gateway restart, protected AGENTS.md edits, pushes/force-pushes, anything leaving
the machine). Re-rank the remaining items when data from an earlier item disproves its premise,
and say so.

Korean, direct, peer tone. Lead with the finding, then the evidence table. When the user asks
"measure again", re-measure fresh (new deltas, same method) and compare against the previous
numbers in the table — including correcting an earlier estimate that the new data disproves. State measured
numbers (PIDs, byte counts, HTTP codes) rather than "it should work now". When you were wrong
earlier in the session, say so plainly in one line and correct it — do not quietly restate.
