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

Trade-offs to state when proposing it: `hermes gateway restart` reconnects all bots at once;
`hermes -p <bot> gateway restart` now hot-unserves/re-serves ONE profile on the host ("Profile
'<bot>' restarted by the host gateway", siblings stay connected). Use it for a single bot's
Discord/config change. If it instead prints the `gateway.standalone: true …` compatibility hint,
nothing was restarted, so don't report it as applied. Watch for the adapter's own `✓ discord
reconnected` line; `stop` parks the profile (`start` unparks). Older builds exited 78 here;
if so, fall back to the full restart;
one crash takes down all bots (launchd relaunches); old chat threads lose continuity because
secondary session keys become `agent:<profile>:…`; no one-command rollback
(`gateway_migration.json` resumes a failed apply, it does not undo — reverting means
`gateway.standalone: true` per profile + reinstalling services).

After migration all bot logs go to `~/.hermes/logs/gateway.log` (profile named per line), and a
`fatal` entry for the default profile's own platform is pre-existing noise if the default
profile is not used as a bot — check its timestamp before attributing it to the migration.

`⚠ Service definition is stale` → `hermes gateway start` regenerates the plist and restarts
(approval needed; all bots reconnect). If the plist was hand-edited on purpose, the stale warning
is expected and `gateway start` / `update` / `install` undo the edit (`hermes gateway restart`
keeps it). Prefer fixing the cause by updating Hermes over keeping a hand-edited plist — see
`references/gateway-resource-usage.md`. `Bootstrap failed: 5: Input/output error` lines during
it are harmless when the next line reports the service started — confirm with
`hermes gateway status` and the per-bot connected lines.

## Updating Hermes (`hermes update`)

Gated: it restarts the gateway (all bots) and the desktop backend (the current desktop chat may
drop). Order:
1. Preflight in one batch: no running kanban tasks (`status` counts + `pgrep -fl "work kanban
   task"`), `git status --porcelain` in `~/.hermes/hermes-agent` empty, commits behind
   (`git fetch && git rev-list --count HEAD..origin/main`), whether the wanted fix commit is in
   `origin/main` (`git merge-base --is-ancestor <sha> origin/main`), and `hermes update --plan`.
2. Back up plist + every profile's `config.yaml` and `SOUL.md` to `~/.hermes/backups/<ts>_update/`
   and record the before-state (wrapper/gateway CPU).
3. Run it as a tracked background job (`terminal(background=true, notify=true)`; `nohup`/`&`
   are rejected), output to the backup dir: `hermes update --yes > …/update.log 2>&1`. Tell the
   user the desktop chat may disconnect; if the turn is interrupted, read the log tail first.
4. Verify, as a table: `hermes --version`; `update.log` ends `exit=0` + fleet version check "up to
   date"; `gateway status` says the definition matches; per-bot `discord connected` lines after
   the restart; each bot's `model.default`, `agent.reasoning_effort`, `terminal.cwd`, delegation
   model unchanged; kanban task counts and cron list unchanged; your own helper scripts still run;
   the targeted problem re-measured (e.g. 60 s CPU-time delta).
5. Count errors since the restart by timestamp, not by grepping `Traceback`: traceback lines carry
   no timestamp, so a naive filter pulls in weeks-old ones — `awk '$1" "$2>="<ts>"'` keeps every
   non-timestamp line too (letters sort after digits), inflating counts into the hundreds. Attribute each to the nearest
   preceding timestamped line before calling it new.
6. Update the ops issues table, memory, and any upstream issue (comment with before/after numbers,
   then close).
7. Count active skills before and after (`find ~/.hermes/skills -name SKILL.md -not -path
   '*/.archive/*' | wc -l`) — see below.

## Skills vanished ("플러그인이 빠졌다", a big "No longer available" list)

Usually the curator, not the user's last action. Prove the cause before blaming a recent step
(a keychain/credential change does not remove skills or Claude Code plugins):
1. `ls ~/.hermes/skills/.archive` + `stat -f '%Sm' -t '%m-%d %H:%M' .archive/*` grouped by time,
   and `grep 'curator: auto: .* archived' ~/.hermes/logs/gateway.log` — a batch with one
   timestamp is the 30-day-unused auto-archive. Archives are recoverable, never deleted.
2. Separately confirm Claude Code side if the user mentions plugins: `claude plugin list`. Its
   "Synced from claude.ai" block vanishes while logged out (e.g. after deleting the
   `Claude Code-credentials` keychain item) and returns after `/login` — not a loss. A synced
   plugin with the same name as a local one is ignored; silence it with
   `claude plugin disable <name>@synced`. `plugins/.trash/` holding only old versions of one
   plugin is update leftovers.
3. Restore a chosen subset, not everything (each restored skill costs index tokens every turn):
   `hermes curator restore <name>`. Before restoring, check whether a newer bundled skill
   replaced it (e.g. one office skill covering docx/xlsx/pptx) and skip the duplicates.
4. `restore` fails with `destination already exists` when a CATEGORY folder has the skill's
   name (`skills/github/` holding `github-*`); `mv .archive/<name>` to its original category
   path by hand (e.g. `software-development/<name>`) and confirm with `skills list`.
5. `hermes curator pin` refuses bundled/hub skills, yet the 30-day auto-archive still moves them
   (the CLI's "never touched" wording is wrong). For skills the user wants kept:
   `hermes curator restore <n> && hermes curator lock <n>` — locked skills are skipped by the
   automatic transitions (side effect: agents can no longer `skill_manage` them). Re-check
   `.archive/` a few days later. Pin only agent-created skills.
Shared-skill links (`~/.hermes/shared-skills`) point at default originals; if the curator archives
an original, the bots silently lose it — re-check `skills list | grep -c external` after an
archive batch.

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

### Can work from different sessions mix?

Chat history never crosses sessions and kanban workers see only their board. Leakage comes from
state shared across ALL of a bot's sessions — check each when the user asks:
- **Bot memory** (`profiles/<bot>/memories/MEMORY.md`) is injected into every session; a line
  about project A reaches project B's thread. Keep project facts in that project's AGENTS.md.
- **Background skill review** edits the bot's skills after sessions (`grep "Background review
  complete" profiles/*/logs/agent.log` → `result=skill`), so one project's specifics land in
  skills other projects load.
- **Shared cwd**: with `terminal.cwd` = parent, a thread can open another project's files and pull
  in its AGENTS.md (search that session's `messages.tool_calls` for the other folder name).
- **One thread, several jobs/bots**: bots take over each other's work.
Mitigation to recommend: one project per thread (name it in the first message), project facts in
AGENTS.md not memory, every kanban task `--workspace dir:<project>`.

The real cross-project risk on one machine is usually **CPU contention, not context**: check
`uptime` load vs `sysctl -n hw.ncpu` and `pgrep -fl "work kanban task"` across boards. Workers
from two projects running at once skew timing-sensitive measurements (per-step timeouts, h2h
wall time, benchmark seconds) in the other project. Recommend not overlapping heavy
measurement runs across boards, and require reports to record loadavg so a slow result can be
attributed. When moving a memory line into a project AGENTS.md, note that open threads keep
the old memory until a new session starts.

### One parent folder, one subfolder per project (e.g. per client or product)

This avoids new bots. AGENTS.md discovery walks from the git root down to the cwd and loads every AGENTS.md on that path. Without a git root it loads only the cwd's file. **A project subfolder with its own `.git` (cloned repo, `git init` for its own remote) becomes its own root, so the parent's shared AGENTS.md silently stops loading there.** Check every project folder with `agent.prompt_builder._agents_md_directory_chain(Path(<project>))` (Hermes venv) — each must list the parent. For a nested repo, keep its git and make the project AGENTS.md open with "read `../AGENTS.md` (shared rules) first; this file wins on conflict". If that nested repo is public, add `AGENTS.md` to its `.git/info/exclude` (local, untracked) so bot-ops rules never get pushed with it. A bot asked "do the shared rules apply to every project folder?" answers from its prompt and says yes. Run the chain check and correct it with the output. Also check each board's `default_workdir` (`board.json`): a board created without `--default-workdir` has `null`, and its tasks fall back to whatever workspace the creator passed. Target layout: parent `AGENTS.md` = shared rules (reporting, review severity/loop cap, roles, decision authority), `<project>/AGENTS.md` = project-only rules (validation set, domain rules, current deployed build, failed ideas), `git init` at the parent with `logs/` and `.venv` in `.gitignore`, bot `terminal.cwd` = parent, and one kanban board per project whose workdir is the project subfolder.

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

What each surface gets after the move: kanban workers (cwd = board workdir = project) get parent + project AGENTS.md from turn one — boards pass `default_workdir` only to `dir`/`worktree` task kinds, not scratch. **Task creation defaults to `scratch`** (CLI and the bots' `kanban_create` tool alike), so a task created without a workspace runs in a temp dir with no project AGENTS.md. Always pass `--workspace dir:<absolute project path>` (bare `dir` is rejected) or `workspace_kind="dir"` + `workspace_path`, check `workspace_kind/workspace_path` in the DB right after creating, and write the rule into the shared AGENTS.md and the task-creating bot's SOUL. A task created wrong: `block` then `archive` it before a worker claims it, and recreate. A chat bot with cwd = parent gets only the shared file up front; project rules arrive when a tool first touches the project folder. So a no-tools "summarize this project's validation set" test correctly answers "not loaded" — rerun it with file tools allowed; a pass is citing the project numbers after reading.

New project AGENTS.md checklist:
- The header line points at the shared file.
- Board name and work-log path are listed.
- The rules page is saved verbatim to `docs/rules_원문_<date>.txt` and the AGENTS summary cites
  its clause numbers.
- Every rule that is not yet verified is written as `<미확인>`, together with "don't start work
  that depends on it until the source is quoted". Fill it in once the user supplies the text.
- When the project's deliverables are themselves prompts (agent configs, `SKILL.md`,
  `system.md`), add a line saying those files are artifacts to edit, not instructions to the bot.
  Also forbid naming a deliverable file `AGENTS.md`, because subdirectory discovery would load it
  as bot rules.
- Confirm it reaches only that folder with `_agents_md_candidates` on it and on a sibling
  project.

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
hermes -p <bot> gateway restart                 # one bot (multiplexed host re-serves just it)
```

The multiplex re-scan on a `config.yaml`/`.env` change only ADDS missing adapters — an
already-connected bot keeps its old Discord gates (log: `Re-scanned profile '<bot>' … (0
adapter(s) connected)`). After changing a connected bot's `discord.*` settings, run
`hermes -p <bot> gateway restart` and confirm a fresh `✓ discord connected (profile: <bot>)`.
Adapter-level settings (mention gating, allow_bots) then apply to existing threads too; SOUL does
not (below).

Applying a SOUL change to a thread that is already running: the session restores its stored
system prompt every turn, and gateway `/compress` deliberately keeps that seeded prompt — it does
NOT reload SOUL. Options to offer: (1) in the thread, "re-read `<SOUL path>` and follow rule X"
(immediate, conversation-level, may fade in a long thread); (2) have it write a handoff note, then
`/new` or a new thread (reliable). Recommend (2) for long-lived threads.

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

## Adding a bot to the fleet (new profile)

1. Ask once, in one `clarify`: Discord bot + kanban, or kanban-only (no token needed); profile name.
2. Clone the closest role without channels: `hermes profile create <bot> --clone-from <similar-bot>
   --description "..."`. Without `--clone-channels` the source's bot token is NOT copied (`.env`
   holds only comments) — check `grep -oE "^[A-Z_]+=" .env`. The multiplexed gateway picks the
   profile up live ("add its bot token and it connects"); no restart.
3. The clone carries the source's SOUL.md, MEMORY.md AND USER.md. All three must be rewritten before
   first use: a one-shot "summarize your role" on the fresh clone answers as the SOURCE bot. Rewrite
   SOUL for the new role (keep the mention-token and skill-marker blocks); in both memory files keep
   only role-neutral entries (split on `\n§\n`, drop or rewrite entries naming the source role —
   USER.md typically says "user wants <source-bot> to do X", which mis-scopes the new bot).
4. `hermes -p <bot> config set model.default <id>` (live-probe the id, see Switching one bot's
   model), `agent.reasoning_effort <v> --force`, then the Discord block copied from a sibling:
   `discord.require_mention true`, `discord.allowed_channels <channel>`, `DISCORD_ALLOWED_USERS`,
   `DISCORD_COMMAND_SYNC_POLICY off` (the last two land in `.env` via `config set`).
5. Token: the user creates the app (Bot → Reset Token, enable Message Content Intent, invite with
   `bot` scope) and writes it themselves — `hermes -p <bot> gateway setup` or a line in the profile
   `.env`. Never accept it in chat (see Secrets never travel through chat); a pasted token must be
   reset in the developer portal before use. Give the user a hidden-input one-liner for their own
   terminal: `read -rs "?토큰: " T && echo "DISCORD_BOT_TOKEN=$T" >> ~/.hermes/profiles/<bot>/.env
   && unset T`. The gateway re-scans a profile on `.env` change; confirm with
   `✓ discord connected (profile: <bot>)` in `gateway.log`, then run the token audit in
   `references/discord-bot-plumbing.md` (no overlap with siblings, differs from any pasted token,
   `/users/@me` names the new app).
6. Verify with a one-shot role test (`hermes -p <bot> chat -Q -t file --max-turns 2 -q "역할과
   금지사항 요약"`) and the `model=<id>` line in its `agent.log`, then add the bot to the shared
   AGENTS.md role table and to any SOUL that routes work to it.
7. Consistency sweep across the WHOLE fleet, not just the SOULs you edited: every sibling SOUL
   (implementer, helper) needs a hand-off line for the new bot's trigger ("최종점검 → <bot>"), or a
   request that lands on them is handled the old way. Grep all SOULs, both memory files of every
   profile, and the shared + per-project AGENTS.md for the superseded wording. Then ask EVERY bot
   the same one-shot question in a fresh session ("if the user asks you for <trigger>, what exactly
   do you do?") and tabulate the answers — each must route or act per the new design.

A "final check" bot on a stronger, different model (independent re-derivation of the key numbers,
no code, no task creation, never `request-review`, ends with a decision report: per-criterion
met/unmet/unverified with numbers, defects by severity, unverified items, risks, advisory pick) is
the alternative to raising effort on the reviewer: different model = different blind spots.
Check the model is in `agent/usage_pricing.py` first — if not, cost tracking reports it as unknown;
tell the user to read the bill from the provider console. Keep decision authority with the user
in its SOUL explicitly.

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
   provider first (Discord bot token: developer portal → Bot → Reset Token); moving it to a file
   does not un-leak a value sitting in a session DB. Do not write the pasted value anywhere, even
   when the user says "just use this" — finish the non-secret setup and leave the slot empty.
2. **The user writes the new value themselves**, in their terminal, straight to the file the tool
   reads — a downloaded credential file moved into place is best, since nothing is ever typed.
   When a bot asks the user to put an API key at a path, prepare the slot for them: `mkdir -p`
   (chmod 700), `touch` + chmod 600, then `open -e <file>` so they paste one line and save; also
   give the hidden-input alternative (`read -rs "?key: " K && printf '%s' "$K" > <file> && unset K`).
   Point them to the provider console's spend limit / prepaid-credit setting in the same reply.
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

Bringing Claude Code plugin content into Hermes ("claude code 안에 있는거 넣어줘"):
1. Inventory every plugin — local (`installed_plugins.json` → `installPath`) AND account-synced
   (`~/.claude/plugins/synced/<bucket>/<plugin>`) — counting skills, commands, agents, hooks,
   MCP servers. Only `skills/*/SKILL.md` transfers; commands/agents/hooks are Claude Code formats,
   and hook-driven plugins (memory, context compressors) don't run in Hermes. Most MCP servers
   need SaaS accounts — skip unless asked.
2. Propose a subset tied to the user's work (typically engineering + data skills), dropping
   ones that duplicate an existing Hermes skill; never import everything (~200 skills = index
   tokens every turn). Ask once with the list.
3. Check name clashes across default, every bot folder, and shared-skills before copying.
4. Copy (not link — plugin updates rewrite the cache) to `~/.hermes/skills/claude-plugins/<name>`,
   rewrite `description` to ≤60 chars with a "Use when …" trigger, keep the original as an HTML
   comment, and add a one-line note where the body uses `~~category` connector placeholders
   ("use the matching Hermes skill/CLI"). Claude-only frontmatter keys (`user-invocable`,
   `allowed-tools`) are ignored by Hermes — leave them.
5. `hermes curator pin <name>` each (unmanaged local skills accept it), link the bot-relevant
   subset into `shared-skills`, then verify per bot as in Sharing skills across profiles.
Tell the user the copies don't follow plugin updates.

## Sharing skills across profiles

A skill installed in the default profile is invisible to bot profiles. Don't copy it per
profile (copies drift, and the curator edits each separately) and don't point bots at the whole
`~/.hermes/skills` (unrelated skills such as jailbreak/creative/device ones enter every bot's
prompt, ~1k extra tokens of skill index per turn). Share a curated subset:

1. List default-only skills (from the dashboard reader or a per-profile `SKILL.md` name diff) and
   propose a subset by function (dev/github, data/ML, docs, kanban ops) for the user to confirm.
2. `mkdir ~/.hermes/shared-skills` and symlink each chosen skill dir, keeping its category path:
   `ln -s ~/.hermes/skills/<cat>/<name> ~/.hermes/shared-skills/<cat>/<name>`. Add a README
   (purpose, add/remove commands, precedence).
3. Back up each bot `config.yaml`, confirm it has no `skills:` key, then append
   `skills:\n  external_dirs:\n    - ~/.hermes/shared-skills`. The loader follows symlinked dirs.
4. Verify per bot: `COLUMNS=250 hermes -p <bot> skills list | grep -c external` (without
   `COLUMNS` the table truncates long names and a name diff reports false misses). Skills with
   `environments: [kanban]` in frontmatter only appear inside kanban runs — check them with
   `HERMES_KANBAN_TASK=t_test` set before calling them missing. Then one-shot a bot to
   `skill_view` a shared skill and confirm the tool result `success: true`.

Tell the user: the bot's own skill of the same name wins; links mean a bot's auto-edit of a
shared skill rewrites the default original; open threads keep their old skill list (new
threads see it); any dashboard "installed" column built from profile folders needs a shared
marker (see `references/dashboard-service.md` → Skills page).

## Making skill usage visible in answers

When the user wants to know which skills actually fire, add the requirement to the instruction
layer (`SOUL.md` per profile, `~/.claude/CLAUDE.md` for Claude Code) rather than wiring tool
hooks — every runtime honors it and there is no plumbing to maintain. Require a one-line marker
at the top of the answer naming the loaded skills, and state explicitly that **nothing is printed
when no skill was used**; without that clause every reply grows a "none" line and the signal is
lost in noise.

Recommending skills per question ("질문마다 스킬 추천") is the opposite direction and does need
plumbing: a `pre_llm_call` shell hook picks candidates and its injected text tells the model to
load a fitting one before answering (`💡 추천 스킬:` only for related-but-unneeded ones). Recipe,
consent registration for headless gateways, human-turn scoping (kanban notices, first turn vs
mid-thread), precision rules and the eval/replay script in `references/shell-hooks.md`.

Judge such a hook on real Discord traffic, not hand-picked questions — replaying a week of logged
turns is what exposed its noise. The injected context is ephemeral (not stored in `messages`),
so measure effect as "candidate skill was `skill_view`ed in that turn", not by searching stored
text.

"Bots skip installed skills" — diagnose in this order before changing anything:
1. Measure per human turn: was a relevant skill loaded in that turn OR earlier in the session.
   Most "skipped" turns are follow-ups with no relevant skill, and a skill loaded once stays in
   context, so a raw per-turn load rate (often ~6%) badly understates use.
2. Does that bot actually have the skill (`COLUMNS=250 hermes -p <bot> skills list`)? Design/
   methodology skills often live only in default — share them.
3. Is its category demoted to `[names only]`? That happens only under
   `agent.coding_context: focus`; under the default `auto` it is not the cause.
4. Model judgment: generic methodology skills (testing-strategy, analyze, architecture,
   code-review) get skipped as "already known" despite the MUST-load prompt, while project/
   procedure skills load fine. Fix with a SOUL section `## 스킬 먼저 로드`: a task-type → skill
   table, only two allowed skips (not in your list; already loaded and still in context), "don't
   just show 💡 — load it", and "this does not change role rules". Pair it with hook text saying
   "load first". An always-present index beats relying on the model's description-based choice.
Verify interactively (pty path below) with the previously missed question types plus a
near-miss negative (an off-topic question must load nothing, 0 tool calls). For a number that
holds up, run a trigger eval: ~20 prompts (half should-load incl. paraphrases that never name the
domain, half near-misses sharing its words), each 3×, target ≥80% loaded / ≤20% false loads —
three single runs are anecdote. Harness that works (`~/.hermes/hooks/skill_trigger_eval.py`):
`script -q /dev/null timeout 100 hermes -p <bot> chat -t skills -q "<q>"` per run, parse
`📚 Skill <name>` from the ANSI-stripped output, thread pool of ≤5 (bots share the provider login
with live Discord traffic). `-t skills` only: no file/terminal side effects, and the load decision
happens in the first seconds, so don't wait for the full answer. Run it as a background job with
notify (~40 min for 2 bots × 20 × 3). These local runs land in the bot's `state.db` as
`source='local'` sessions — every usage metric (monitor scripts, dashboards) must filter
`sessions.source='discord'` or the eval inflates it.

Discord is the claim the user cares about; CLI tests only prove the mechanism. Report the two
separately: "applied" (files, hook log `platform=discord`, `prompt-size --platform discord`) vs
"observed in a real Discord turn" (a `skill_view` in a `source='discord'` session that started
after the change, or the new SOUL phrase in that thread's stored prompt via the system_prompts
hash join below). Open threads only pick up SOUL edits if a compaction rebuilt their prompt
(`Compaction rebuilt a drifted system prompt` in the profile's `agent.log`) — check the stored
prompt rather than assuming either way. Bot-authored messages are ignored by default
(`allow_bots`), so a real Discord test needs the user to post in a NEW thread: hand them 2–3
paste-ready messages (two should-load, one off-topic) and what you will check afterwards. New SOUL rules reach new
threads; long open threads keep their stored prompt until compaction.

The user wants this hook ON for every profile; it measurably turns a skipped skill into a loaded one
(same interactive question: no `skill_view` without it, `code-review` + `github-code-review`
loaded with it). When bots under-load skills, check the hook is registered before anything else.
After adding or importing skills, run the hook's `--explain` with a few domain questions for
the new skills — Korean queries often miss them until synonyms are added. The `🧩 스킬:` usage
marker stays. Removing any injection hook: delete the `hooks:` block
from every profile `config.yaml` (backup first), `hermes -p <p> hooks revoke "<command>"`, wait
~30 s, confirm the hook log stops. Threads whose history already holds injected blocks or the
model's reactions to them keep imitating them — find them with a `state.db` query on a
distinctive phrase of the block and recommend `/new` for those threads only.

## Bot skills at the size limit

`skill_manage` refuses any skill file over 100,000 chars — SKILL.md AND each `references/` file
(same check on `write_file`). A bot that hits it trims the file to just under the cap, so every
later patch fails again — visible only as `Tool skill_manage returned error … limit: 100,000`
WARNINGs in that profile's `errors.log`. Hermes' linter already warns at ~24k (`skill_view` loads
the whole body and it stays in context all session). Sweep all bots and include reference files,
not just the skill that errored — several sit at the cap together. `find -size` and
`prompt-size`'s `skill_md_bytes` count bytes (Korean ≈3 bytes/char), so use them only as a
prefilter and decide on `wc -m`:
`find ~/.hermes/profiles/*/skills \( -name SKILL.md -o -path '*/references/*.md' \) -not -path '*/.archive/*' -size +80k -exec wc -m {} + | sort -rn`
A reference file already near the cap is split sideways: keep its name for the first part (old
pointers keep working), move whole `## ` sections to sibling topic files, add a note at its top
naming them, and list each sibling in SKILL.md's References with its own "read when".

Split (bot-owned skills need the user's OK):
1. Back up each dir: `COPYFILE_DISABLE=1 tar -C <category dir> -czf
   ~/.hermes/backups/<ts>_skill_split/<name>.tgz <name>` — without the env var macOS adds `._*`
   AppleDouble members that break any later diff or check.
2. Target shape: SKILL.md ≤24k with always-on rules first (role boundaries, approval/submission
   gates, current-state facts — after compaction only the start may survive), a short step
   overview, then `## References` listing every file with a "read when …" condition. Detail moves
   verbatim into topical `references/` (extend an existing topic file before creating one), one
   level deep, `## Contents` atop reference files over 100 lines, frontmatter byte-identical.
3. Gate: `python3 scripts/skill_split_check.py <profile> <name> <backup dir>` must print PASS —
   every non-empty original line (old SKILL.md + old references) still present, size, frontmatter,
   every reference linked. Run it on the untouched skill first to prove it reports 0 missing.
4. Each skill needs a full read, so give one skill per subagent in parallel with the rules
   above, the checker command, and "the bot is live: re-check SKILL.md mtime before the final
   write and merge". Re-run the checker yourself on every result — children self-report.
5. Verify loading through Hermes itself, not just the files: with
   `HERMES_HOME=~/.hermes/profiles/<bot>` and the Hermes venv, call
   `tools.skills_tool.skill_view(name)` and `skill_view(name, file_path='references/<x>.md')` and
   check `success` + content length for every split skill.
6. Cause is bots appending incident narration to skills, so prevent the repeat with a SOUL
   section `## 스킬에 기록할 때` in every bot: lessons only (rule + one-clause why; no dates, card/
   PR numbers, narration); check `wc -m` before a patch and, past 20,000 chars, add nothing to the
   SKILL.md body — append to the matching `references/<topic>.md` via `skill_manage` with
   `file_path` (new topic file if none fits) and add one router line only if it is not listed;
   on the 100k error, move content to references instead of trimming to fit.

## "Do the bots use plugins?"

Discord bots run Hermes, so Claude Code plugins (`claude plugin list`) never apply to them —
say so first. For Hermes: `hermes -p <bot> plugins list` (Source column: `bundled` vs
user-installed), and actual use = counts of plugin-provided tool names (`browser_*`,
`web_search`/`web_extract`, `vision_analyze`, `image_*`, `memory`) in that bot's
`messages.tool_calls` over 30 days (read-only `state.db`). Report a per-bot table: total tool
calls vs plugin-backed calls.

## Protected instruction files and approval timeouts

`AGENTS.md` writes require per-write approval that can **expire silently**; the write is refused,
not queued. When the refusal says not to retry, don't — tell the user to approve and batch the
remaining edits into that one approval instead of firing them one at a time. Put the exact
pending patch into the deliverable (e.g. an appendix of the design doc) so nothing is lost.

Kanban workers run headless. Nobody answers their approval prompt, so a worker's write to a protected file (AGENTS.md) always times out. Workers also run as delegate children, which cannot mutate kanban state through the CLI, so a worker cannot run `boards set-default-workdir` either. Keep both steps out of worker specs. Either the operator does them, or the spec has the worker write `docs/AGENTS.md.draft` for the user to approve and place.

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

Subdirectory AGENTS.md is injected once per directory per live agent (`subdirectory_hints`
keeps `_loaded_dirs`), so an edit does not reach a chat thread that already touched that folder.
It arrives when the cached agent is rebuilt (after about 1 h idle, then the next message), in a
new thread, or in any kanban run. For immediate effect, tell the user to say "re-read
`<project>/AGENTS.md`" in the thread.

To confirm AGENTS.md reached a chat turn: with `terminal.cwd` pinned it is in the session's stored
system prompt; without it, search for `Subdirectory context discovered` inside a tool result. The
stored prompt is content-addressed — `sessions.system_prompt` is NULL; join on the hash:

```bash
sqlite3 ~/.hermes/profiles/<bot>/state.db "select s.id, length(p.prompt),
  instr(p.prompt,'<old phrase>')>0, instr(p.prompt,'<new phrase>')>0
  from sessions s join system_prompts p on p.hash=s.system_prompt_hash
  where s.source='discord' and s.ended_at is null"
```

This is how to answer "which open threads still run the old rules?" after a SOUL change —
list them with titles/message counts and recommend new threads for those, rather than editing the
stored prompts (DB surgery + a one-turn cache break per thread). Offline check of what a profile would load (run outside the
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
  When the test touches skills, include the `skills` toolset (`-t skills,file`) — without it
  `skill_view` is absent and the bot falls back to reading files, which tests nothing.
- **Never judge skill AUTO-loading from `chat -q`/`-Q`.** One-shot sessions get a lean `## Skills`
  prompt ("load only for knowledge you lack; don't load process skills") instead of the gateway's
  "MUST load / err on the side of loading", so they skip skills a Discord turn would load. Run the
  interactive path in a pty and exit after the answer:
  `(sleep 120; printf '/exit\r') | script -q /dev/null timeout 170 hermes -p <bot> chat -t skills,file -q "<question without the skill name>"`,
  then read that session's `skill_view` calls from `state.db` (`json_each(tool_calls)`). Confirm
  the prompt variant with `instr(p.prompt,'MUST load')` on the session's `system_prompts` row.
  A skill that is listed and still skipped is the model's judgment (often several overlapping
  skills for one task), not a broken install — report it that way, with the real Discord
  load rate (discord sessions with ≥1 `skill_view` / all discord sessions, 14 days).
- Role-split tests run safely against throwaway files in the scratch dir (a 2-line buggy
  function + a small diff): T1 "fix this" with "(no kanban tools here — describe what you would
  do in ≤5 lines)" must yield a spec + coder task plan and leave the file unchanged; T2 the
  explicit override phrase must edit the file (`cat` it after); T4 "review this diff only" must
  return 🔴/🟡/🟢 with no task. These need no Discord.
- Run several bots in parallel from `execute_code` with a thread pool calling `terminal()`; the
  terminal tool rejects `&` backgrounding in foreground commands.
- Give concrete paths in test prompts. A vague "pick any log under logs/" fails on discovery and
  tests the wrong thing; name the file so the test checks the rule (e.g. which loader was used).
- To test real kanban behavior (routing, effort, a SOUL rule) end to end, use a throwaway board,
  never the project board: `hermes kanban boards create <x>_tmp --default-workdir <scratch dir>`,
  create the task with `--workspace "dir:<scratch dir>"` and a body with an exact expected
  result, let the live dispatcher run it, check files + `task_events` + the worker session's
  `model`/effort in the assignee's state.db, then `hermes kanban boards rm <x>_tmp` (archives, so
  watchers skip it).
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
A pin-routing table must name every tier, including the default workhorse (e.g. reviewer-owned
non-design chores → Sonnet), not only the exceptions. Mechanical no-review chores (move/archive
files, reformat, list, summarize logs) go to the cheap **bot** (assign `helper-bot`), not a Haiku
pin on another bot — its SOUL then applies. A quick-answers helper SOUL usually says "hand off
file work", so add a "kanban chores assigned to you" section first (do them, stay in scope, no
logic changes, `kanban_complete`, never `request-review`, `kanban_block` if it needs judgment).
Never route a task that will be reviewed to the cheap bot — the review run inherits the model.

Reasoning effort per stage: without any task pin, each run uses its assignee profile's
`agent.reasoning_effort` (`hermes -p <bot> config get agent.reasoning_effort`), and a review run
is dispatched as the reviewer — so "high only at review" already holds when the reviewer profile
is high and the implementer medium. Recommend keeping design on high (spec defects are a real
share of rejects and cost more loops than the effort saves) and cutting cost via model routing.

Final checks prefer a separate final-check bot on a different model (see Adding a bot to the
fleet): the reviewer SOUL routes "최종점검" to it as a task with `--assignee <final-bot>
--workspace dir:<project>` and NO `--model`/effort pin. Verify the route end to end on a throwaway
board: a FRESH reviewer one-shot asked only "최종점검해줘" on data with one planted error must
create the task for the final bot (`model_override`/`reasoning_effort` empty, zero
`reasoning_effort_set` events), the worker session's `model` must be the final bot's, and the
report must catch the planted error. Grep every SOUL/AGENTS and the ops docs for leftover
"xhigh final check" and "decides with <model> outside Hermes" wording after switching.

Make the route visible in the thread. The reviewer SOUL must start its reply with a fixed line
for each path: `🔀 최종점검 → <final-bot> (<model>) · <task_id> · 결과는 이 스레드로 옵니다` when
it delegates, and `🔍 reviewer(<model>) 직접 검증 — 최종점검 아님` when it checks inline. Only
the literal trigger word should route. "자세히 검증해줘" stays with the reviewer, because routing
every "verify" to the premium bot makes routine checks expensive. Without the 🔍 line the user
cannot tell which model did the check. Test both phrasings on a throwaway board in fresh
one-shots.

Handoff content: the reviewer's task body (decision at stake, artifact paths, pass criteria from
AGENTS.md, what it already checked) is the default route — fewest tokens, a board record, and no
conversation to anchor the checker on the reviewer's conclusions. Put paths and criteria in the
body, not verdicts, because whatever the reviewer missed is also missing from its summary. Tagging
the final bot in a thread is the quick path: it reads only the last ≤50 visible Discord messages
(never the other bot's tool calls or files), so cost is bounded; no need to shrink the backfill.
Tell the user the reviewer route works only in threads started after the SOUL change, while
tagging a brand-new final bot works in any thread (it has no old session).

The per-task effort route below remains for other uses. A per-task effort is possible: the kanban DB
has a `reasoning_effort` column, the dispatcher adds `--reasoning <v>` to every worker of that
task, and it survives `unblock` — but the CLI and bot tools cannot set it. Call
`hermes_cli.kanban_db.set_reasoning_effort` from a small script (the ops repo's
`kanban_set_effort.py`, run with the Hermes venv). Because it applies to EVERY run of the task,
the final check must be its own task: `create --initial-status blocked` → set effort →
`kanban unblock` (a `ready` task can be claimed before you set it). Prove it offline with
`kanban_db_dispatch._worker_argv(task, ...)` containing `--reasoning xhigh`. Put "only when the
user explicitly asks for a final check" in the reviewer SOUL, and tell the user the trigger is that
word to the reviewer bot in a new thread — a generic "verify carefully", or asking the operator
chat, does not switch effort. When the user reports "I asked and it didn't change", find the turn
in the bot's state.db (`messages` by timestamp → `session_id`), then compare that session's
`started_at` with the SOUL.md mtime and grep its tool calls for the effort script: a thread older
than the rule runs the old SOUL and just does the check inline. Offer two fixes: spell the
procedure out in the message (blocked task → set effort → unblock) so the old thread follows it,
or have the old thread write a handoff doc and continue in a new thread (files, kanban, memory
carry over; only the chat flow does not). The effort-watch alerts (`references/scheduled-alerts.md`) let them
see it apply. Cost: effort raises only the
thinking/output share, a small part of a cache-heavy session's bill.

Switching effort mid-conversation does not invalidate the prompt cache in practice: alternating
high/xhigh/none across turns of one resumed session (`hermes -p <bot> chat --resume <id>
--reasoning <v>`) kept the ~13k system+tools prefix as cache reads every turn. Measure such
claims this way (per-turn deltas of `sessions.cache_read_tokens/cache_write_tokens` in the
profile's state.db) instead of quoting provider docs; `thinking` (on/off/adaptive) and `effort`
are separate API parameters, and Hermes changes only `effort` between high and xhigh.

Token saving: find where the spend actually goes before tuning the final-check path. Sum
`input_tokens+cache_read_tokens` and `cache_write_tokens` per profile and per session over 7 days
from each `state.db`. One long-lived thread typically outweighs everything else, and cache writes
cost about 12× reads, from idle-expiry and prompt rebuilds. The lever is "one job per thread, new
thread when done". To retire a long thread without posting into it, run one resumed one-shot:
`hermes -p <bot> chat -Q -t file,terminal --resume <session_id> -q "write a handoff to
<project>/docs/봇_인계_<date>.md: state, done phases + doc paths, open tasks, decisions/user
instructions, next steps, pitfalls; re-check numbers from files/kanban; write nothing else"`.
Spot-check its numbers yourself, then give the user a paste-ready first message for the new
thread.

Cron jobs are not a model tier: check `cron/jobs.json` per profile before claiming which bot
"does cron". A job's delivery uses its OWN profile's platform credentials — the multiplexed
gateway does not lend a bot's token to another profile's cron. A default-profile job with
`--deliver discord:<ch>` fails preflight (`blocked_config … has no gateway credentials`) when
only the bot profiles hold `DISCORD_BOT_TOKEN`. Create Discord-delivered jobs in a bot profile
(`hermes -p <bot> cron create …`; the job then runs on that bot's `model.default`, or pin with
`--model`), make any skill it uses reachable from that profile (a catalog install lands only in
the chat's profile — link it into the shared skills dir, see Sharing skills across profiles),
remove the failed default copy, then test with `hermes -p <bot> cron run
<id>` and prove delivery from `profiles/<bot>/cron/deliveries.db` (`status=delivered`, empty
`error`) — not from the run's "succeeded" line. Don't copy a bot token into the default `.env`
to fix it: two connections on one token knock each other off.
Monitoring/usage reports should be `no_agent` scripts (zero tokens, deterministic);
put a job on the cheap bot's profile with a model only when its output needs interpretation or
summarizing.

## Depth

- `references/kanban-review-loop.md` — making implementer→reviewer handoff actually route.
- `references/discord-bot-plumbing.md` — mentions, tokens, profile/account mapping, tagging a
  second bot in another bot's thread (allow_bots / thread_require_mention), and "bot isn't
  answering" triage (adapter fatal/retry, inbound check, dead OAuth login, quiet hours, recurring
  disconnect correlation).
- `references/scheduled-alerts.md` — zero-token cron alerts, edge-triggered notification, the
  standard fleet automation set (kanban anomaly watch with evidence capture, daily
  `hermes backup`, weekly metrics post, effort change/apply watch, kanban auto-wake for
  `SCHEDULED_UNTIL=` parked cards) and how to test each before
  scheduling.
- `references/dashboard-service.md` — running the web dashboard, autostart, the env trap,
  watching fleet work live (Kanban tab, `kanban watch`/`tail`, tmux split), and building a
  project-centric view on Hermes data (plugin tab vs separate app; never mount WAL DBs into
  containers; design → private app repo → cluster-free Phase-0 checks; guiding the user to
  enable Docker Desktop Kubernetes; in-cluster Phase-0 probes; Phase-1 build order, rule-chain
  parity check, board→project mapping when `default_workdir` is null, non-root Secret
  permissions, launchd/background-shell traps; Phase-2 summary batch: message filters, dry-run
  first, token-estimate ratio, fact-check method, freshness (hourly runs, same-day merge,
  missing-field defaults, overlap guard, thread→project pinning); progress percentages — score/checklist via
  heartbeat `진행 k/N`/recent completion/time elapsed, and why plain completion rate is useless;
  skills page — inventory/source/per-profile drift/usage from `skill_view` calls, hash-gated
  Korean summaries, functional grouping (name rules over folder categories); skill search — client filter + host-side body search, Korean→English
  synonyms, word-boundary matching for short terms; keeping it project-agnostic; ops page from
  `gateway.error.log` + cron files; usage page spreading cumulative per-session cost by day;
  launchd urgent alerts outside the gateway, mention-masking trap; cost alerts from snapshot
  diffs; moving the summary batch from an API key to the Claude subscription via the official
  CLI in the container).
- `references/fleet-design-doc.md` — writing/revising the fleet architecture document, and
  evolving the design from kanban metrics (reject rate, crashes, unused task features).
- `references/gateway-resource-usage.md` — measuring gateway CPU/RAM right (CPU-time deltas,
  sleep bias), the macOS osascript-wrapper idle-CPU cost and how to remove it, whole-machine
  battery triage, "can this Mac run it 24/7" capacity check (swap, Docker VM size, disk), and
  safe Docker disk cleanup (A/B/C groups, DB dump before volume delete).
- `references/ops-repo-publishing.md` — keeping ops docs project-agnostic in their own repo,
  kanban hygiene (notify-subscription cleanup), pushing the repo + own skills to GitHub without
  leaking IDs, going public (withholding live-project content, squash, per-folder commit
  labels), and filing upstream bug reports.
- `references/shell-hooks.md` — per-turn context injection with `pre_llm_call` shell hooks
  (payload fields, consent allowlist on unattended gateways, live reload, platform/attachment
  filtering, fail-open, keyword-scoring precision), the skill-recommendation hook as the worked
  example, and how to verify it reached a real Discord turn.
- `scripts/verify_fleet.sh` — one-shot check that prompt edits are live on every profile.
- `scripts/skill_split_check.py` — zero-loss/size/link gate for splitting an oversized skill
  (see Bot skills at the size limit).

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

The reviewer bot also unblocks and re-scopes tasks on its own. Before the operator acts on a blocked task, read the events and comments that came after the block: `hermes kanban --board <b> show <id>`, or `task_events` with `id >` the block event's id. It may already be unblocked and running under a new comment that overrides the body (e.g. "write a draft, not the file"). If the operator acted anyway, report the overlap and reconcile the two outputs; do not re-run `unblock`.

## Reading Hermes DBs from the shell

Never point the `sqlite3` CLI at a path you have not checked exists — it creates a 0-byte DB file
on open, and every reader that globs `kanban/boards/*/kanban.db` (dashboard host reader, watch/wake
scripts) then crashes on `no such table: tasks`. Loop boards with `[ -f "$db" ] || continue` and
open as `sqlite3 "file:$db?mode=ro"`; in Python use `sqlite3.connect(f"file:{db}?mode=ro",
uri=True)` after `db.exists()`, and skip DBs without a `tasks` table. If a dashboard or script
breaks right after an inspection pass, look for fresh 0-byte `kanban.db` files first
(`find ~/.hermes/kanban -name kanban.db -size 0`).

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
and say so. Mark each todo completed the moment it is verified — a stale checklist shown in the
UI makes the user ask "isn't this already done?". Answer "추천하는 방법은?" with one pick per open
decision plus the reason and the exact next action, not a re-listing of the options.

When the user asks to check outside docs/articles for something you built, return a table: source
(link) → key finding → what it means for our setup, then a short list of concrete changes. On
"근거가 있고 우리거에 넣으면 좋으면 진행", apply every evidence-backed item (backup first) and defer only the
ones whose value depends on a measurement you haven't run yet, saying which measurement decides them.

Korean, direct, peer tone. Lead with the finding, then the evidence table. When the user asks
"measure again", re-measure fresh (new deltas, same method) and compare against the previous
numbers in the table — including correcting an earlier estimate that the new data disproves. State measured
numbers (PIDs, byte counts, HTTP codes) rather than "it should work now". Never report a
check as passed from `$?` after a pipe (`cmd | tail -5; echo rc=$?`) — that is the last
command's status, so a crashed `tsc`/test run reads as rc=0; run the check unpiped, or use
`set -o pipefail` / `${PIPESTATUS[0]}`, and read its own output for the pass line. When you were wrong
earlier in the session, say so plainly in one line and correct it — do not quietly restate.

When a delete/disable instruction could refer to more than one pending thing (a feature, a
recommendation in your last answer, a plan item), ask which in one line before acting —
removing the wrong one silently is worse than a one-line question.

Before running an ops script just to see its options, read its argv handling: a script without
argparse ignores `--help` and performs its full action (copy, delete, push prep).
